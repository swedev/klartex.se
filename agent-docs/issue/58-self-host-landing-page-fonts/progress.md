# Framsteg: Issue #58 — Self-host the landing page fonts instead of loading them from Google Fonts

**Påbörjad:** 2026-08-29
**Senast uppdaterad:** 2026-08-29
**Status:** Klar

## Genomförda steg

- [x] Fas 0, steg 1–2: Inga öppna PR:er i repot. Branch `issue/58-self-host-landing-page-fonts` från `main`. `python3` 3.13.5, nätåtkomst till `raw.githubusercontent.com`, Chrome via DevTools-MCP och Pillow i scratchpad-venv.
- [x] Fas 0, steg 3: Referensmätning före ändring vid 320/360/768/1280 px (`python3 -m http.server`, isolerad Chrome-kontext). Nätverkslistan innehöll `fonts.googleapis.com` + `fonts.gstatic.com`; de tre gstatic-woff2:orna sparades också som facit för fil-jämförelser (122 168 / 28 792 / 31 340 byte, name-ID 5 = 4.004 / 3.052 / 2.211).
- [x] Fas 1, steg 4: `assets/fonts/build.sh` — pinnade commits, SHA-256 på alla sex hämtade filer, `--print-sums`-läge, venv med `fonttools==4.63.0` + `brotli==1.2.0`, omdöpning av Source-derivaten, `pyftsubset` med Googles latin-range, avslutande kontroll av axlar, cmap, hinting-tabeller, name-ID 0/5/13/14 och RFN-läckage. `SOURCE_DATE_EPOCH=0` gör körningarna deterministiska.
- [x] Fas 1, steg 5: Bygget kört. `klartex-serif.woff2` 117 636 B, `klartex-sans.woff2` 28 156 B, `jetbrains-mono.woff2` 38 596 B (totalt ≈ 184 kB mot Googles ≈ 182 kB i dag), plus de tre `*-OFL.txt`.
- [x] Fas 1, steg 6: Två körningar i rad ger byte-identiska woff2 (`shasum -a 256 -c` grön).
- [x] Fas 1, steg 7: `assets/fonts/README.md` — proveniens, versioner, licens/RFN, uppdateringsrutin, återanvändning i webbappen.
- [x] Fas 2, steg 8: `index.html` — de tre `<link>`-raderna borta, tre `@font-face` med `font-weight: 400 700` och `font-display: swap` först i `<style>`, `--serif`/`--sans` pekar på Klartex Serif/Klartex Sans.
- [x] Fas 2, steg 9: `grep` ger 0 träffar på `googleapis`/`gstatic`/`Source S`, 3 träffar på `@font-face`.
- [x] Fas 3, steg 10: rsync-filtret i `.github/workflows/deploy.yml` utökat med `assets/fonts/`, `*.woff2` och `*-OFL.txt`.
- [x] Fas 3, steg 11: Seedad dry-run överför de sex filerna, raderar `assets/fonts/stale.woff2`, tar inte med `README.md`/`build.sh` och rör inte `design/sentinel.txt`.
- [x] Fas 4, steg 12: Elementhöjder identiska med baseline vid 1280 och 360 px (`h1`, `h2`, `main p`, `pre`, `.templates-table`, `footer`). `[...document.fonts]` = tre poster, alla `loaded`, vikt `400 700`. `document.fonts.check` sant för 600/56 px serif, 400/16 px sans, 400/13 px mono. Ingen horisontell scroll vid 320 och 360 px. Helsides-PNG:erna har samma mått vid alla fyra viewports; pixeldiffen är inte noll (se Anteckningar).
- [x] Fas 4, steg 13: Nätverkslistan efter full laddning innehåller bara `127.0.0.1`: dokumentet, tre SVG:er, `favicon.svg` och de tre woff2 (200, `content-type: font/woff2`).
- [x] Fas 4, steg 14: Med typsnitten oåtkomliga renderas sidan i Georgia / systemsans / SF Mono, utan layoutkollaps och utan horisontell scroll; `h1` blir 353 px mot 352,78 px med webbtypsnitten.
- [x] Fas 5, steg 15–16: `CLAUDE.md` och `design/README.md` beskriver `assets/fonts/`, omdöpningen och att sidan inte anropar tredje part.

