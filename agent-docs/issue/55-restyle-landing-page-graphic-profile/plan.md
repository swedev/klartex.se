# Plan: Issue #55 — Restyle the landing page to the graphic profile

## Mål

Ge landningssidan `index.html` den grafiska profilen som landade i `design/` (`e119a3a`): Papper som grund, Marin 900 som text, Klarblå 600 för länkar, Source Serif 4 / Source Sans 3 / JetBrains Mono enligt profilens skala, lockupen i sidhuvudet och (valfritt) bladet på en marin yta. Sidan förblir byggfri — inline CSS, typsnitt via `<link>` — och de tillgångar sidan refererar följer med i deployen. Texten från PR #45 (svenska, API-anropet först) behålls oförändrad: det här är en omformning av ramen, inte av innehållet.

**Klart-kriterium:** issuet stängs när PR:en mergas till `main`. Produktionssajten uppdateras först vid nästa `v*`-tagg (deployen kör bara på tagg, se noteringarna) — det är befintligt beteende och ingen del av detta issue. Vid nästa release ska dock kontrollen i Fas 7 steg 14 göras.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget |
| **Blockerar** | Inget (PLAN.md fas 6 "uppdaterad `index.html` som länkar till appen" bygger vidare på resultatet, men är inte beroende av det) |
| **Relaterade issues** | #21 (öppet; llms.txt-generering och innehållsordning — stängs **inte** av detta), #50 (stängt; gav sidan `app.klartex.se/api`-adresserna), #14 (öppet; appens frontend — samma profil; kommer senare att röra `deploy.yml` för `app/dist`, ingen öppen PR i dag) |
| **Omfattning** | 4 befintliga filer (`index.html`, `.github/workflows/deploy.yml`, `CLAUDE.md`, `design/README.md`) + 3 nya tillgångar i `assets/` |
| **Risk** | Låg |
| **Komplexitet** | Medel |
| **Säker för junior** | Ja, med profildokumentet öppet bredvid |
| **Konfliktrisk** | Låg — inga öppna PR:er rör `index.html`; planen för #17 (stängt) listade `index.html`/`llms.txt` men är levererad. #14:s framtida ändring av `deploy.yml` (bygga och synka `app/dist`) hamnar i ett annat steg än rsync-raden för landningssidan. |

### Triagemässiga noteringar

- **Samordningen med PR #45 är redan avgjord.** Issuet ber om att landa #45:s innehåll och omformningen som en förändring. PR #45 mergades till `main` 2026-08-29 som `56be0cb`, så `index.html` på `main` är redan den svenska sidan med API-anropet först. Planen utgår från den — inget rebase-arbete återstår, och issuets alternativ "fold #45's content into this work and close that PR" är inaktuellt.
- #21 förblir öppet: dess första punkt (generera `llms.txt` från API:t) är en egen mekanism. `llms.txt` rörs inte här.
- Landningssidans vhost i `infra/Caddyfile` har **ingen CSP**, så Google Fonts (`fonts.googleapis.com` + `fonts.gstatic.com`) fungerar utan infra-ändring. Appens vhost har strikt CSP, men den berör inte `klartex.se`.
- Deployen (`.github/workflows/deploy.yml`) kör bara på `v*`-tagg och rsync:ar landningssidan till `/home/klartex/site`, som Caddy monterar som `/srv/site`. Merge till `main` ändrar alltså inte produktionssajten; det gör nästa release. Se klart-kriteriet ovan.

## Angreppssätt

`index.html` är en enkel statisk sida (inline CSS, ingen build) som servas av Caddy ur `/srv/site`, dit `deploy.yml` rsync:ar **enbart** `index.html` och `llms.txt` (`--include`-filter med `--exclude='*'` och `--delete`). Allt sidan refererar externt måste alltså antingen läggas till i det filtret eller inlines.

Profilens auktoritet är `design/Klartex grafisk profil.dc.html`; `design/README.md` är snabbreferensen. De regler som styr just den här sidan:

- **Färgroller:** Papper `#FBFAF8` bakgrund; Marin 900 `#071A43` text och mörka ytor; Klarblå 600 `#0A5FD8` länkar, primärknapp, fokusram (enda blå som får bära text); Klarblå 500 `#0870FF` aldrig som text; Linje `#E3E1DB` alla ramar och avdelare, 1 px; Grå 600 `#6B6A63` sekundär text, metadata, sidfot; Marin 700 `#0B2B65` skiljelinjer på mörk yta. Tegel används inte på sidan (ingen fel/varning).
- **Typografi:** Source Serif 4 (400/600/700) rubriker; Source Sans 3 (400/600/700) brödtext och UI; JetBrains Mono (400/700) kod. Skalan: Display 56/1,05 serif 600 · Rubrik 1 32/1,15 serif 600 · Rubrik 2 21/1,3 serif 600 · Bröd 16/1,6 sans 400 · Liten 13/1,5 sans 400 · Kod 13/1,7 mono 400. Profildokumentet laddar typsnitten från Google Fonts med `Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700`, `Source+Sans+3:wght@400;500;600;700`, `JetBrains+Mono:wght@400;500;700`, `display=swap` — samma `<link>` återanvänds. Profildokumentets rubriker låser dessutom `font-variation-settings: 'opsz' 60` (Display-instansen, samma som lockupen är ritad ur) — gör detsamma på `h1`/`h2`.
- **Logotyp:** `klartex-lockup.svg` (4168 × 1043, konturer, inget typsnittsberoende) från 120 px bredd; `klartex-lockup-reverse.svg` på mörk bakgrund. **Friyta** = ordmärkets x-höjd över/höger/under, 1,55 × till vänster. Profildokumentets exempel visar friytan runt en 290 px bred lockup som padding `19.6px 31.7px 22.5px 49px` (topp/höger/botten/vänster), dvs. ~6,8 % / 10,9 % / 7,8 % / 16,9 % av lockupens bredd. Aldrig på accentblått, aldrig omsatt som text, aldrig nedtonad. Appvyerna sätter den negativa lockupen till 108 px i headern och `clamp(132px, 11vw, 200px)` på inloggningssidan.
- **Bladet (§06):** bara på Marin 900/700, i par i diagonalt motsatta hörn, alltid utfallande; armen (`klartex-blad-arm.svg`) uppe till vänster med lodrät gradient som börjar i bakgrundsfärgen nedtill, det omvända bladet (`klartex-blad-omvant.svg`) nere till höger; skalas fritt, roteras eller speglas aldrig; text får ligga i fältet men aldrig över en tät del — den negativa logotypen är undantaget. Profildokumentet har två kompositioner att utgå från: den **breda** (full bredd × 340 px hög): arm `left:-100px; top:10px; width:680px`, omvänt `right:-130px; bottom:-110px; width:680px`; och **visitkortet** (340 × 220 px): arm `left:-60px; top:-6px; width:360px`, omvänt `right:-70px; bottom:-60px; width:340px`, lockup reverse 168 px i mitten. Heron här är ett brett band, så den breda kompositionen är förebilden: bladens bredd ≈ 2 × bandets höjd.
- **Tabeller (§05):** linjer över och under, aldrig runt varje cell.
- **Ikoner:** Lucide, oförändrade. Sidan har inga ikoner i dag och behöver inga; regeln noteras för att ingen ska lägga till egna.

Sidans innehållsordning behålls: sidhuvud → tagline → curl-exemplet → "Två sätt att använda det" → "Mallar" → "Ta reda på vad som ska skickas" → "Vad som är öppet" → sidfot. Det enda som skiftar roll är rubriken: `<h1>Klartex</h1>` ersätts av lockupen (`<img alt="klartex">`), och taglinen — som redan bär budskapet — blir sidans `<h1>` i Display-graden. Ingen text skrivs om.

Layoutidé (agentens bedömning, se Designbeslut 2): ett **marint hero-band** upptill med den negativa lockupen och taglinen i vitt, bladparet utfallande i motsatta hörn; därunder Papper med resten av innehållet i en spalt om ~680 px. Sidfoten ligger på Papper i Grå 600 med en Linje-avdelare över. I dag bär `body` `max-width`/centrering/padding — det flyttas till en `.container`-klass så att heron kan gå full bredd och innehållet ändå ligga i samma spalt.

## Steg

### Fas 1: Tillgångar

1. Skapa `assets/` i repots rot med byte-identiska kopior av de filer sidan refererar:
   - `assets/klartex-lockup-reverse.svg` (sidhuvudet på marin yta)
   - `assets/klartex-blad-arm.svg`, `assets/klartex-blad-omvant.svg` (bladparet i hero-bandet)
   - Kopiera med `cp design/<fil> assets/<fil>`; verifiera med `cmp`. Ändra inget i filerna. Lägg inte in filer som ingen refererar (t.ex. `klartex-lockup.svg` — standardlockupen används inte med Designbeslut 2).

