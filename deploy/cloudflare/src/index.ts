// Rozprava on Cloudflare (docs/production-deployment.md).
//
// Every request goes to one web container running the FastAPI app. A daily cron
// starts a second container from the same image that imports new transcripts,
// tags their word forms and embeds them (`python -m rozprava.ingest update`).
// Both live in the EU jurisdiction, near the Neon database in Frankfurt. The
// Worker limits how often one visitor may request summaries and searches, which
// cost money (Claude) or free tokens (Voyage).
import { DurableObject } from "cloudflare:workers";

const PORT = 8080;
// A quiet site lets its container sleep; the next visitor waits for a start.
const WEB_IDLE_MS = 15 * 60 * 1000;
// The import exits by itself; one still running after this long is stopped.
const UPDATE_LIMIT_MS = 3 * 60 * 60 * 1000;
// How long a stopping container may finish its work before it is destroyed.
const DRAIN_MS = 30 * 1000;
const SIGINT = 2; // the importer records an interrupted run (KeyboardInterrupt)
const SIGTERM = 15; // uvicorn finishes in-flight requests, then exits

// Values the app reads from its environment (settings.py). Secrets come from
// `wrangler secret put`; empty ones are left out so the app sees them as unset.
function appEnv(env: Env): Record<string, string> {
	const values: Record<string, string | undefined> = {
		DATABASE_URL: env.DATABASE_URL,
		VOYAGE_API_KEY: env.VOYAGE_API_KEY,
		ANTHROPIC_API_KEY: env.ANTHROPIC_API_KEY,
		ROZPRAVA_AI_MONTHLY_LIMIT_USD: env.ROZPRAVA_AI_MONTHLY_LIMIT_USD,
	};
	return Object.fromEntries(
		Object.entries(values).filter((entry): entry is [string, string] => Boolean(entry[1])),
	);
}

/** Ask a container to stop; destroy it if it has not exited after DRAIN_MS. */
async function stop(container: Container, signal: number, reason: string): Promise<void> {
	container.signal(signal);
	const exited = await Promise.race([
		container.monitor().then(
			() => true,
			() => true,
		),
		scheduler.wait(DRAIN_MS).then(() => false),
	]);
	if (!exited && container.running) {
		await container.destroy(reason);
	}
}

/** The app's own redirects name the container's host ("http://container/…"). */
function publicLocation(response: Response, origin: string): Response {
	const location = response.headers.get("location");
	if (!location) {
		return response;
	}
	const target = new URL(location, "http://container");
	if (target.host !== "container") {
		return response;
	}
	const fixed = new Response(response.body, response);
	fixed.headers.set("location", `${origin}${target.pathname}${target.search}${target.hash}`);
	return fixed;
}

export class Web extends DurableObject<Env> {
	private starting: Promise<void> | undefined;
	private ready = false;
	private image: string | undefined; // the image the running container started from

	constructor(ctx: DurableObjectState, env: Env) {
		super(ctx, env);
		const container = ctx.container!;
		void ctx.blockConcurrencyWhile(async () => {
			this.image = await ctx.storage.get<string>("image");
			if (container.running) {
				// After a deploy or restart the Durable Object forgets its timeout.
				await container.setInactivityTimeout(WEB_IDLE_MS);
			}
		});
	}

	async fetch(request: Request): Promise<Response> {
		const container = this.ctx.container!;
		if (!this.ready || !container.running || this.image !== container.images.base) {
			// Concurrent requests share one start and readiness check.
			this.starting ??= this.start().finally(() => {
				this.starting = undefined;
			});
			await this.starting;
		}
		const url = new URL(request.url);
		url.protocol = "http:";
		url.host = "container";
		const forwarded = new Request(url, request);
		forwarded.headers.delete("host");
		const response = await container.getTcpPort(PORT).fetch(forwarded);
		return publicLocation(response, new URL(request.url).origin);
	}

	private async start(): Promise<void> {
		const container = this.ctx.container!;
		if (container.running && this.image !== container.images.base) {
			// A deploy brought a new image; a busy container would otherwise never be
			// replaced. Requests already inside it finish; new ones wait for the start.
			this.ready = false;
			await stop(container, SIGTERM, "Replaced by a newly deployed image");
		}
		if (!container.running) {
			this.ready = false;
			const image = container.images.base;
			container.start({ image, instance: "basic", enableInternet: true, env: appEnv(this.env) });
			this.image = image;
			await this.ctx.storage.put("image", image);
			container.monitor().finally(() => {
				this.ready = false;
			});
		}
		await container.setInactivityTimeout(WEB_IDLE_MS);
		// Ready once the app answers at all; without its database it answers 503 itself.
		const port = container.getTcpPort(PORT);
		let lastError: unknown;
		for (let attempt = 0; attempt < 150; attempt++) {
			try {
				const response = await port.fetch("http://container/health", {
					signal: AbortSignal.timeout(2000),
				});
				await response.body?.cancel();
				this.ready = true;
				return;
			} catch (error) {
				lastError = error;
				await scheduler.wait(200);
			}
		}
		throw new Error(`The app did not answer on port ${PORT}`, { cause: lastError });
	}
}

