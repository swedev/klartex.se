# Plan: Issue #58 — Self-host the landing page fonts instead of loading them from Google Fonts

## Mål

Landningssidan `index.html` laddar Source Serif 4, Source Sans 3 och JetBrains Mono via en Google Fonts-`<link>`. Varje besökares webbläsare kontaktar därmed `fonts.googleapis.com` och `fonts.gstatic.com`, vilket skickar IP-adressen till Google — sidans enda tredjepartsanrop, och ett med GDPR-bäring (LG München I, 3 O 17493/20, januari 2022). De tre familjerna ska i stället ligga som woff2 i `assets/fonts/`, laddas med `@font-face` + `font-display: swap`, och följa med i deployens rsync-filter. Inget i sidans utseende ska ändras; sidan ska efter ändringen inte göra något anrop utanför `klartex.se`.

**Klart-kriterium:** issuet stängs när PR:en mergas till `main` — samma konvention som #55 (PR #56) och #57 (PR #59). Produktionssajten får ändringen först vid nästa `v*`-tagg, och en sådan **kräver en versionsbump**: deployen vägrar taggar som inte matchar `backend/pyproject.toml` (`0.4.0`, och `v0.4.0` finns redan — taggad 11:29 den 29 aug, *före* alla tre landningssidecommits #45/#55/#57). En patchrelease `0.4.1` (bump i `backend/pyproject.toml` + `backend/src/klartex_se/__init__.py`, tagg) är alltså vad som tar #45, #55, #57 **och** detta issue till produktion. Den bumpen ligger utanför PR:en (se Triagemässiga noteringar) men ska anges i PR-bodyn så att den inte glöms; tills den görs ligger Google Fonts-laddningen kvar i produktion.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget för implementation och merge. För *produktion* krävs en patchrelease (`v0.4.1`) — ett driftsteg, inte ett issue. |
| **Blockerar** | Inget hårt. #14 (webbappen) ska återanvända filerna i `assets/fonts/` i stället för att ladda typsnitten igen — noteras för #14, inget beroende åt något håll. |
| **Relaterade issues** | #55 (stängt via PR #56; restylingen som medvetet valde Google Fonts-`<link>` för att förbli byggfri — detta issue är den uppföljning planen för #55 pekade ut), #57 (stängt via PR #59; favicon-raden ligger i samma `<head>`, redan mergad), #14 (öppet; webbappen ska peka på samma filer) |
| **Omfattning** | 3 nya binärer + 3 licensfiler + 2 nya textfiler i `assets/fonts/`; 4 befintliga filer ändras (`index.html`, `.github/workflows/deploy.yml`, `CLAUDE.md`, `design/README.md`); plus planmappen `agent-docs/issue/58-…/` (`plan.md`, `index.md`, `progress.md`) som committas med PR:en enligt repots mönster |
| **Risk** | Låg — sidan har fallback-stackar, ingen backend- eller infra-ändring, och licensfrågan (Reserved Font Name) är hanterad i planen (Designbeslut 2) |
| **Komplexitet** | Låg–Medel (typsnittsbygget är det enda icke-triviala; det görs en gång och är skriptat) |
| **Säker för junior** | Ja, med byggskriptet och mätprotokollet i fas 4 framför sig |
| **Konfliktrisk** | Låg — inga öppna PR:er i repot vid planeringen (`gh pr list` 2026-08-29). Den enda andra öppna planen med ett öppet issue är #20 (`backend/`, `infra/`), som inte rör någon av filerna här. #14 kommer att ändra `deploy.yml` (bygga och synka `app/dist`) — rsync-raden här är en egen rad i landningssidans steg, så en eventuell merge-konflikt är trivial. Kontrollera `gh pr list` igen strax före implementation. |

### Triagemässiga noteringar