### Fas 2: Struktur i `index.html`

2. `<head>`:
   - Lägg till `preconnect` till `fonts.googleapis.com` och `fonts.gstatic.com` (`crossorigin`) och profildokumentets Google Fonts-`<link>` (exakt samma familjer, vikter och `opsz`-axel).
   - `<meta name="theme-color" content="#071A43">`.
   - Behåll `lang="sv"`, `<title>` och `<meta name="description">` oförändrade.
3. DOM med tydliga ansvar (texten flyttas oförändrad in i den nya strukturen):
   - `body` — ingen `max-width`, ingen centrering, ingen padding; bara bakgrund, färg och typsnitt.
   - `<header class="hero">` — full bredd, Marin 900; inuti en `<div class="container">` med `<a href="/" class="lockup"><img src="assets/klartex-lockup-reverse.svg" alt="klartex" width="4168" height="1043"></a>` och `<h1>` = taglinen. `width`/`height`-attributen bär proportionen (4168 : 1043) så layouten inte hoppar innan SVG:n laddats; den visade storleken sätts i CSS.
   - `<main class="container">` — allt från curl-exemplet till "Vad som är öppet".
   - `<footer class="container">` — länkraden och licensraden.
   - `.container`: `max-width: 680px; margin: 0 auto; padding: 0 1.5rem` (≈68 tecken i 16 px sans).
   - Relativa sökvägar (`assets/…`, inte `/assets/…`) så sidan går att öppna direkt från filsystemet vid granskning.
4. Mall-tabellen: lägg till `<thead>`/`<tbody>` och `scope="col"` på rubrikcellerna, och lägg tabellen i en `<div class="table-scroll">` med `overflow-x: auto` så långa beskrivningar på 320–360 px scrollar i stället för att kläms.
   - Filer att ändra: `index.html`

### Fas 3: Typografi och färg i `index.html`

5. Ersätt stilblocket. Definiera färg- och typsnittsroller som CSS-variabler i `:root` (namn efter profilens roller: `--papper`, `--marin-900`, `--marin-700`, `--klarbla-600`, `--linje`, `--gra-600`, `--serif`, `--sans`, `--mono`) och använd dem genomgående — inga lösa hexvärden i reglerna.
   - Reset och rytm: behåll `* { margin: 0; padding: 0; box-sizing: border-box }` från dagens stilblock; `main { padding: 2.5rem 0 }` så innehållet inte ligger dikt an mot heron; `p, li { margin-bottom: 0.75rem }`, `ul { padding-left: 1.5rem }`, `pre { margin: 1rem 0; padding: 1rem }`, `h2 { margin: 2.5rem 0 0.75rem }`.
   - `body`: Papper, Marin 900, Source Sans 3 16/1,6, fallback-stack `"Source Sans 3", -apple-system, "Segoe UI", sans-serif`.
   - `h1` (taglinen i heron): Source Serif 4 600, `clamp(32px, 6vw, 56px)`/1,05, `letter-spacing: -0.02em`, `font-variation-settings: 'opsz' 60`, vit på marin, `max-width: 20ch`.
   - `h2`: Source Serif 4 600, 21/1,3, samma `opsz`, Marin 900; `margin-top: 2.5rem` så sektionerna andas.
   - `pre`/`code`: JetBrains Mono 13/1,7; `pre` med 1 px Linje-ram på Papper, ingen fyllning (Designbeslut 4), `overflow-x: auto`; inline `code` utan bakgrund, samma mono.
   - `a`: Klarblå 600, understruken. Fokus: `a:focus-visible { outline: 2px solid var(--klarbla-600); outline-offset: 2px }` på Papper. På heron räcker inte Klarblå 600 (≈2,9:1 mot Marin 900, under 3:1) — `.hero a:focus-visible { outline-color: #FFFFFF }`.
   - `strong`: Source Sans 3 600.
   - Tabellen (§05: linjer över och under): 1 px Marin 900 över tabellen och under rubrikraden, 1 px Linje under övriga rader — inga vertikala linjer, ingen ram runt celler, ingen bakgrund på rader. Mallnamnen i `code` (mono).
   - `footer`: Liten 13/1,5, Grå 600, 1 px Linje över, `margin-top: 3rem`.
   - Filer att ändra: `index.html`

### Fas 4: Hero och blad

