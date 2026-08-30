# Framsteg: Issue #15 — Auth: API_TOKEN for writes and the extended surface (replaces ADMIN_TOKEN)

**Påbörjad:** 2026-08-30
**Senast uppdaterad:** 2026-08-30
**Status:** Klar

## Genomförda steg

- [x] Fas 1, steg 1: `auth.py` — `Tier`, `TOKEN_HOWTO`, `_verify`, `require_api_token`, `render_tier`
- [x] Fas 1, steg 2: `page_template_router.py` — `Depends(require_api_token)`, docstrings, `responses`
- [x] Fas 2: `render.py` — `find_latex_block`, tier-dependency, `403 token_required`, `responses`
- [x] Fas 3, steg 1: `tests/test_page_templates.py` — `API_TOKEN`, skärpta assertions
- [x] Fas 3, steg 2: `tests/test_render.py` — tier-tester och enhetstester för `find_latex_block`
- [x] Fas 3, steg 3: `pytest` i `backend/` grönt — 70 passed (baseline 43), inga skips
- [x] Fas 4: `infra/docker-compose.yml`, `infra/.env.example`, `infra/README.md`, `.github/workflows/deploy.yml`
- [x] Fas 5: `backend/README.md`, `llms.txt`, `index.html`, `PLAN.md`

## Pågående arbete

Inget — implementationen är komplett. Fas 6 (release-koordinering) ligger utanför PR:en.

## Anteckningar

- Fas 6 körs av användaren: `API_TOKEN` i serverns `.env` (med `ADMIN_TOKEN` kvar under rollback-fönstret), versionsbump till `0.5.0` i release-committen, och produktionsverifiering efter deploy.
- `ADMIN_TOKEN` finns kvar på två ställen i `infra/README.md` — i övergångsavsnittet, som avsiktligt beskriver rollback-fönstret.
- Designbeslut 2 ändrat efter PR-granskning (#62): planen valde en generisk genomgång av allt under `data["body"]` med motiveringen att en felträff ändå skulle avvisas av kärnan. Det stämmer inte — `parties.party1`/`party2` och `signatures.parties[i]` tillåter extra properties, så ett objekt som `{"name": "Alfa AB", "type": "latex"}` renderas av kärnan men fick `403` av spärren. Genomgången följer nu bara blockmotorns faktiska carriers (`list`, `columns`, `clause`), speglade lokalt i `render._child_block_lists` i stället för importerade från kärnans privata namn. Ett test pinnar spegeln mot kärnan, så en ny carrier där ger rött test i stället för en tyst lucka i spärren. *Proveniens: användarbeslut i PR-granskningen.*
- Designbeslut 3 (token på förfrågan via kontakt@klartex.se) är implementerat som `TOKEN_HOWTO` i `auth.py` och upprepat i `llms.txt`, `index.html` och `backend/README.md`. Planen markerar det som ett produktbeslut att bekräfta innan texterna låses.
