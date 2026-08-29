# Issue #58: Self-host the landing page fonts instead of loading them from Google Fonts

**Baserad på:** main

## Sammanfattning

Landningssidan laddar Source Serif 4, Source Sans 3 och JetBrains Mono via Google Fonts — sidans enda tredjepartsanrop, som skickar besökarens IP till Google (GDPR-bäring). Planen bygger de tre familjerna som variabla woff2 i `assets/fonts/` från samma versioner Google servar i dag (google/fonts vid pinnade commits: 4.004 / 3.052 / 2.211), med `wght` begränsad till 400–700, `opsz` 8–60 bevarad på serifen och exakt Googles latin-subset; totalt ≈ 140 kB (mindre än de ≈ 182 kB Google levererar). Eftersom subsetting gör dem till Modified Versions under OFL och båda Source-familjerna bär Reserved Font Name "Source" döps derivaten om till Klartex Serif / Klartex Sans (copyright, RFN-deklaration och licens kvar i filerna, `OFL.txt` bredvid); JetBrains Mono saknar RFN och behåller namnet. Ett reproducerbart `assets/fonts/build.sh` (pinnad fontTools + brotli, SHA-256 på indata, inbyggd axel-/cmap-/namn-/licenskontroll, byte-identiska omkörningar) committas tillsammans med utfilerna. `index.html` byter `<link>`-raderna mot tre `@font-face` med `font-weight: 400 700` och `font-display: swap`; rsync-filtret i `deploy.yml` utökas med `assets/fonts/`. "Ingen visuell förändring" bevisas med identiska elementhöjder, pixeldiff = 0 vid #55:s viewports, DevTools *Rendered Fonts* och en nätverkslista där varje host är origin. Ingen infra- eller backend-ändring. Produktion kräver en patchrelease `v0.4.1` (deployen kräver tagg = `pyproject`-version, och `v0.4.0` ligger före alla landningssidecommits) — utanför PR:en, anges i PR-bodyn.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Låg |
| **Säker för junior** | Ja |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-29
**Feedback:** Två codex-pass. Tillämpat: OFL Reserved Font Name — subsettade Source-derivat får inte heta "Source", så de döps om till Klartex Serif/Sans i alla name-poster utom copyright/varumärke/licens (även `fvar`-instansnamn över 255), med lossless-alternativet uppmätt (≈ 427 + 170 kB); release-vägen gjord explicit (deployen kräver tagg = `pyproject`-version → `v0.4.1` behövs för produktion); `≥` (U+2265) tas **inte** in i subsetet — exakt Googles range, så pixeldiffen blir ett rent noll-test; reproducerbarhet skärpt (pinnad brotli, SHA-256 på indata med `--print-sums`-bootstrap, byte-identiska omkörningar som hård grind, bygge i tmp med kopiering efter grön kontroll); objektiv visuell verifiering (Pillow-pixeldiff, DevTools *Rendered Fonts*, nätverks-allowlist med cache av/preserve log); Caddy-påståendet om `encode` rättat (`font/*` matchas, dubbelpackning ofarlig); issue-metadata läst via `gh` (inte i projekt, ingen milestone) i stället för "okänt"; preflight-formulering om den ospårade planmappen och `progress.md` i scope. Ej tillämpat (medvetet): risknivån hålls på Låg eftersom licens- och release-frågorna nu är hanterade i planen.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #55 — Restyle the landing page to the graphic profile (stängt, PR #56) — valde Google Fonts-`<link>` för att förbli byggfri; detta är den utpekade uppföljningen
- #57 — Add the favicon from the graphic profile (stängt, PR #59) — rör samma `<head>`, redan mergad
- #14 — MVP fas 1 (webbappen) — ska kopiera in samma woff2-filer i sin bundle i stället för att ladda typsnitten igen (appens CSP är `default-src 'self'`)