6. `.hero`: Marin 900, `padding: 3rem 0 3.5rem`, `position: relative; overflow: hidden`.
   - `.lockup img`: `display: block; width: clamp(140px, 14vw, 200px); height: auto` (över profilens 120 px-minimum även på 360 px-skärm).
   - **Friyta** ligger på `.lockup`-wrappern, inte på sidans spalt: `padding: 14px 22px 16px 34px` (profilens proportioner vid 200 px bredd — konservativt vid mindre bredder), `display: inline-block`. Ingen text, kant eller bild innanför. Bladen får gå in i friytan enligt §06 (logotypen i negativ tål bladet).
   - `<h1>` under lockupen med `margin-top: 1.5rem`, `position: relative; z-index: 1` så den ligger över bladen.
7. Bladparet, enligt §06 och den breda kompositionen:
   - `<img src="assets/klartex-blad-arm.svg" alt="" aria-hidden="true" class="blad blad-arm">` uppe till vänster och `<img src="assets/klartex-blad-omvant.svg" alt="" aria-hidden="true" class="blad blad-omvant">` nere till höger, båda `position: absolute; pointer-events: none; z-index: 0`.
   - Utgångsvärden att justera mot bandets faktiska höjd (~300 px på desktop): arm `left: -100px; top: 10px; width: min(680px, 60vw)`; omvänt `right: -130px; bottom: -110px; width: min(680px, 60vw)`. Rotera eller spegla aldrig; skala fritt.
   - Kontrollera visuellt att taglinen inte ligger över en tät del (armens täta ände uppe vid kanten, det omvända bladets nere till höger). Bladen ligger i hörnen, texten i spalten — men på smala skärmar möts de: under 640 px sätts `.blad { display: none }`. Heron utan blad är uttryckligen tillåten per issuet ("or not at all").
   - Filer att ändra: `index.html`

### Fas 5: Deploy

8. Utöka rsync-filtret i `.github/workflows/deploy.yml`, steget "Sync infra and landing page":
   - `--include='index.html' --include='llms.txt' --include='assets/' --include='assets/*.svg' --exclude='*'`
   - `--delete` ligger kvar och städar bort tillgångar som inte längre refereras.
   - Filer att ändra: `.github/workflows/deploy.yml`
9. Bevisa filtret lokalt med en dry-run mot en seedad målkatalog i scratchpad:
   - Skapa `<mål>/assets/obsolete.svg` och `<mål>/design/sentinel.txt` i förväg.
   - `rsync -avn --delete --include='index.html' --include='llms.txt' --include='assets/' --include='assets/*.svg' --exclude='*' ./ <mål>/`
   - Förväntat: överförda paths är exakt `index.html`, `llms.txt`, `assets/` och de tre SVG-filerna; `deleting assets/obsolete.svg` visas; `design/sentinel.txt` rörs inte (exkluderat är skyddat från `--delete`); inget från `design/`, `backend/`, `app/` överförs. `./` i utskriften är rsyncs egen rotrad och räknas inte.

### Fas 6: Dokumentation

10. `CLAUDE.md`, avsnittet "Landningssidan idag": skriv om i nu-state — sidan är `index.html` + `assets/` (kopior av logotyp- och bladfiler ur `design/`), synkas av `deploy.yml` till `/home/klartex/site` som Caddy servar som `klartex.se` ur `/srv/site`. Meningen "Driftas via GitHub Pages eller motsvarande" stämmer inte och ersätts. Ändringar görs fortfarande direkt i `index.html`/`llms.txt`, ingen build.
11. `design/README.md`: en rad om att `assets/` i repots rot bär kopior av de filer landningssidan refererar (lockup reverse, bladen) och att kopiorna ska uppdateras när någon av dem ändras här — `design/` är källan.
   - Filer att ändra: `CLAUDE.md`, `design/README.md`

### Fas 7: Verifiering