export class Update extends DurableObject<Env> {
	constructor(ctx: DurableObjectState, env: Env) {
		super(ctx, env);
		const container = ctx.container!;
		if (container.running) {
			// After a deploy the Durable Object forgets its timeout, which would stop
			// the import soon; the alarm still enforces the absolute limit.
			void ctx.blockConcurrencyWhile(() => container.setInactivityTimeout(UPDATE_LIMIT_MS));
		}
	}

	/** Start today's import unless one is still running; returns at once. */
	async run(reason: string): Promise<string> {
		const container = this.ctx.container!;
		if (container.running) {
			return "An import is still running.";
		}
		container.start({
			image: container.images.base,
			instance: "standard-1", // the Czech tagger needs about 400 MB besides the app
			enableInternet: true,
			env: appEnv(this.env),
			entrypoint: ["python", "-m", "rozprava.ingest", "update"],
		});
		await container.setInactivityTimeout(UPDATE_LIMIT_MS);
		// Each cron or manual call wakes the object and restarts the inactivity
		// clock, so a hung import could live forever; the alarm is an absolute limit.
		await this.ctx.storage.setAlarm(Date.now() + UPDATE_LIMIT_MS);
		console.log(`Import started (${reason}).`);
		return "Import started.";
	}

	async alarm(): Promise<void> {
		const container = this.ctx.container!;
		if (container.running) {
			console.log("Import still running after its time limit; stopping it.");
			await stop(container, SIGINT, "Import exceeded its time limit");
		}
	}
}

function eu<T extends Rpc.DurableObjectBranded | undefined>(
	namespace: DurableObjectNamespace<T>,
	name: string,
): DurableObjectStub<T> {
	const jurisdiction = namespace.jurisdiction("eu");
	return jurisdiction.get(jurisdiction.idFromName(name));
}

async function sameSecret(given: string, expected: string): Promise<boolean> {
	const encoder = new TextEncoder();
	const [a, b] = await Promise.all(
		[given, expected].map((value) => crypto.subtle.digest("SHA-256", encoder.encode(value))),
	);
	return crypto.subtle.timingSafeEqual(a, b);
}

/** POST /_admin/update with "Authorization: Bearer <ADMIN_TOKEN>" starts an import. */
async function adminUpdate(request: Request, env: Env): Promise<Response> {
	const given = (request.headers.get("authorization") ?? "").replace(/^Bearer /, "");
	if (!env.ADMIN_TOKEN || request.method !== "POST" || !(await sameSecret(given, env.ADMIN_TOKEN))) {
		return new Response("Not found", { status: 404 });
	}
	const update = eu(env.UPDATE as DurableObjectNamespace<Update>, "daily");
	return new Response(`${await update.run("manual")}\n`);
}

const SLOW_DOWN = "Příliš mnoho požadavků za minutu. Zkuste to prosím za chvíli.";

function tooMany(summary: boolean): Response {
	if (summary) {
		// The search page swaps this block in where the summary would appear.
		const html =
			'<section class="summary" data-summary data-summary-note><header class="summary__head">' +
			'<h2 class="label">Shrnutí · jazykový model</h2></header>' +
			`<p class="summary__body">${SLOW_DOWN}</p></section>`;
		return new Response(html, { headers: { "content-type": "text/html; charset=utf-8" } });
	}
	return new Response(SLOW_DOWN, {
		status: 429,
		headers: { "content-type": "text/plain; charset=utf-8", "retry-after": "60" },
	});
}

export default {
	async fetch(request: Request, env: Env): Promise<Response> {
		const url = new URL(request.url);
		// The app routes on the decoded path ("/api%2Fshrnuti" is "/api/shrnuti"), so
		// rate limits must too, or an encoded path would escape them.
		let path: string;
		try {
			path = decodeURIComponent(url.pathname);
		} catch {
			return new Response("Bad request", { status: 400 });
		}
		if (path === "/_admin/update") {
			return adminUpdate(request, env);
		}
		const visitor = request.headers.get("cf-connecting-ip") ?? "unknown";
		const summary = path === "/api/shrnuti";
		const limiter = summary
			? env.SUMMARY_LIMITER
			: path === "/hledat" || path.startsWith("/api/")
				? env.SEARCH_LIMITER
				: undefined;
		if (limiter && !(await limiter.limit({ key: visitor })).success) {
			return tooMany(summary);
		}
		const forwarded = new Request(request);
		forwarded.headers.set("x-forwarded-for", visitor);
		forwarded.headers.set("x-forwarded-proto", url.protocol.replace(":", ""));
		return eu(env.WEB, "web").fetch(forwarded);
	},

	async scheduled(controller: ScheduledController, env: Env): Promise<void> {
		const update = eu(env.UPDATE as DurableObjectNamespace<Update>, "daily");
		console.log(await update.run(`cron ${new Date(controller.scheduledTime).toISOString()}`));
	},
} satisfies ExportedHandler<Env>;
