// Secrets set with `npx wrangler secret put NAME`; `wrangler types` cannot see them.
interface Env {
	DATABASE_URL: string;
	VOYAGE_API_KEY: string;
	ANTHROPIC_API_KEY: string;
	ADMIN_TOKEN: string;
}