12. Lokal granskning: `python3 -m http.server` i repots rot (och öppna `index.html` direkt från filsystemet) och gå igenom sidan på 320 px, 360 px, 768 px och 1280 px bredd samt vid 200 % zoom. Ta skärmdumpar vid behov via Chrome DevTools. Testa med nätverket avstängt att fallback-stackarna håller.
13. Gå igenom checklistan nedan mot profildokumentet, inte mot minnet.
14. Efter nästa release (`v*`-tagg): kontrollera `https://klartex.se/`, `/assets/klartex-lockup-reverse.svg`, `/assets/klartex-blad-arm.svg`, `/assets/klartex-blad-omvant.svg` svarar 200 med `image/svg+xml`. Det är en driftkontroll utanför PR:en, men den enda punkt där deploy-ändringen faktiskt bevisas.

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `index.html` | Ändra | Ny `<head>` (Google Fonts, theme-color), `.container`-struktur med `header.hero`/`main`/`footer`, nytt stilblock på profilens roller, negativ lockup + bladpar i heron, tabell/pre/footer enligt profilen. Texten oförändrad. |
| `assets/klartex-lockup-reverse.svg` | Skapa (kopia) | Lockupen i sidhuvudet, byte-identisk med `design/` |
| `assets/klartex-blad-arm.svg` | Skapa (kopia) | Bladet, armen — uppe till vänster i heron |
| `assets/klartex-blad-omvant.svg` | Skapa (kopia) | Bladet, omvänt — nere till höger i heron |
| `.github/workflows/deploy.yml` | Ändra | rsync-filtret för landningssidan inkluderar `assets/` och dess SVG-filer |
| `CLAUDE.md` | Ändra | "Landningssidan idag": `assets/` som deployade kopior ur `design/`; korrekt driftbeskrivning (Caddy via `deploy.yml`, inte GitHub Pages) |
| `design/README.md` | Ändra | Notis om att `assets/` i roten är kopior som ska hållas i synk med `design/` |

## Berörda kodområden

- `index.html` (repots rot)
- `assets/` (ny katalog i repots rot)
- `.github/workflows/`
- `CLAUDE.md`, `design/README.md` (dokumentation)

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Tillgångar som kopior i `assets/` — inte inline, inte `design/` direkt
**Alternativ:** A) kopiera de refererade SVG-filerna till `assets/` i roten och lägga till katalogen i deployens rsync-filter · B) inline:a SVG-koden i `index.html` · C) referera `design/klartex-*.svg` direkt och rsync:a delar av `design/`
**Beslut:** A
**Motivering:** Issuet räknar uttryckligen med externa tillgångar som deployas med sidan. B håller deployen orörd men trycker in ~8 KB path-data i en sida som ska gå att läsa och redigera för hand, och bladens gradienter delar `id="g"` så de skulle behöva skrivas om — profilen säger "använd den som den är". C undviker dubbletter men publicerar en designkatalog under en URL som avslöjar repostrukturen och gör rsync-filtret krångligare. Dubbleringen i A är liten (tre filer, < 8 KB) och logotypen är låst; `cmp` mot `design/` i verifieringen fångar drift. *Proveniens: agentens bedömning — öppet att ifrågasätta.*

### 2. Marint hero-band med negativ lockup, resten på Papper
**Alternativ:** A) marint band upptill (lockup reverse + tagline + bladpar), Papper därunder · B) helt ljus sida med standardlockupen och inget blad · C) ljus sida med marin sidfot som bär bladet
**Beslut:** A
**Motivering:** Appvyerna i `design/` sätter den negativa lockupen på en marin header, så A ger landningssidan och appen samma första intryck — precis CLAUDE.md:s "samma produkt". Det ger också en tillåten yta för bladet utan att bryta §06. B är enklast men lämnar sidan utan den yta som binder den till appen. C lägger tyngden sist på sidan där få når. Issuet nämner både hero och sidfot som godkända ytor. *Proveniens: agentens bedömning — öppet att ifrågasätta; B är fallback om heron känns för tung för en sida som ska vara ett API-exempel.*

### 3. Google Fonts via `<link>`, inte självhostade woff2
**Alternativ:** A) Google Fonts-`<link>` (samma som profildokumentet) · B) självhostade woff2 i `assets/fonts/` med `@font-face`
**Beslut:** A — ett medvetet accepterat val, inte ett uppskjutet
**Motivering:** Issuet tillåter båda; A är byggfri, en rad, och identisk med profildokumentets laddning (inklusive `opsz`-axeln på Source Serif 4). B kräver att välja ut subset och vikter, committa ett par hundra KB binärer och lägga till dem i rsync-filtret. Avvägning att känna till: Google Fonts skickar besökarens IP till Google, vilket har GDPR-bäring (tyska domstolsbeslut 2022). Om det ska undvikas är B en fristående uppföljning som inte ändrar sidans utseende. *Proveniens: användarbeslut i issuet för att båda är tillåtna; valet mellan dem är agentens bedömning.*

