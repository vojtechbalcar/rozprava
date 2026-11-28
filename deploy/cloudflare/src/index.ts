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

export class Web extends DurableObject<Env> {
	private starting: Promise<void> | undefined;
	private ready = false;

	constructor(ctx: DurableObjectState, env: Env) {
		super(ctx, env);
		const container = ctx.container!;
		if (container.running) {
			// After a deploy or restart the Durable Object forgets its timeout.
			void ctx.blockConcurrencyWhile(() => container.setInactivityTimeout(WEB_IDLE_MS));
		}
	}

	async fetch(request: Request): Promise<Response> {
		if (!this.ready || !this.ctx.container!.running) {
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
		return this.ctx.container!.getTcpPort(PORT).fetch(forwarded);
	}

	private async start(): Promise<void> {
		const container = this.ctx.container!;
		if (!container.running) {
			this.ready = false;
			container.start({
				image: container.images.base,
				instance: "basic",
				enableInternet: true,
				env: appEnv(this.env),
			});
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
		console.log(`Import started (${reason}).`);
		return "Import started.";
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
		if (url.pathname === "/_admin/update") {
			return adminUpdate(request, env);
		}
		const visitor = request.headers.get("cf-connecting-ip") ?? "unknown";
		const summary = url.pathname === "/api/shrnuti";
		const limiter = summary
			? env.SUMMARY_LIMITER
			: url.pathname === "/hledat" || url.pathname.startsWith("/api/")
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
