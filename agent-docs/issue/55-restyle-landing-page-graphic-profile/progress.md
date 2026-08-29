# Framsteg: Issue #55 — Restyle the landing page to the graphic profile

**Påbörjad:** 2026-08-29
**Senast uppdaterad:** 2026-08-29
**Status:** Klar

## Genomförda steg

- [x] Fas 1, steg 1: Kopiera lockup reverse och bladen till `assets/` (`cmp` mot `design/` OK)
- [x] Fas 2, steg 2: `<head>` — preconnect, Google Fonts, theme-color
- [x] Fas 2, steg 3: DOM med `header.hero` / `main` / `footer` och `.container`
- [x] Fas 2, steg 4: Mall-tabellen med `<thead>`/`<tbody>`/`scope` i scrollwrapper
- [x] Fas 3, steg 5: Nytt stilblock på profilens färg- och typsnittsroller
- [x] Fas 4, steg 6: Hero-bandet med negativ lockup och friyta
- [x] Fas 4, steg 7: Bladparet i motsatta hörn, dolt under 640 px
- [x] Fas 5, steg 8: rsync-filtret i `deploy.yml` inkluderar `assets/`
- [x] Fas 5, steg 9: Seedad rsync-dry-run som bevisar filtret och `--delete`
- [x] Fas 6, steg 10: `CLAUDE.md` — "Landningssidan idag" i nu-state
- [x] Fas 6, steg 11: `design/README.md` — notis om `assets/`-kopiorna
- [x] Fas 7, steg 12–13: Lokal granskning och checklista mot profildokumentet

## Verifiering

- Textinnehållet är ordagrant oförändrat; enda skillnaden i renderad text är att ordet "Klartex" försvinner (lockupen bär det som bild).
- Hexvärden i stilblocket: `#071A43`, `#0A5FD8`, `#6B6A63`, `#E3E1DB`, `#FBFAF8` och `#FFFFFF`. Ingen Klarblå 500.
- 320 px och 360 px: `documentElement.scrollWidth === clientWidth` — sidan scrollar inte horisontellt. Tabellen (480 px) och kodblocken scrollar i sina egna wrappers.
- Lockupen 140 px på 360 px viewport (över profilens 120 px-minimum); bladen dolda under 640 px.
- `:focus-visible` på lockupen i heron ger vit ram; på Papper Klarblå 600.
- Fallback-stackarna (Georgia / systemsans / SF Mono) renderar sidan läsbar med typsnitten borttagna.
- Sidan öppnad som `file://` laddar alla tre SVG-filerna via de relativa sökvägarna.
- rsync-dry-run överför `index.html`, `llms.txt`, `assets/` och de tre SVG-filerna, raderar `assets/obsolete.svg` och rör inte `design/sentinel.txt`.
- `llms.txt` och `infra/Caddyfile` orörda.

## Anteckningar

- **Avvikelse från planen:** `--marin-700` deklareras inte i `:root`. Sidan har ingen skiljelinje på mörk yta, så variabeln hade blivit död kod. Övriga rollnamn finns som planerat.
- `<pre>`-blocken blir tangentbordsfokuserbara eftersom de scrollar; de får webbläsarens egen fokusram. Det är avsiktligt beteende från Chrome och lämnat som det är.
- Steg 14 (driftkontroll av `https://klartex.se/assets/*.svg`) ligger utanför PR:en och görs efter nästa `v*`-tagg.