### 4. Kodblock som Papper med Linje-ram — ingen fyllning
**Alternativ:** A) `pre` på Papper med 1 px Linje-ram · B) `pre` på Marin 900 med vit text · C) ljusgrå fyllning som i dag (`#f5f5f5`)
**Beslut:** A
**Motivering:** Paletten har ingen ljusgrå yta — Klarblå 100 är för markerad rad, inte för kod — så C introducerar en färg utanför profilen. B ger en andra marin yta per sida och fem mörka block som konkurrerar med heron. A följer profilens "alla ramar och avdelare 1 px Linje" och håller koden i Marin 900 på Papper med 16,3:1 kontrast. *Proveniens: agentens bedömning.*

### 5. Taglinen blir `<h1>`, lockupen ersätter texten "Klartex"
**Alternativ:** A) `<h1>` = taglinen, lockupen som `<img alt="klartex">` · B) behålla `<h1>Klartex</h1>` som visuellt dold text bredvid lockupen
**Beslut:** A
**Motivering:** Profilen förbjuder att ordmärket sätts om i text; ett `<h1>Klartex</h1>` i Source Serif bredvid lockupen vore precis det. `alt="klartex"` på bilden ger skärmläsare namnet, och taglinen är redan sidans budskap — den bär Display-graden bättre än ett ensamt ord. Ingen text ändras, bara elementroller. *Proveniens: agentens bedömning.*

### 6. Ingen favicon i det här issuet
**Alternativ:** A) lämna favicon utanför · B) skapa `assets/favicon.svg` (symbolen negativ på marin platta) och länka den
**Beslut:** A
**Motivering:** Profilen specificerar favicon ("symbolen ensam, alltid negativ på marinblå platta") men det kräver en ny härledd fil — en platta runt `klartex-symbol-v2-reverse.svg` — som inte finns i `design/`. Att skapa en ny logotypfil är ett designbeslut för `design/`, inte för landningssidan. Sidan har ingen favicon i dag, så inget bryts. Föreslås som eget litet issue som tillför filen i `design/` först. *Proveniens: agentens bedömning.*

## Verifieringschecklista

- [ ] Texten i `index.html` är ordagrant densamma som på `main` före ändringen (diff visar bara markup/CSS, `<h1>Klartex</h1>` → lockup + tagline som `<h1>`).
- [ ] Bakgrund `#FBFAF8`, brödtext `#071A43`, länkar `#0A5FD8`, avdelare `#E3E1DB`, sidfot `#6B6A63`; inga andra hexvärden i stilblocket än profilens (plus `#FFFFFF` för text och fokusram på marin).
- [ ] Ingen text i Klarblå 500 `#0870FF`.
- [ ] Rubriker i Source Serif 4 600 (`opsz` 60); brödtext Source Sans 3; `pre`/`code` JetBrains Mono. Storlekar: Display ≤ 56/1,05, H2 21/1,3, Bröd 16/1,6, Liten 13/1,5, Kod 13/1,7.
- [ ] Fallback-stackar renderar acceptabelt om Google Fonts blockeras (testa med nätverket avstängt).
- [ ] Lockupen är ≥ 120 px bred på 360 px viewport, proportionerna orörda, `alt="klartex"`, friytan (`.lockup`-padding) fri från text och kanter.
- [ ] Bladen ligger bara på Marin 900, i motsatta hörn, utfallande, ej roterade/speglade; taglinen ligger inte över en tät del; bladen är gömda under 640 px.
- [ ] Tabellen har bara horisontella linjer (Marin 900 över tabellen och under rubrikraden, Linje mellan raderna), `<thead>`/`<tbody>`/`scope="col"`, och scrollar i sin wrapper på 320 px utan att sidan scrollar horisontellt.
- [ ] `:focus-visible` syns på länkar både på Papper (Klarblå 600) och i heron (vit), utan layoutskift (`outline`, inte `border`).
- [ ] `assets/*.svg` är byte-identiska med motsvarande filer i `design/` (`cmp`).
- [ ] rsync-dry-run (steg 9) överför exakt `index.html`, `llms.txt`, `assets/` + tre SVG-filer, raderar `assets/obsolete.svg`, rör inte `design/sentinel.txt`.
- [ ] Sidan går att öppna direkt från filsystemet (relativa sökvägar) och via `python3 -m http.server`, på 320/360/768/1280 px och 200 % zoom.
- [ ] `llms.txt` orörd. `infra/Caddyfile` orörd.
- [ ] `CLAUDE.md` beskriver driften korrekt (Caddy via `deploy.yml`), inte "GitHub Pages".
- [ ] PR-bodyn: `Closes #55`, `Refs #21` — #21 stängs inte.
