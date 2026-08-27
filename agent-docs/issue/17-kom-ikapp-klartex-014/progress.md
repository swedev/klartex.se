# Framsteg: Issue #17 — Kom ikapp klartex 0.14.0: bumpa pinnen, hantera breaking changes, uppdatera sajtinnehåll och CLAUDE.md

**Påbörjad:** 2026-08-27
**Senast uppdaterad:** 2026-08-27
**Status:** Klar

## Genomförda steg

- [x] Fas 1, steg 1: Bumpa `klartex==0.11.1` → `0.14.0` i `backend/pyproject.toml` och `backend/Dockerfile`
- [x] Fas 1, steg 2: Bumpa backendens version `0.2.1` → `0.2.2` (både `pyproject.toml` och `src/klartex_se/__init__.py`)
- [x] Fas 1, steg 3: Ominstallation (`pip install -e '.[dev]'`), `pip check` rent, testsviten grön
- [x] Fas 2, steg 1: Verifierat att `signatures`/`contract_intro`-heuristiken inte används
- [x] Fas 2, steg 2: Verifierat felsträngspassthrough + nytt test för `body[i]`-path
- [x] Fas 3, steg 1: Verifierat felhantering för ogiltig/borttagen bundle-katalog
- [x] Fas 3, steg 2: Dokumenterat asset-upplösning i `page_templates.py` och `backend/README.md`
- [x] Fas 4, steg 1: `index.html` — komplett mall-tabell, `klartex serve` ersatt med curl mot api.klartex.se
- [x] Fas 4, steg 2: `llms.txt` — komplett mall-lista, 20 verifierade blocktyper, 0.14.0-nyheter
- [x] Fas 4, steg 3: Listorna verifierade mot taggen `v0.14.0` och mot `/templates`/`/blocks` på 0.14.0
- [x] Fas 5: CLAUDE.md kärnprincip punkt 1 pekar på `backend/`
- [x] Fas 6: Slutverifiering — 27 tester gröna (inga skippade), sanity-rendering med bundle-assets

## Verifiering

- `grep -rn "0.11.1" backend/` → noll träffar
- `pip check` → "No broken requirements found"
- `pytest -rs tests/` → 27 passed, 0 skipped (xelatex fanns på PATH, så render-testerna kördes)
- Sanity-rendering: en registrerad bundle med `logo.pdf` + två `.tex`-assets, refererade både som bara filnamn och `./`-prefixade, renderade 16 kB PDF från en cwd utan någon av filerna. Textextraktion visar båda markörerna och båda loggorna → bundle-katalogen används för båda referensformerna
- Efter att bundle-katalogen raderats: `/render` ger 400 `unknown_page_template` (ingen tyst no-op)
- `index.html` listar `_block` + alla 7 recept; inga `klartex serve`-referenser kvar i repot
- `llms.txt`-blocktyplistan matchar `git -C ../klartex ls-tree --name-only v0.14.0 klartex/schemas/blocks/` (20 st)

## Anteckningar

Utöver planens filöversikt ändrades tre saker:

- `backend/src/klartex_se/__init__.py` — `__version__` speglar `pyproject.toml` och serveras av `/health`; den hade halkat efter på `0.2.1` medan `pyproject.toml` stod på samma. Båda står nu på `0.2.2`.
- `backend/README.md` — endpoint-tabellen saknade `/page-templates` helt, vilket det nya asset-avsnittet refererar till. Raderna är tillagda, med notis om att skriv-endpointsen kräver `ADMIN_TOKEN`.
- `CLAUDE.md` rad 15 — repotabellen beskrev kärnan som "Python-paket, CLI, HTTP-API"; HTTP-ytan bor i `backend/`.

Grenen är skapad från `main` (458390d). Inget `agent-docs/github/`-underlag finns i repot, så projektstatussteget hoppades över. Inga `--commit`/`--PR`-flaggor angavs — arbetet ligger ocommittat på grenen `issue/17-kom-ikapp-klartex-014`.
