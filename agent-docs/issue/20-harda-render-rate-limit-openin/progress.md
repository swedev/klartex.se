# Framsteg: Issue #20 — Härda /render: rate limit, openin_any, och policy för latex-blocket

**Påbörjad:** 2026-08-27
**Senast uppdaterad:** 2026-08-27
**Status:** Klar (implementation) — deploy och produktionsverifiering återstår

## Genomförda steg

- [x] Fas 1, steg 1: Semafor (max 2 samtidiga renders) i `render.py`
- [x] Fas 1, steg 2: Tester för överlasttaket i `test_render.py`
- [x] Fas 1, steg 3: Xelatex-fritt pytest-steg i `.github/workflows/backend.yml`
- [x] Fas 1, steg 4: Container-tak i `infra/docker-compose.yml`
- [x] Fas 1, steg 5: Versionsbump 0.2.2 → 0.2.3 (pyproject + `__init__.py`)
- [x] Fas 1, steg 6: Dokumentera driftbeteendet i `backend/README.md`
- [x] Fas 2, steg 1: `infra/caddy/Dockerfile` — pinnat xcaddy-bygge
- [x] Fas 2, steg 2: Compose-tjänsten caddy byter till byggd image
- [x] Fas 2, steg 3: Rate limit, body-gräns och timeout i `infra/Caddyfile`
- [x] Fas 2, steg 4: Backup, preflight och rollback i `deploy/deploy.sh`
- [x] Fas 2, steg 5: Dokumentera i `infra/README.md`
- [x] Fas 3, steg 2: `infra/.env.example` → 0.2.3

## Verifieringschecklista

- [x] `pytest` grönt i `backend/`: 503-gren, slot-frigöring efter lyckad och
      misslyckad render, samtidighetstest — 31 tester, allt utan xelatex-beroende
      i de nya testerna.
- [x] Motsvarigheten till CI-smoketestet: `test_render_minimal_block_doc`
      renderar en riktig PDF med xelatex och semaforen på plats.
- [ ] Caddy-imagen bygger på ARM; preflight `caddy list-modules` visar
      `rate_limit`; `caddy validate` accepterar nya Caddyfile. **Går inte att
      köra lokalt** — ingen docker-daemon och ingen caddy-binär i utvecklings-
      miljön. Täcks av preflighten i `deploy.sh` innan gamla stacken stoppas.
- [ ] Efter deploy: `docker inspect klartex-se-backend` visar gränserna.
- [ ] Tre samtidiga renders mot produktion: två går igenom, tredje ger 503.
- [ ] Lång render (>60 s) fullföljer genom Caddy (`response_header_timeout` 150s).
- [ ] `POST /render` med body > 2 MB ger 413 från Caddy.
- [ ] Rendering end-to-end (vkf-bundlen) efter härdningarna.
- [ ] Sist: 11 billiga `POST /render` på en minut → nr 11 ger 429 + `Retry-After`;
      `GET /templates` och `/health` opåverkade; spoofad `X-Forwarded-For` är
      ingen bypass.

## Anteckningar

- **Modul-pinningen avviker från tag.** `mholt/caddy-ratelimit` har bara taggen
  `v0.1.0` (2025-01-06), och `ipv6_prefix` — som planens zon använder — landade
  först i commit `16aecbbc` (2026-05-21). Dockerfilen pinnar därför master-
  committen `5625512f24f6f59d6f64fb3aafe5eecff0b286db` (2026-06-12). Caddy är
  pinnat till `2.11.4` i både builder- och runtime-steget.
- **`docker compose pull --ignore-buildable` har ett fallback.** `deploy.sh`
  kollar `docker compose pull --help` och faller tillbaka på
  `docker compose pull backend` om serverns Compose saknar flaggan, så deployen
  inte fastnar på en versionsskillnad.
- **`rate_limit` behöver ingen `order`-direktiv.** Modulen ordnas numera själv
  före `basic_auth`, vilket placerar den före `reverse_proxy`.
- Fas 3 steg 1, 3, 4 och 5 (merge, deploy mot produktion, produktions-
  verifiering, koordinering mot #15) ligger utanför implementationen och körs
  av användaren efter merge. `BACKEND_VERSION` i den lokala, gitignorerade
  `infra/.env` måste bumpas till 0.2.3 innan `deploy.sh` körs.
