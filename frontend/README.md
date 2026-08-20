## WAH-LAH frontend

The React 19 frontend uses Vite and keeps the existing pages, components, and stylesheets in place.

```bash
yarn install --frozen-lockfile
yarn dev
```

Production commands are `yarn build` and `yarn preview`. Set `VITE_BACKEND_URL` in the
Cloudflare Pages environment to the backend URL. The player-facing Genie bubble is
mounted globally in the main app shell and uses the player's authenticated session.
