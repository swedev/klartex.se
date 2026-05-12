# app/ — klartex.se-frontend

WYSIWYG-webapp som anropar `api.klartex.se/render`. Live på `app.klartex.se`.

Se `../PLAN.md` för fas-uppdelning och `../backend/README.md` för API:t.

## Stack

- React 19 + TypeScript
- Vite 6 (`@vitejs/plugin-react`)
- Tailwind CSS 4 (`@tailwindcss/vite`)
- `@radix-ui/themes` 3 + `@swedev/ui` 0.2.x
- `lucide-react` (ikoner)
- `@tiptap/react` 3 + `@tiptap/starter-kit`
- ESLint 9 (flat config) + knip

Stacken matchar referensen i `~/repos/openvera/frontend`. Saker som *medvetet*
inte är med ännu: `@tanstack/react-query` (kommer i fas 3 när vi behöver delad
async-state), `react-router` (fas 3, flera sidor), Clerk (fas 5, auth).

## Utveckling

```sh
cd app
npm install
npm run dev       # http://localhost:5173, /api proxy → api.klartex.se
npm run typecheck
npm run lint
npm run build     # producerar app/dist/
```

`vite.config.ts` proxar `/api/*` → `https://api.klartex.se/*` i dev så att
browsern aldrig ser en cross-origin-request. I prod servas `dist/` direkt av
Caddy på `app.klartex.se` och hittar `api.klartex.se` via CORS-konfiguration i
`infra/Caddyfile`.

## Deploy

`../deploy/deploy.sh` rsyncar `app/dist/` till servern om katalogen finns. Den
copy-pastar inga API-nycklar — appen har inga (admin-token används bara av
backend-CRUD på `/page-templates`).

Aktuell deploy-status: `app.klartex.se` returnerar fortfarande 404 tills första
`npm run build` + `deploy.sh` körts.