- **Issue-metadata** (hämtat 2026-08-29 via `gh issue view 58 --json …`): öppet, inga labels, ingen assignee, inga kommentarer, `projectItems: []` (inte i något GitHub-projekt) och `milestone: null`. Ingen projektkonfiguration finns i repot (`agent-docs/github/` saknas), och eftersom issuet inte ligger i något projekt finns inga projektfält (status, release, sprint) att läsa. Ingen branch-justering mot release-typ görs; planen utgår från `main`.
- Inga explicita blockerare i issuet. "Deferred from PR #56" är historik, inte ett beroende — PR #56 är mergad (`2a307d6`), liksom favicon-PR:en #59 (`63faac5`).
- **Release-vägen:** `infra/README.md` beskriver flödet (bumpa version → merga → tagga). Versionsbumpen görs **inte** i denna PR: den hör till releasen, inte till typsnitten, och #45/#55/#57 väntar på samma bump. Rekommendation till användaren: cut `v0.4.1` när denna PR är mergad, så att hela landningssideserien går ut i ett svep. *Proveniens: befintlig konvention i `infra/README.md` + #55/#57:s "produktion vid nästa tagg"; rekommendationen om tidpunkt är agentens.*
- Caddys `klartex.se`-vhost (`infra/Caddyfile`) är `root * /srv/site` + `file_server` **utan CSP** — ingen `font-src` att uppdatera. Go:s `net/http` sätter `font/woff2` på `.woff2` (innehållssniffningen känner igen `wOF2`-signaturen även om MIME-tabellen saknar ändelsen), `encode zstd gzip` matchar som standard även `font/*`, så woff2-svaren gzip/zstd-packas en gång till — verkningslöst (data är redan Brotli-packad) men ofarligt. Ingen infra-ändring behövs; att undanta fonter från `encode` eller sätta cache-headers hör till Designbeslut 6.
- **Vad Google faktiskt servar i dag** (kontrollerat 2026-08-29 med Chrome-UA mot exakt den `<link>` sidan har): ett *variabelt* woff2 per familj och subset, där alla begärda vikter (400/500/600/700) pekar på samma fil. Latin-subsetet: Source Serif 4 v4.004 (axlar `wght` 200–900, `opsz` 8–60; 122 kB), Source Sans 3 v3.052 (`wght` 200–900; 29 kB), JetBrains Mono v2.211 (`wght` 400–800; 31 kB). Unicode-range för latin: `U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD`.
- **Källfiler med samma version som Google servar** finns i `google/fonts` på GitHub (`ofl/sourceserif4/SourceSerif4[opsz,wght].ttf` 4.004, `ofl/sourcesans3/SourceSans3[wght].ttf` 3.052, `ofl/jetbrainsmono/JetBrainsMono[wght].ttf` 2.211, alla ohintade). Senaste commit som rör respektive katalog: `08dc85da6bca7ae308a6f1d38d0b137465646071` (sourceserif4), `914ec116571b1162d886aa402e715552221f0b77` (sourcesans3), `6e4b84c976cadb3c49a40fd9a1c203e4f7fcf2da` (jetbrainsmono). Adobes och JetBrains egna senaste releaser är *nyare* (Source Serif 4.005, JetBrains Mono 2.304) — att bygga från dem vore en glyfändring mot i dag; se Designbeslut 1.
- **Licens — Reserved Font Name (RFN).** Alla tre är SIL OFL 1.1. Båda Source-familjerna bär RFN **'Source'**: Source Sans 3 i `OFL.txt` och i fontens name-ID 0 (`© 2023 Adobe …, with Reserved Font Name 'Source'`); Source Serif 4 saknar RFN i google/fonts `OFL.txt` men deklarerar den i fontens egen name-ID 0 (`© 2014 - 2021 Adobe Systems Incorporated …, with Reserved Font Name 'Source'`) — planen behandlar båda som RFN-bärande. JetBrains Mono har **ingen** RFN (name-ID 7 noterar varumärke, vilket inte är OFL:s RFN-mekanism). SIL:s vägledning (openfontlicense.org, "Webfonts and Reserved Font Names") är entydig: pre-subsetting är en *Modified Version* och får inte använda RFN; enbart WOFF/WOFF2-inpackning av **oförändrad** fontdata får behålla namnet (OFL-FAQ 2.2). Google kan servera subsettade Source-fonter under originalnamnet därför att Adobe bidragit dem till Google Fonts — det överförs inte till oss. Konsekvens: de subsettade Source-derivaten måste döpas om (Designbeslut 2); JetBrains Mono behåller sitt namn. Uppmätt alternativ utan omdöpning — oförändrad data som lossless woff2: Source Serif 4 ≈ 427 kB, Source Sans 3 ≈ 170 kB (mot ≈ 82 / 29 kB subsettat).
- **Förprövning under planeringen** (i scratchpad, `fonttools` 4.63.0 + `brotli` 1.2.0): `varLib.instancer` med `wght=400:700` (opsz orörd) följt av `pyftsubset --flavor=woff2` med Googles latin-range ger Source Serif 4 ≈ 82 kB, Source Sans 3 ≈ 29 kB, JetBrains Mono ≈ 29 kB — totalt ≈ 140 kB, *mindre* än de ≈ 182 kB Google levererar i dag. Axlar, `å ä ö — ·` och licensposterna (name-ID 0/7/13/14) verifierades i utfilerna. Receptet i fas 1 är alltså bevisat körbart.
- Tecken utanför ASCII som sidan faktiskt använder (utanför `<style>`): `· Ö ä å ö —` (alla inom Googles latin-range) samt `≥` (U+2265, i "Python ≥ 3.12") som **inte** ingår i Googles latin-range och därför i dag renderas ur fallback-stacken. Så förblir det (Designbeslut 4).
- Profildokumentet `design/Klartex grafisk profil.dc.html` laddar också Google Fonts, men `design/` deployas inte och är inte en publik sida. Utanför scope.

## Angreppssätt

### Från Googles CSS till egna `@font-face`-regler

I dag beskriver Googles CSS tre familjer med en `@font-face` per vikt, alla mot samma variabla fil. Motsvarigheten med egna filer är **en `@font-face` per familj med viktintervall**. De två Source-derivaten bär nya namn (Designbeslut 2); JetBrains Mono heter som förut:

```css
@font-face {
  font-family: "Klartex Serif";
  font-style: normal;
  font-weight: 400 700;
  font-display: swap;
  src: url("assets/fonts/klartex-serif.woff2") format("woff2");
}
@font-face {
  font-family: "Klartex Sans";
  font-style: normal;
  font-weight: 400 700;
  font-display: swap;
  src: url("assets/fonts/klartex-sans.woff2") format("woff2");
}
@font-face {
  font-family: "JetBrains Mono";
  font-style: normal;
  font-weight: 400 700;
  font-display: swap;
  src: url("assets/fonts/jetbrains-mono.woff2") format("woff2");
}
```

och i `:root` byts familjenamnen i stackarna — `--serif: "Klartex Serif", Georgia, …` och `--sans: "Klartex Sans", -apple-system, …`; `--mono` oförändrad. Inga andra stilregler rörs.

