# Issue #20: Härda /render: rate limit, openin_any, och policy för latex-blocket

**Baserad på:** main

## Sammanfattning

`POST /render` kör xelatex på anropar-styrd payload och ska framöver vara öppet för anonyma anrop (#23), så själva renderingen måste härdas först. Efter issuekommentarens beslut 2026-08-27 utgår issuets punkt 1 (`openin_any = p`) — TeX Live 2026 har tagit bort enforcementen och prod kör redan TL2026; sandboxing av filläsning blir ett eget kärn-issue. Planen implementerar de två kvarvarande punkterna: grovt IP-rate-limit (10/min, IPv6 per /64) plus 2 MB body-tak på `POST /render` via en server-byggd, version-pinnad Caddy-image med `mholt/caddy-ratelimit`, samt resurstak (CPU/minne/swap/pids i compose plus max 2 samtidiga renders med 503 vid fullt hus). Issuets punkt 3 — token-krav för `latex`-blocket — görs enligt issuetexten tillsammans med #23 och ingår inte här.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Medel |
| **Säker för junior** | Nej |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-27
**Feedback:** Codex-granskning av den omskrivna planen (punkt 1 borttagen per issuekommentar). Tillämpat: deploy-backupen flyttad utanför `/srv/klartex` (rsync `--delete` hade raderat den) och gjord till eget SSH-steg före rsyncen; `__version__` i `__init__.py` bumpas med pyproject; semafortester skärpta (full slot-återställning, per-test-reset, bounded timeouts); xelatex-fritt pytest-steg tillagt i CI; body-gränsens rationale rättad (inga inline-assets i `RenderRequest`, 413 vid kapning); rate limit-produktionstestet får tyst window + XFF-bypass-kontroll; README-städning (`KLARTEX_VERSION`/`KLARTEX_SE_BACKEND_VERSION` → `BACKEND_VERSION`); faserna omordnade backend-först. Ej tillämpat (medvetet): aggregat-tolkningen av "per render" förblir ett flaggat öppet designbeslut i stället för blocker; risknivån hålls på Medel efter rollback-fixen.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #23 — Anonym rate-limitad nivå på /render; blockeras av detta issue och tar över punkt 3 (token för `latex`-blocket)
- #15 — API_TOKEN för writes; branchen `issue/15-api-token-auth` (öppen) överlappar sex filer (bl.a. `render.py`, `test_render.py`, compose) och väljer version 0.3.0 — merge-ordning dokumenterad i planens triagering
- #17 — Kom ikapp klartex 0.14.0; landat på `main` (PR #24), backend är 0.2.2 — ingen konflikt kvar
