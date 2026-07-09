This is a [Next.js](https://nextjs.org) app deployed to Cloudflare Workers with the [OpenNext Cloudflare adapter](https://opennext.js.org/cloudflare).

## Getting Started

Install dependencies and run the Next.js development server:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Cloudflare Workers

Use the regular Next.js dev server for day-to-day development. Use the OpenNext preview command when you need to verify behavior in the Cloudflare Workers runtime.

```bash
npm run build
npm run preview
```

Deploy with:

```bash
npm run deploy
```

The Cloudflare entrypoint and static asset directory are configured in `wrangler.jsonc`. Adapter-specific settings live in `open-next.config.ts`.

## Data Sources

- [Cloudflare Workers Next.js guide](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/)
- [OpenNext Cloudflare adapter](https://opennext.js.org/cloudflare)
- [Next.js documentation](https://nextjs.org/docs)