- `format("woff2")` räcker (det är vad Google själva skriver); `format("woff2-variations")` är utfasat och `tech("variations")` är nyare än nödvändigt. Alla webbläsare som klarar woff2 klarar variabla fonter i den.
- Ingen `unicode-range`: med ett enda subset per familj fyller den ingen funktion (webbläsaren faller ändå tillbaka per glyf som saknas i cmap). Färre rader, samma beteende.
- Sidans befintliga `font-optical-sizing: none; font-variation-settings: 'opsz' 60` på `h1`/`h2` fortsätter fungera eftersom `opsz`-axeln behålls i serif-filen (verifieras i byggskriptet).
- De tre `<link>`-raderna (två `preconnect` + stylesheet) tas bort. Ingen `preload` läggs till (Designbeslut 7).
- Relativ sökväg (`assets/fonts/…`) som övriga tillgångar; fonter från samma origin behöver ingen `crossorigin`.

### Bygget av woff2-filerna

Källa: de variabla TTF-filerna i `google/fonts` vid pinnade commits (samma version som Google servar i dag). Bearbetning i tre steg med fontTools, allt i en tempkatalog; utfilerna kopieras till `assets/fonts/` **först efter** att kontrollen gått igenom:

1. `fonttools varLib.instancer <ttf> wght=400:700` — begränsar viktaxeln till profilens intervall (400/600/700 ligger i det; 500 som `<link>`:en också begär används inte av sidan och ingår inte i profilen). `opsz` på Source Serif 4 lämnas hel (8–60).
2. **Omdöpning av Source-derivaten** (Python med `fontTools.ttLib`): i **varje** post i `name`-tabellen utom ID 0, 7, 13 och 14 ersätts `Source Serif 4` → `Klartex Serif`, `SourceSerif4` → `KlartexSerif`, `Source Sans 3` → `Klartex Sans`, `SourceSans3` → `KlartexSans`. Det täcker inte bara ID 1/3/4/6/16 utan också de `fvar`/`STAT`-refererade posterna över 255 — serifen har t.ex. PostScript-instansnamn `SourceSerif4Roman-Regular` … `-Bold` (ID 349–352 i förprövningen) som `pyftsubset` behåller eftersom de refereras. ID 0 (copyright **med RFN-deklarationen**), 7 (varumärkesnot), 13 och 14 (licens) lämnas **ordagrant orörda** — OFL kräver att de följer med. Kontrollen efteråt: ingen post utanför 0/7/13/14 innehåller strängen `Source`. JetBrains Mono döps inte om.
3. `pyftsubset <ttf> --flavor=woff2 --unicodes=<Googles latin-range> --name-IDs=0,1,2,3,4,5,6,7,13,14,16,17 --notdef-outline` — latin-subset (exakt Googles range, inget tillägg); standarduppsättningen av layout-features (`kern`, `liga`, `calt`, `ccmp`, `locl`, `mark`, `mkmk`, …, de webbläsaren aktiverar utan `font-feature-settings`); copyright/varumärke/licens kvar i filen.

Skriptet `assets/fonts/build.sh` gör detta reproducerbart: skapar en venv i en tempkatalog med `fonttools==4.63.0` och `brotli==1.2.0` pinnade (båda påverkar utdata), hämtar TTF-filerna och `OFL.txt` från `raw.githubusercontent.com/google/fonts/<commit>/ofl/<familj>/…`, **verifierar SHA-256** på varje hämtad fil mot summor inskrivna i skriptet (fylls i vid första körningen), kör de tre stegen och avslutar med en Python-kontroll som **failar** om axlarna inte är `wght 400–700` (+ `opsz 8–60` för serifen), om något av `U+00E5 U+00E4 U+00F6 U+00D6 U+2014 U+00B7` saknas i cmap, om `U+2265` *finns* (subsetet ska vara exakt Googles), om name-ID 0/13/14 saknas, eller om ett Source-derivat fortfarande har strängen `Source` i någon name-post utanför 0/7/13/14. Utfilerna committas — landningssidan förblir byggfri; skriptet är verktyg för den som ska uppdatera typsnitten, inte ett byggsteg. Två körningar i rad ska ge byte-identiska filer (hård grind, se steg 6).

Filnamn i `assets/fonts/` (kebab-case som övriga assets): `klartex-serif.woff2`, `klartex-sans.woff2`, `jetbrains-mono.woff2`, licenserna `klartex-serif-OFL.txt` (Source Serif 4:s `OFL.txt`), `klartex-sans-OFL.txt` (Source Sans 3:s), `jetbrains-mono-OFL.txt`, samt `README.md` och `build.sh`.

### Deployen

Landningssidans rsync-filter i `.github/workflows/deploy.yml` listar explicit vad som följer med. Det utökas med katalogen och de två filtyperna:

```
--include='index.html' --include='llms.txt' \
--include='assets/' --include='assets/*.svg' \
--include='assets/fonts/' --include='assets/fonts/*.woff2' --include='assets/fonts/*-OFL.txt' \
--exclude='*'
```

`README.md` och `build.sh` matchar inget include och deployas inte. Bevisas med en seedad dry-run precis som i #55/#57.

### "Ingen visuell förändring" — hur det bevisas

