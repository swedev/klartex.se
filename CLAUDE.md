# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vad detta repo är

`klartex.se` är hemmet för **klartex.se-webbappen** — en planerad WYSIWYG-webapp ovanpå klartex-kärnan. Idag innehåller repot bara en statisk landningssida (`index.html`, `llms.txt`) som annonserar Python-paketet. Webappen är inte byggd än.

Se `PLAN.md` för MVP-roadmapen.

## Relaterade repon

| Repo | Roll | Sökväg |
|------|------|--------|
| `swedev/klartex` | Kärnan: Python-paket och CLI. Lever på PyPI. | `../klartex/` |
| `projects/klartex` | Visionsdokument: arkitektur, WYSIWYG-design, composable templates. | `../projects/klartex/` |
| `swedev/klartex.se` | **Detta repo.** Landningssida idag → WYSIWYG-webapp framöver. | `.` |

Visionsdokumenten i `../projects/klartex/` är källan för designbeslut (`README.md`, `architecture.md`, `wysiwyg.md`, `composable-templates.md`, `filregister.md`). När de motsäger något i kärnans `README.md` vinner kärnan — visionsdokumenten beskriver vart vi ska, kärnan beskriver vad som finns.

## Kärnprincip: klartex.se är ett tunt frontend-lager

Kärnan (`../klartex/`) är ett **headless API**: in kommer JSON, ut kommer PDF. klartex.se ska inte duplicera den logiken. Webbappen ska:

1. Anropa `klartex-se-backend` (`backend/` i detta repo) för all PDF-rendering — aldrig själv producera LaTeX. `backend/` är policy-lagret: discovery, auth, sidmallsregistret och `/api`. Kompileringen sker i kärnans render-image `ghcr.io/swedev/klartex-render`, som `swedev/klartex` bygger och publicerar vid varje release och som detta repo konsumerar utan att bygga.
2. Använda kärnans schema-discovery (`/api/templates`, `/api/templates/<name>/schema`) som single source of truth för vilka block som finns och hur deras data ser ut.
3. Serialisera editor-state till samma JSON som CLI:t använder. Rundresan **klartex-JSON → editor-state → klartex-JSON** ska vara förlustfri (se `../projects/klartex/wysiwyg.md`).

Om webbappens behov tvingar fram förändringar i kärnan görs de i kärnan, inte parallellt här.

## Landningssidan idag

`index.html` är en enkel statisk sida (inline CSS, ingen build) tillsammans med `assets/`, som bär kopior av de logotyp- och bladfiler sidan refererar samt `favicon.svg`, symbolen i negativ på marin platta — `design/` är källan för dem. `assets/fonts/` bär profilens tre typsnitt självhostade som woff2, byggda från google/fonts med `assets/fonts/build.sh`; Source-derivaten heter Klartex Serif och Klartex Sans eftersom OFL:s reserverade typsnittsnamn inte får följa med i en subsettad version. Sidan gör därmed inga anrop utanför `klartex.se`. `llms.txt` följer [llms.txt-konventionen](https://llmstxt.org) och listar mallar, exempel och länkar för LLM-konsumenter.

Driften: `.github/workflows/deploy.yml` synkar `index.html`, `llms.txt` och `assets/` till `/home/klartex/site` på produktionsservern, som Caddy servar som `klartex.se` ur `/srv/site`. Deployen kör bara på `v*`-tagg.

Tills webappen byggs: ändringar i landningssidan görs direkt i `index.html`/`llms.txt` och commitas. Ingen build, inga dependencies.

## Språk

- **Användarvänd text** (UI-strängar, fel-meddelanden, README, CHANGELOG, planerings-dokument): svenska.
- **Kod, identifiers, kommentarer i kod, commit messages, docstrings**: engelska.
- **GitHub issues och pull requests** (titel och body): engelska.
- **Konversation med användaren** (Martin Söderholm): svenska — matcha språket i användarens senaste meddelande.

## Designkonvention

Klartex-paketet, landningssidan och webbappen ska kännas som **samma produkt**. Typografi, färger och tonläge ska kunna delas mellan landningssidan och appen. När appen växer fram bör landningssidan revideras för att matcha — inte tvärtom.

## Arbetsflöde

- Branch innan commit på `main`.
- För större förändringar: skapa GitHub-issue först, planera där, implementera mot issuen.
- Pull requests reviewas innan merge.
