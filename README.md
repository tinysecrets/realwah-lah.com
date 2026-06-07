# Wah-Lah Migration: Emergent ➔ Fly.io + Cloudflare Pages + MongoDB Atlas

Goal: get wah-lah.com running on stable, free infrastructure that you control, independent of Emergent's preview/deploy lifecycle. End state: backend on Fly.io, frontend on Cloudflare Pages, data on MongoDB Atlas, DNS at Cloudflare.

### TL;DR Architecture

```text
[ Cloudflare DNS ]
       │
       ├───► wah-lah.com ──────► Cloudflare Pages (React Frontend)
       │
       └───► api.wah-lah.com ──► Fly.io App (FastAPI + Playwright)
                                       │
                                       └──► MongoDB Atlas DB (Cloud Data)