Samma typsnittsversioner som Google servar + samma axlar + samma subset = samma glyfer och metrik. Det ska inte bara antas utan mätas objektivt: innan `index.html` rörs sparas elementhöjder och helsides-PNG:er av sidan som den ser ut i dag (Google Fonts laddade), och samma artefakter tas efter ändringen. Kravet är identiska höjder **och** noll skiljande pixlar i en pixeldiff (Pillow i scratchpad-venven) vid #55:s fyra viewports, plus att DevTools "Rendered Fonts" visar de nya filerna för representativa noder. Inga avsiktliga undantag.

## Steg

### Fas 0: Preflight

1. `gh pr list --state open` — inga öppna PR:er som rör `index.html` eller `deploy.yml`. Utgå från `main` med rent working tree *bortsett från* planmappen `agent-docs/issue/58-self-host-landing-page-fonts/` (ospårad tills PR:en; den committas i implementationsbranchen som repots övriga planmappar). Skapa branch `58-self-host-fonts` (eller motsvarande).
2. Verktyg: `python3` (≥ 3.10) och nätåtkomst till `raw.githubusercontent.com` för skriptet; Chrome med DevTools-MCP för fas 4; Pillow för pixeldiffen installeras i en scratchpad-venv (`pip install pillow`). `pyftsubset` finns i pyenv-shimmen men **utan** `brotli` — därför skapar byggskriptet sin egen venv i stället för att lita på maskinens Python.
3. Referensmätning **före** ändring (fas 4 behöver den). Starta `python3 -m http.server 8000` i repots rot. Nytt/privat Chrome-fönster (fonter cachas hårt), DevTools → Network med *Disable cache* och *Preserve log*. Vid 1280 och 360 px, efter `await document.fonts.ready`, spara till `<scratchpad>/58-baseline/`:
   - `fonts.json`: `[...document.fonts].map(f => [f.family, f.weight, f.status])`
   - `heights-<vp>.json`: `['h1', 'h2', 'main p', 'pre', '.templates-table', 'footer'].map(s => [...document.querySelectorAll(s)].map(e => Math.round(e.getBoundingClientRect().height * 100) / 100))`
   - `network.json`: listan över request-URL:er (via MCP `list_network_requests` eller Network-panelens export) — i dag ska den innehålla `fonts.googleapis.com` + `fonts.gstatic.com`
   - helsides-PNG vid 320/360/768/1280 px: `full-<vp>.png` (DevTools → *Capture full size screenshot*, eller MCP:ns `take_screenshot` med filväg)
   - Elements → Computed → *Rendered Fonts* för `h1`, första `main p` och första `pre code`: anteckna familj + "Network resource" (i dag Source Serif 4 / Source Sans 3 / JetBrains Mono).
   Det här är facit.

### Fas 1: Bygg typsnitten

4. Skapa `assets/fonts/build.sh` (bash, `set -Eeuo pipefail`), körbar från repots rot:
   - Konstanter överst: de tre commit-SHA:erna ovan, filnamn i `google/fonts`, SHA-256 per hämtad fil (sex värden: tre TTF + tre `OFL.txt`), `FONTTOOLS_VERSION=4.63.0`, `BROTLI_VERSION=1.2.0`, unicode-range (Googles latin, ordagrant), `WGHT=400:700`. Ett bootstrap-läge `build.sh --print-sums` hämtar filerna, skriver ut deras SHA-256 och avslutar **utan** att bygga — det är enda sättet att köra med tomma summor; i normalläge avbryter tomma eller avvikande summor.
   - `tmp=$(mktemp -d)` med `trap 'rm -rf "$tmp"' EXIT`; `python3 -m venv "$tmp/venv" && "$tmp/venv/bin/pip" -q install "fonttools==$FONTTOOLS_VERSION" "brotli==$BROTLI_VERSION"`.
   - `curl -fsSL` av TTF + `OFL.txt` per familj från `https://raw.githubusercontent.com/google/fonts/<sha>/ofl/<katalog>/<fil>` (hakparenteser i filnamnen URL-kodas som `%5B`/`%5D`) till `$tmp`, följt av `shasum -a 256 -c` mot de inskrivna summorna — avvikelse eller tom summa avbryter (utom i `--print-sums`).
   - `fonttools varLib.instancer -q -o "$tmp/<namn>.ttf" "<ttf>" wght=$WGHT` (serifen: bara `wght`; `opsz` lämnas orörd genom att inte nämnas).
   - Omdöpning (inline Python-heredoc) för de två Source-filerna enligt Angreppssätt steg 2.
   - `pyftsubset "$tmp/<namn>.ttf" --output-file="$tmp/<namn>.woff2" --flavor=woff2 --unicodes="$UNICODES" --name-IDs=0,1,2,3,4,5,6,7,13,14,16,17 --notdef-outline`.
   - Avslutande Python-kontroll (inline heredoc mot venv:ens python) som öppnar de tre woff2-filerna i `$tmp` med `fontTools.ttLib.TTFont` och asserterar axlar, cmap-tecken (inkl. att `U+2265` saknas), name-ID 0/13/14 och att `Source` inte förekommer i någon name-post utanför 0/7/13/14 hos derivaten; skriver ut filstorlek per fil. **Först därefter** `cp` av de tre woff2 och de tre `OFL.txt` (döpta enligt ovan) till `assets/fonts/`.
   - Filer att skapa: `assets/fonts/build.sh`
