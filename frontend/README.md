## WAH-LAH frontend

The React 19 frontend uses Vite and keeps the existing pages, components, and stylesheets in place.

```bash
yarn install --frozen-lockfile
yarn dev
```

Production commands are `yarn build` and `yarn preview`. Set `VITE_BACKEND_URL` (or `REACT_APP_BACKEND_URL`) to `https://api.wah-lah.com` in the Vercel environment so the SPA reaches the backend. The player-facing Genie bubble is
mounted globally in the main app shell and uses the player's authenticated session.