## Pågående arbete

Inget. Implementationen ligger på `issue/58-self-host-landing-page-fonts`.

## Anteckningar

### Viktaxeln lämnas hel — Designbeslut 3 föll på paritetsmätningen

Planens Designbeslut 3 smalnar av viktaxeln till 400–700 med
`fontTools.varLib.instancer`. Mätningen visar att det inte går ihop med
acceptanskriteriet: instancer löser om variationsmodellen, och teckenbredderna
hamnar hundradels pixlar fel. Uppmätt i webbläsaren, samma text vid 600/56 px:

| Fil | Bredd på "Skicka strukturerad" |
|-----|-------------------------------|
| Googles woff2 | 464,46685791015625 px |
| Orörd källa (google/fonts) | 464,46685791015625 px |
| Enbart subsettad | 464,46685791015625 px |
| Instansierad `wght=400:700` | 464,42468261718750 px |

Skillnaden förskjuter varje tecken efter det första och gav 77 818 avvikande
pixlar i helsidesdiffen. Utan instancer är rubriken pixelidentisk med Googles
rendering (mätt isolerat vid både 16 och 56 px: `getbbox()` = `None`).
Kostnaden är storleken: ≈ 184 kB i stället för ≈ 140 kB, alltså i praktiken
samma som de ≈ 182 kB Google levererar i dag. CSS:ens `font-weight: 400 700`
begränsar de vikter sidan kan använda.

### Kvarvarande pixeldiff: sans och mono

| Viewport | Mått före/efter | Avvikande pixlar | Max kanalavvikelse |
|----------|-----------------|------------------|--------------------|
| 320 px | 320 × 3271 = 320 × 3271 | 42 690 (4,1 %) | 163 |
| 360 px | 360 × 3143 = 360 × 3143 | 45 139 (4,0 %) | 163 |
| 768 px | 768 × 2694 = 768 × 2694 | 54 219 (2,6 %) | 164 |
| 1280 px | 1280 × 2766 = 1280 × 2766 | 54 219 (1,5 %) | 164 |

Serifen är pixelidentisk; avvikelserna ligger i kantutjämningen på sans- och
monotexten och syns inte i 1:1. Det som skickas är verifierat likvärdigt med
det Google levererar: bas-outlines, `gvar`-deltan, `avar`, `hmtx`/`HVAR`,
glyfernas bounding boxes, `gasp` och tabelluppsättningen är identiska glyf för
glyf, teckenbredderna är lika ned till sista biten (283,5892639160156 px för en
mening sans vid 16 px; 383,9996337890625 px för mono), och FreeType rastrerar
filerna till identiska bitmappar. Skillnaden uppstår alltså i Chromes egen
rastrering, inte i filerna — samma jämförelse mot enbart subsettade filer, mot
filer utan omdöpning och mot filer utan name-ID 16 ger exakt samma avvikelse.

Enda kända vägen till en ren nolla är att checka in Googles egna woff2-filer
från `fonts.gstatic.com` i stället för att bygga från google/fonts — det byter
ut planens Designbeslut 1, 2 och 8 och är inget den här implementationen gör.

### Övrigt

- Hinting: `pyftsubset` körs med `--no-hinting`. Källfilerna bär en
  `prep`-tabell som Google också tar bort; utan flaggan skiljer sig
  tabelluppsättningen från den Google levererar.
- Steg 17 (PR-body) och steg 18 (driftkontroll) ligger utanför branchen.
  Produktion kräver patchreleasen `v0.4.1`.