5. Kör `bash assets/fonts/build.sh --print-sums` för att få de sex summorna, skriv in dem i skriptet, kör sedan `bash assets/fonts/build.sh`. Förväntat: tre woff2 (≈ 82 / 29 / 29 kB), tre `*-OFL.txt`, kontrollen grön.
   - Filer att skapa: `assets/fonts/klartex-serif.woff2`, `assets/fonts/klartex-sans.woff2`, `assets/fonts/jetbrains-mono.woff2`, `assets/fonts/klartex-serif-OFL.txt`, `assets/fonts/klartex-sans-OFL.txt`, `assets/fonts/jetbrains-mono-OFL.txt`
6. Reproducerbarhet (hård grind): `shasum -a 256 assets/fonts/*.woff2 > <scratchpad>/build1.sha`, kör skriptet en gång till, `shasum -a 256 -c <scratchpad>/build1.sha` ska vara grönt. Diffar det trots pinnade versioner är något i skriptet icke-deterministiskt (t.ex. tidsstämpel i `head.modified` — sätt då `SOURCE_DATE_EPOCH` i skriptet) — åtgärda innan vidare, gå inte förbi.
7. Skriv `assets/fonts/README.md` (svenska, nu-state): vad filerna är (variabla woff2, latin-subset, `wght` 400–700, `opsz` 8–60 på serifen), varifrån (google/fonts vid pinnade commits, versioner 4.004 / 3.052 / 2.211), att `klartex-serif`/`klartex-sans` är *Modified Versions* av Source Serif 4 respektive Source Sans 3 under SIL OFL 1.1 och därför inte får bära namnet "Source" (RFN), att copyright/RFN-deklaration/licens ligger kvar i filernas name-tabell och i `*-OFL.txt`, hur man uppdaterar (bumpa SHA + summor i `build.sh`, kör, granska diff, verifiera enligt fas 4), samt att webbappen (#14) ska använda samma filer.
   - Filer att skapa: `assets/fonts/README.md`

### Fas 2: `index.html`

8. Ta bort de tre raderna `<link rel="preconnect" …>` × 2 och `<link href="https://fonts.googleapis.com/…" rel="stylesheet">`. Lägg de tre `@font-face`-blocken ovan **först** i `<style>`, före `:root`. Byt familjenamnet i `--serif` och `--sans` i `:root`. Ändra inget annat i stilbladet.
   - Filer att ändra: `index.html`
9. `grep -n -i 'googleapis\|gstatic\|fonts.g' index.html` ska ge noll träffar. `grep -c '@font-face' index.html` = 3. `grep -c 'Source S' index.html` = 0.

### Fas 3: Deployen

10. Utöka rsync-filtret i `.github/workflows/deploy.yml` (steget "Sync infra and landing page", andra rsync-anropet) med `--include='assets/fonts/' --include='assets/fonts/*.woff2' --include='assets/fonts/*-OFL.txt'` före `--exclude='*'`.
    - Filer att ändra: `.github/workflows/deploy.yml`
11. Seedad dry-run i scratchpad, som i #55/#57: skapa `<mål>/assets/fonts/stale.woff2` och `<mål>/design/sentinel.txt`, kör
    `rsync -avn --delete --include='index.html' --include='llms.txt' --include='assets/' --include='assets/*.svg' --include='assets/fonts/' --include='assets/fonts/*.woff2' --include='assets/fonts/*-OFL.txt' --exclude='*' ./ <mål>/`
    Förväntat: de tre woff2 + tre OFL-filer överförs, `assets/fonts/stale.woff2` raderas, `assets/fonts/README.md` och `build.sh` överförs **inte**, `design/sentinel.txt` rörs inte, inget ur `backend/`/`infra/`.

### Fas 4: Verifiering i webbläsare (hård grind)

12. Samma `http.server`, nytt/privat fönster, Network med *Disable cache* + *Preserve log*, rensa loggen och hård-navigera till `http://localhost:8000/`. Vid 1280 och 360 px, efter `await document.fonts.ready`, ta samma artefakter som i steg 3 till `<scratchpad>/58-after/`:
    - `fonts.json`: exakt tre poster, `status: "loaded"`, vikt `400 700`, familjer `Klartex Serif`, `Klartex Sans`, `JetBrains Mono`; `document.fonts.check('600 56px "Klartex Serif"')`, `('400 16px "Klartex Sans"')`, `('400 13px "JetBrains Mono"')` alla `true`.
    - `heights-<vp>.json` **identiska** med baseline (`diff`). Avvikelse = fel version/axel/subset; stanna och felsök (jämför woff2:ans name-ID 5 mot 4.004 / 3.052 / 2.211).
    - Pixeldiff per viewport (Pillow): `ImageChops.difference(Image.open(a).convert('RGB'), Image.open(b).convert('RGB')).getbbox()` ska vara `None` för 320/360/768/1280. Är den inte det: skriv ut bbox, beskär och titta — kravet är noll avvikande pixlar, och det finns inget avsiktligt undantag att skriva av.
    - *Rendered Fonts* för `h1`, `main p`, `pre code`: `Klartex Serif` / `Klartex Sans` / `JetBrains Mono`, alla "Network resource" (inte "Local file" — det skulle betyda att en lokalt installerad font tagit över).
    - `documentElement.scrollWidth === clientWidth` vid 320 och 360 px (#55:s check).
13. Nätverk: `network.json` efter full laddning — **varje** request-URL:s host ska vara `localhost` (tillåtelselista med exakt en post; inte bara "inget googleapis/gstatic"); tre `.woff2` med status 200 och `content-type: font/woff2` (Pythons `http.server` känner till ändelsen). Skriv ut listan i `progress.md`.
14. Fallback: blockera `*.woff2` i DevTools (eller döp om `assets/fonts/` tillfälligt) och ladda om — sidan renderas läsbar i Georgia / systemsans / SF Mono, ingen layoutkollaps, `swap` ger text direkt. Återställ.

### Fas 5: Dokumentation

15. `CLAUDE.md`, "Landningssidan idag": lägg till att `assets/fonts/` bär de tre typsnitten självhostade som woff2 (byggda med `assets/fonts/build.sh`, källa google/fonts; Source-derivaten omdöpta på grund av OFL:s RFN) och att sidan inte gör anrop utanför `klartex.se`. Behåll "ingen build, inga dependencies" — skriptet är underhållsverktyg, inte byggsteg. Skriv i nu-state.
16. `design/README.md`: en mening i `assets/`-stycket om `assets/fonts/` (självhostade woff2 av profilens tre familjer; `assets/fonts/README.md` är källan för hur de byggs och varför två av dem heter Klartex Serif/Sans). Nu-state.
    - Filer att ändra: `CLAUDE.md`, `design/README.md`

### Fas 6: PR och efter release

17. PR-body (engelska, en rad per stycke): vad som ändrats, bevisen från fas 3–4 (höjdparitet, pixeldiff = 0, nätverkslistan, dry-run), RFN-hanteringen, designbeslut 1/2/5/6/7 som öppna för invändning, att produktion kräver `v0.4.1`, `Closes #58`, `Refs #55, #14`.
18. Efter `v0.4.1` (utanför PR:en): `curl -sI https://klartex.se/assets/fonts/klartex-sans.woff2` → `200`, `content-type: font/woff2`; `https://klartex.se/` i ett privat fönster med Network (*Disable cache*, *Preserve log*): varje request-host är `klartex.se`, `[...document.fonts]` tre `loaded`. Samma slags driftkontroll som #55 steg 14 / #57 steg 8.

### Notering för #14 (ingen åtgärd här)

`app.klartex.se` har `Content-Security-Policy: default-src 'self' …` utan egen `font-src`, så typsnitten måste komma från appens eget origin. Webbappen ska därför **kopiera in** `assets/fonts/*.woff2` (+ `*-OFL.txt`) i sin bundle (Vite `public/fonts/` eller import via byggsteget) och deklarera samma tre `@font-face`-block med samma familjenamn — inte ladda från `klartex.se` (det hade krävt både `font-src https://klartex.se` i CSP:n och CORS-headers på landningssidans vhost) och inte ladda från Google. Skriv det som en punkt i #14 vid implementationen så ytorna delar samma filer.

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `assets/fonts/build.sh` | Skapa | Reproducerbart bygge: hämtar TTF + OFL från google/fonts vid pinnade commits med SHA-256-kontroll, instansierar `wght` 400–700, döper om Source-derivaten, subsettar till Googles latin-range, packar woff2, verifierar axlar/cmap/namn/licensposter, kopierar in först efter grön kontroll |
| `assets/fonts/klartex-serif.woff2` | Skapa | Modified Version av Source Serif 4 v4.004, variabel (`wght` 400–700, `opsz` 8–60), latin-subset, ≈ 82 kB |
| `assets/fonts/klartex-sans.woff2` | Skapa | Modified Version av Source Sans 3 v3.052, variabel (`wght` 400–700), latin-subset, ≈ 29 kB |
| `assets/fonts/jetbrains-mono.woff2` | Skapa | JetBrains Mono v2.211, variabel (`wght` 400–700), latin-subset, ≈ 29 kB |
| `assets/fonts/klartex-serif-OFL.txt`, `klartex-sans-OFL.txt`, `jetbrains-mono-OFL.txt` | Skapa | SIL OFL 1.1-licenstexterna (originalens `OFL.txt`, oförändrade) bredvid respektive typsnitt; deployas med |
| `assets/fonts/README.md` | Skapa | Proveniens, versioner, licens/RFN-resonemang, uppdateringsrutin, återanvändning i webbappen |
| `index.html` | Ändra | Google Fonts-`<link>` + två `preconnect` bort; tre `@font-face` med `font-weight: 400 700`, `font-display: swap` först i `<style>`; `--serif`/`--sans` pekar på de nya familjenamnen |
| `.github/workflows/deploy.yml` | Ändra | Landningssidans rsync-filter inkluderar `assets/fonts/`, `*.woff2` och `*-OFL.txt` |
| `CLAUDE.md` | Ändra | "Landningssidan idag": `assets/fonts/`, RFN-omdöpningen och att sidan inte anropar tredje part |
| `design/README.md` | Ändra | `assets/`-stycket nämner `assets/fonts/` |
| `agent-docs/issue/58-self-host-landing-page-fonts/progress.md` | Skapa | Implementationslogg med mätresultat (höjder, pixeldiff, nätverkslista) |

## Berörda kodområden

- `assets/fonts/` (ny katalog i repots rot)
- `index.html` (`<head>` och toppen av `<style>`, `:root`-stackarna)
- `.github/workflows/deploy.yml` (landningssidans rsync-filter)
- `CLAUDE.md`, `design/README.md` (dokumentation)

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Källa: google/fonts vid pinnade commits, inte Adobes/JetBrains senaste releaser
**Alternativ:** A) de variabla TTF-filerna i `google/fonts` (Source Serif 4.004, Source Sans 3.052, JetBrains Mono 2.211 — exakt de versioner Google servar sidan i dag) · B) upstream-releaser (`adobe-fonts/source-serif` 4.005R, `adobe-fonts/source-sans` 3.052R, `JetBrains/JetBrainsMono` v2.304)
**Beslut:** A.
**Motivering:** Issuets krav är "no visual change". A ger samma glyfer och metrik som i dag, vilket gör paritetsmätningen i fas 4 till ett skarpt test. B skulle byta version på två av tre familjer — små men verkliga glyf- och metrikändringar som inte hör till detta issue. Uppgradering är sedan en SHA-bump i `build.sh` med samma verifiering. *Proveniens: agentens bedömning, härledd ur issuets "no visual change" — öppen att ifrågasätta.*

