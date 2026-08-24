# Deployment validation

This file documents the Cloudflare/Supabase deployment validation checkpoint.

- Cloudflare Worker configuration: `fronted/wrangler.jsonc`
- Worker entrypoint: `fronted/src/worker.js`
- Cloudflare deployment workflow: `.github/workflows/deploy-cloudflare.yml`
- Supabase configuration is provided to the backend through repository/environment secrets.

No trading logic is changed by this checkpoint.