### 2. OFL Reserved Font Name: Source-derivaten döps om till "Klartex Serif" / "Klartex Sans"; JetBrains Mono behåller namnet
**Alternativ:** A) subsetta + instansiera och döpa om derivaten (name-tabell + CSS-alias), copyright/RFN-deklaration/licens orörda i filen · B) servera **oförändrad** fontdata som lossless woff2 under originalnamnen (tillåtet enligt OFL-FAQ 2.2): Source Serif 4 ≈ 427 kB + Source Sans 3 ≈ 170 kB i stället för ≈ 82 + 29 kB · C) subsetta och ändå behålla namnen "Source Serif 4"/"Source Sans 3" · D) be Adobe om ett RFN-avtal
**Beslut:** A.
**Motivering:** C bryter mot OFL — pre-subsetting är en Modified Version och RFN 'Source' får då inte användas (SIL:s vägledning "Webfonts and Reserved Font Names"; RFN deklareras i Source Sans 3:s `OFL.txt` och i båda fonternas name-ID 0). B är licensrent men gör sidans typsnittsvikt ≈ 4,5× större än Google levererar i dag, tvärt emot syftet med att bara byta laddningsväg. D är rätt väg för en webfont-tjänst, inte för en landningssida. A är vad OFL är gjord för: derivatet får ett eget namn, bär originalets copyright/RFN-deklaration/licens (name-ID 0/7/13/14 orörda, `OFL.txt` bredvid, README förklarar), och renderar identiskt — namnet syns bara i DevTools. Namnvalet "Klartex Serif"/"Klartex Sans" följer att fonten är repots produktderivat; det är osynligt för besökare. *Proveniens: licenskravet är externt (OFL 1.1, villkor 3: Modified Versions får inte använda Reserved Font Names utan uttryckligt tillstånd); valet av A framför B, och namnen, är agentens bedömning — öppet att ifrågasätta. Vill användaren hellre ha B är ändringen: hoppa över instancer/subset/omdöpning för Source-filerna och packa dem som de är.*

### 3. Ett variabelt woff2 per familj med `wght` 400–700, inte statiska instanser per vikt
**Alternativ:** A) en variabel fil per familj, viktaxeln begränsad till 400–700 (`varLib.instancer`), `opsz` hel · B) en variabel fil per familj med hela viktaxeln (200–900) · C) statiska instanser: 400/600/700 för Source-familjerna, 400/700 för mono (7–8 filer; serifens `opsz` skulle då låsas per fil)
**Beslut:** A.
**Motivering:** Det är också vad Google gör (en variabel fil per familj). A ger tre filer, ≈ 140 kB totalt, och behåller `opsz` som issuet uttryckligen ber om; sidans `font-variation-settings: 'opsz' 60` på rubrikerna fortsätter fungera. B är ≈ 55 kB större för vikter varken profilen eller sidan använder. C bryter `opsz` (issuet säger "keep the opsz axis") och ger fler filer och `@font-face`-block att hålla i synk. *Proveniens: användarbeslut i issuet (opsz + viktlista); valet av variabel fil med begränsad axel är agentens bedömning.*

### 4. Subset: exakt Googles latin-range — `≥` förblir i fallback-stacken
**Alternativ:** A) exakt Googles latin-range (då renderas `≥` i "Python ≥ 3.12" ur fallback-stacken, precis som i dag) · B) Googles latin-range + `U+2265`, så att sidans enda tecken utanför rangen sätts i webbfonten · C) större subset (latin-ext) för framtida innehåll
**Beslut:** A.
**Motivering:** Issuets acceptanskriterium är "no visual change"; A är den enda varianten som gör pixeldiffen i fas 4 till ett rent noll-test utan undantag att resonera bort. B vore en (liten) förbättring, men det är en ändring av sidans utseende och därmed ett eget beslut — den kostar en rad i `build.sh` (`,U+2265` i `UNICODES`, plus att kontrollen vänds) om användaren vill ha den, gärna som eget litet issue. C bygger in gissningar om framtida text. *Proveniens: användarbeslut (issuets kriterium) tolkat strikt; B noteras som möjlig uppföljning.*

### 5. Licensfiler committas och deployas; name-ID 0/7/13/14 behålls i filerna
**Alternativ:** A) originalens `OFL.txt` bredvid varje typsnitt i `assets/fonts/`, med i rsync-filtret, och copyright/RFN/licensposterna kvar i woff2:ans name-tabell · B) bara name-tabellen · C) en gemensam `LICENSE`-fil i `assets/fonts/`
**Beslut:** A.
**Motivering:** OFL 1.1 kräver att licensen och copyright-noten (inklusive RFN-deklarationen) följer med Modified Versions när de distribueras; att servera woff2 till besökare är distribution. A uppfyller det på båda sätten till en kostnad av ≈ 13 kB text som bara hämtas av den som ber om den. Källfilerna är per familj (olika copyright-rader), därför en fil per familj, inte C. *Proveniens: licenskravet är externt; formen är agentens bedömning.*

### 6. Ingen Caddy-ändring (inga `Cache-Control`-headers) i detta issue
**Alternativ:** A) lämna `infra/Caddyfile` orörd — Caddy sätter `ETag`/`Last-Modified`, webbläsaren revaliderar heuristiskt · B) lägga till `header /assets/* Cache-Control "public, max-age=…"` på `klartex.se`-vhosten
**Beslut:** A.
**Motivering:** Issuet är en landningssideändring; B är en Caddyfile-ändring som ska granskas och preflightas (`caddy validate` i deployen) för en sida med ett anrop per besök — releaseflödet bygger om och startar om Caddy vid varje tagg ändå, så kostnaden är review-ytan, inte en extra omstart. Villkorliga anrop mot `ETag` är billiga och filerna byter sällan. Samma sak gäller att undanta `font/*` från `encode` (dubbelpackning av woff2 är verkningslös men ofarlig). Om typsnitten senare delas med appen eller trafiken växer är B ett eget litet issue. *Proveniens: agentens bedömning — öppen att ifrågasätta.*

### 7. Ingen `<link rel="preload">` för typsnitten
**Alternativ:** A) bara `@font-face` + `font-display: swap` · B) dessutom `preload` av sans + serif (kräver `crossorigin` även same-origin)
**Beslut:** A.
**Motivering:** I dag går laddningen via en extern CSS-fil och sedan fonterna — två rundresor mot tredje part. Med inline `@font-face` upptäcks fonterna redan vid första layouten, så FOUT-fönstret krymper utan `preload`. B är en optimering med egna avvägningar (preload av ≈ 110 kB innan first paint) som inte hör till "ta bort Google". *Proveniens: agentens bedömning.*

### 8. Byggskript i `assets/fonts/` som committas tillsammans med utfilerna
**Alternativ:** A) `assets/fonts/build.sh` + committade woff2 · B) bara dokumenterade kommandon i README + committade woff2 · C) bygga i CI
**Beslut:** A.
**Motivering:** A gör proveniensen (commit-SHA, checksummor, version, subset, axlar, omdöpning) till kod som kan köras om och granskas i diff, utan att landningssidan får ett byggsteg (utfilerna är incheckade; skriptet körs bara vid uppdatering). B tenderar att drifta från vad som faktiskt kördes. C bryter mot "ingen build" och principen att per-push-CI ska vara billig. Skriptet deployas inte (matchar inget include). *Proveniens: befintlig konvention ("ingen build, inga dependencies" i `CLAUDE.md`) + agentens bedömning om placeringen.*

## Verifieringschecklista

- [ ] `assets/fonts/build.sh` körs grönt från repots rot, verifierar SHA-256 på alla sex hämtade filer, och producerar de tre woff2 + tre OFL-filerna; inbyggd kontroll bekräftar `wght` 400–700 (+ `opsz` 8–60 på serifen), cmap med `å ä ö Ö — ·` men **utan** `≥`, name-ID 0/13/14, och att `Source` inte finns i någon name-post utanför 0/7/13/14 hos `klartex-serif`/`klartex-sans`
- [ ] Två körningar av skriptet ger byte-identiska woff2 (`shasum -a 256 -c`)
- [ ] woff2-filernas name-ID 5 är 4.004 / 3.052 / 2.211 (samma som Google servar); storlek i storleksordningen 82 / 29 / 29 kB
- [ ] `index.html`: noll träffar på `googleapis`/`gstatic`/`Source S`; tre `@font-face` med `font-weight: 400 700` och `font-display: swap`; `--serif`/`--sans` uppdaterade; inga andra stilregler ändrade
- [ ] `[...document.fonts]` = tre `loaded` (Klartex Serif, Klartex Sans, JetBrains Mono); `document.fonts.check(...)` `true` för 600/56 px serif, 400/16 px sans, 400/13 px mono
- [ ] Elementhöjder (`h1`, `h2`, `main p`, `pre`, `.templates-table`, `footer`) identiska före/efter vid 1280 och 360 px; pixeldiff av helsides-PNG vid 320/360/768/1280 px = `None` (noll avvikande pixlar); *Rendered Fonts* visar de nya familjerna som "Network resource"; ingen horisontell scroll vid 320/360 px
- [ ] Network (cache av, preserve log, hård navigering): varje request-host är `localhost`; tre `.woff2` → 200 `font/woff2`
- [ ] Fallback-stacken renderar sidan läsbar med `*.woff2` blockerade
- [ ] rsync-dry-run: de sex filerna i `assets/fonts/` överförs, `stale.woff2` raderas, `README.md`/`build.sh` överförs inte, `design/` orört
- [ ] `CLAUDE.md`, `design/README.md`, `assets/fonts/README.md` i nu-state; README förklarar RFN-omdöpningen
- [ ] Ingen ändring i `backend/`, `infra/`, `llms.txt`
- [ ] PR-body: `Closes #58`, `Refs #55, #14`; designbeslut 1/2/5/6/7 listade som öppna; anger att produktion kräver `v0.4.1`
- [ ] Efter `v0.4.1`: `https://klartex.se/assets/fonts/*.woff2` → 200 `font/woff2`; `https://klartex.se/` gör inga anrop utanför `klartex.se`
