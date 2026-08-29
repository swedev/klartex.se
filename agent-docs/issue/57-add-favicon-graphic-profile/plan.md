# Plan: Issue #57 — Add the favicon from the graphic profile

## Mål

Ge landningssidan en favicon. Profilen (§01, "Minsta storlek": *16 px symbol — favicon, app-ikon*) säger att symbolen används ensam under 120 px; issue #57 bestämmer utförandet: symbolen i negativ (`klartex-symbol-v2-reverse.svg`) centrerad på en kvadratisk Marin 900-platta (`#071A43`). Filen skapas som `assets/favicon.svg`, länkas från `index.html` och följer med i deployen via det befintliga rsync-filtret (`assets/*.svg`). Samma fil ska kunna återanvändas av webbappen när #14 landar, så att båda ytorna delar en ikon.

**Klart-kriterium:** issuet stängs när PR:en mergas till `main`. Produktionssajten får ikonen vid nästa `v*`-tagg (deployen kör bara på tagg — samma villkor som #55).

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget |
| **Blockerar** | Inget (#14 återanvänder filen men är inte beroende av att den finns först) |
| **Relaterade issues** | #55 (stängt via PR #56; restylingen som medvetet lämnade favicon utanför), #14 (öppet; webbappens frontend — ska dela ikonen), #58 (öppet; self-hostade typsnitt — rör samma `<head>` i `index.html` men andra rader) |
| **Omfattning** | 1 ny fil (`assets/favicon.svg`) + 3 befintliga (`index.html`, `design/README.md`, `CLAUDE.md`) |
| **Risk** | Låg |
| **Komplexitet** | Låg |
| **Säker för junior** | Ja, med profildokumentet och en 16/32 px-rendering framför sig |
| **Konfliktrisk** | Låg — inga öppna PR:er i repot vid planeringen (`gh pr list` 2026-08-29); kontrollera igen strax före implementation. Planen för #58 (ej skriven än) kommer att röra `<head>` (font-`<link>`-raderna); favicon-raden är en egen rad, så en eventuell konflikt är trivial. |

### Triagemässiga noteringar

- Inga explicita blockerare i issuet. "Deferred from PR #56" är historik, inte ett beroende — PR #56 är mergad (`2a307d6`).
- Ingen projektkonfiguration finns i repot (`agent-docs/github/` saknas), så inga projektfält har lästs och ingen branch-justering mot release-typ görs. Planen utgår från `main`.
- `.github/workflows/deploy.yml` synkar landningssidan med `--include='assets/' --include='assets/*.svg' --exclude='*'`. En ny `assets/favicon.svg` matchar filtret utan ändring — ingen deploy-ändring behövs, men det ska bevisas med en dry-run (Fas 4).
- Caddys `klartex.se`-vhost är `root * /srv/site` + `file_server` utan CSP; SVG servas som `image/svg+xml` av Caddys standard-MIME-tabell. `X-Content-Type-Options: nosniff` är satt, så typen måste vara rätt — det är den för `.svg`.
- Webbappen (`app/`) är ännu inte incheckad (bara `app/dist/` och `app/node_modules/` finns i `.gitignore`), så återanvändningen för #14 kan bara noteras, inte implementeras här. Villkorat: landar #14 *före* detta issue ska PR:en här även lägga ikonen i den incheckade appen; landar #57 först ska #14 hämta filen ur `assets/` (byggsteg eller kopia i `public/`), inte rita en egen.

## Angreppssätt

### Vad profilen faktiskt säger

- **§01 Minsta storlek:** under 120 px används symbolen ensam; 16 px symbol är fallet "favicon, app-ikon". Exemplet visar `klartex-symbol-v2.svg` (standard, på vitt). Issuet väljer den negativa varianten på marin platta — det är användarens beslut (issue #57), inte något planen väljer.
- **§01 Friyta** är definierad för *lockupen*: X = ordmärkets x-höjd, över/höger/under exakt X (mätt från versalhöjd, yttersta bläck respektive baslinje), 1,55 X till vänster. Profilen säger också uttryckligen att symbolens stapel och svans ligger utanför de referenserna och *går in i friytan*, "vilket är varför den synliga luften där är mindre än X".
- **Symbolfilen:** `klartex-symbol-v2-reverse.svg`, viewBox `511 165 569 646` (beskuren till bläck, 569 × 646, dvs. bredd = 0,88 × höjd), vit/ljus kropp med gradient, klarblå band, `gradientUnits="userSpaceOnUse"` och en `clipPath` — alla med koordinater i symbolens eget koordinatsystem. Ritinnehållet är identiskt med `klartex-symbol-reverse.svg`; bara rotens `width`/`height`/`viewBox` skiljer (den har luft runt om, 610 × 675).
- **Färg:** Marin 900 `#071A43` är "mörka ytor, symbolens kropp"; `theme-color` i `index.html` är redan `#071A43`, så flikens ikon och mobilens adressfält får samma färg.

### Att räkna om friytan till en ensam symbol

Ur profilens eget friyteexempel (lockupen 290 px bred med padding `19.6 / 31.7 / 22.5 / 49 px`) och lockupfilens metrik (`viewBox 26 -911 4167.68 1043`, symbolhöjd 1043 enheter, k:ets stapeltopp vid −738, baslinje vid 0) följer:

- X ≈ 455 enheter ≈ **0,44 × symbolhöjden** (höger padding 31,7 px är exakt X; vänster 49 px = 1,55 X; över/under stämmer med samma X mätt från −738 respektive 0).
- Den *synliga* luften runt symbolen i exemplet är mindre, eftersom stapeln sticker upp 173 enheter över referensen och svansen 132 enheter under baslinjen: ≈ 282 enheter över (**0,27 H**) och ≈ 323 under (**0,31 H**).

En ensam symbol har varken versalhöjd eller baslinje att mäta från, så "profilens friyta" måste översättas. Planen använder den synliga luften ur profilens exempel, ≈ 0,29 H runt om (Designbeslut 1). Med symbolhöjd H på en kvadrat S: S = H + 2 × 0,29 H ≈ 1,58 H → **H ≈ 0,63 S**. På 16 px är symbolen då ~10 px hög och ~9 px bred; på 32 px ~20 × 18 px. Med nominell X (0,44 H) hade symbolen blivit 0,53 S ≈ 8,5 px på 16 px — för litet för att bandet ska läsas.

### Filens konstruktion

`assets/favicon.svg` byggs som en yttre kvadrat med ett *nästlat* `<svg>` som bär symbolen orörd:

```svg
<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <title>Klartex</title>
  <rect width="64" height="64" fill="#071A43"/>
  <svg x="12" y="12" width="40" height="40" viewBox="511 165 569 646" preserveAspectRatio="xMidYMid meet">
    <!-- hela innehållet i design/klartex-symbol-v2-reverse.svg: defs + de fyra ritande elementen, oförändrat -->
  </svg>
</svg>
```

- Det nästlade `<svg>` får symbolens ursprungliga viewBox och `preserveAspectRatio="xMidYMid meet"` (utskrivet, fast det är default — centreringen är poängen) centrerar symbolen i 40 × 40-rutan: höjd 40 (0,625 S), bredd 35,2, 12 enheter luft över/under och 14,4 till vänster/höger. Geometrisk centrering; optisk justering prövas i verifieringen (symbolens massa sitter till vänster/nedtill).
- Symbolens `<defs>`, `<use>`, `<path>`-element och `id`-attribut kopieras oförändrade in i det nästlade `<svg>`. Källfilen har XML-deklarationen och rot-`<svg>` på samma första rad: kopiera **bara** från `<defs>` till och med sista `<path>` — inte källans XML-deklaration, rot-`<svg>`, `<title>`/`<desc>` eller sluttagg. Filen ska ha exakt en XML-deklaration, först i `favicon.svg`. Eftersom det nästlade `<svg>` skapar ett eget användarkoordinatsystem fungerar `gradientUnits="userSpaceOnUse"` och `clipPath` utan omräkning — path-datan förblir byte-identisk med källfilen, vilket är hela poängen med att inte göra om symbolen.
- Inga rundade hörn på plattan: issuet säger "square", och de plattformar som vill ha runda hörn (iOS, macOS Dock) maskar själva.
- Filen ska vara liten (~3,5 kB) och giltig XML (`xmllint --noout`).

### Länkningen

I `<head>` i `index.html`, efter `theme-color`:

```html
<link rel="icon" type="image/svg+xml" sizes="any" href="assets/favicon.svg">
```

`sizes="any"` markerar ikonen som skalbar (HTML-specifikationens värde för vektorikoner). Relativ sökväg som övriga tillgångar. Ingen `favicon.ico` och ingen PNG-fallback i detta issue (Designbeslut 2).

## Steg

### Fas 1: Bygg `assets/favicon.svg`

1. Skapa filen enligt skissen ovan.
   - Yttre `<svg viewBox="0 0 64 64" width="64" height="64">`, `<title>Klartex</title>`, `<rect>` i `#071A43`.
   - Nästlat `<svg x="12" y="12" width="40" height="40" viewBox="511 165 569 646" preserveAspectRatio="xMidYMid meet">` med **innehållet** i `design/klartex-symbol-v2-reverse.svg` (från `<defs>` till sista `<path>`, med källans indentering bevarad) inklistrat oförändrat. Skriv inte om path-data, gradienter eller id:n.
   - Verifiera att hela det kopierade delträdet är identiskt med källan — inte bara path-datan utan även gradienter, stops, clipPath och `<use>`: `diff <(sed -n '/<defs>/,/<\/svg>/p' design/klartex-symbol-v2-reverse.svg | sed '$d') <(sed -n '/<defs>/,/<\/svg>/p' assets/favicon.svg | sed '$d')` ska vara tomt (i favicon-filen stänger det nästlade `</svg>` först, så intervallet blir exakt delträdet).
   - `xmllint --noout assets/favicon.svg` ska vara tyst.
   - Filer att skapa: `assets/favicon.svg`

2. Rendera och granska vid 16 och 32 px (och 48/64 för säkerhets skull).
   - Avgörande test är webbläsarens: en liten testsida i scratchpad med `<img src="…/favicon.svg" width="16" height="16">`, `32` och `64` sida vid sida, öppnad i Chrome (DevTools-MCP kan ta skärmdumpen). Öppna även SVG-filen direkt i webbläsaren och kontrollera att de nästlade gradienterna, clipPath och `<use>` renderas. `qlmanage` (Quick Look) är kompletterande bevis, inte facit; `rsvg-convert`/ImageMagick saknas på maskinen.
   - `qlmanage` skalar aldrig upp: rendera från en kopia där yttre `width`/`height` satts till 512 (`sed 's/width="64" height="64"/width="512" height="512"/'`) och skala ner till 16 och 32 px med `sips -z 16 16` / `sips -z 32 32` — då får man samma nedsampling som webbläsarens flik gör.
   - Förprövning under planeringen (samma konstruktion, i scratchpad): på 512 px är kompositionen rätt — vit kropp, klarblått band, gradienter och clip intakta i det nästlade `<svg>`. På 32 px läses symbolen entydigt. På 16 px syns stapeln och det blå diagonala bandet, medan veckskuggan försvinner (väntat). Marginalen är alltså tillräcklig men inte stor; jämför gärna mot varianten 0,70 av plattan (`x="9.6" y="9.6" width="44.8" height="44.8"`) innan valet låses.
   - Kriterier: på 16 px ska stapeln, vecket och det blå bandet gå att skilja åt mot marinen; på 32 px ska formen vara entydigt symbolen. Symbolen ska uppfattas centrerad — om massan drar vänster/ned, flytta det nästlade `<svg>` med ≤ 1 enhet (`x`/`y`) hellre än att ändra storleken. Om symbolen inte läses på 16 px: se Designbeslut 1 för det fallback-utrymme som finns.
   - Jämför också med `theme-color`: plattan och adressfältet på mobil ska ha samma marin.

### Fas 2: Länka från `index.html`

3. Lägg till `<link rel="icon" type="image/svg+xml" href="assets/favicon.svg">` i `<head>`, direkt efter `<meta name="theme-color" …>` och före `preconnect`-raderna, så att ikonen ligger ihop med övriga sidmetadata och inte mitt i typsnittsblocket (som #58 kommer att röra).
   - Filer att ändra: `index.html`

4. Kontrollera över HTTP — det är acceptanskriteriet: `python3 -m http.server` i repots rot, öppna `http://localhost:8000/` i Chrome (och Firefox/Safari 26 om de finns på maskinen; anta inte att de gör det). Favicons cachas hårt: använd ett nytt/privat fönster eller `?v=1` på `href` vid omtestning. Ikonen ska synas i fliken och i DevTools → Network ska `assets/favicon.svg` svara `200` med `image/svg+xml`. `file://`-beteende för favicons varierar mellan webbläsare och är inte ett kriterium. Safari ≤ 18.7 visar ingen SVG-favicon (Designbeslut 2) — förväntat.

### Fas 3: Dokumentation

5. `design/README.md`: uppdatera stycket om `assets/` så det även nämner `favicon.svg` och att den — till skillnad från de tre kopiorna — är en *sammansättning* (symbolen i negativ på Marin 900-platta) som ska byggas om om `klartex-symbol-v2-reverse.svg` ändras. Skriv i nu-state, utan hänvisning till att den tillkommit.
6. `CLAUDE.md`, "Landningssidan idag": justera meningen om `assets/` så den täcker favicon ("kopior av de logotyp- och bladfiler sidan refererar samt `favicon.svg`, symbolen på marin platta"). En rad; ingen annan ändring.
   - Filer att ändra: `design/README.md`, `CLAUDE.md`

### Fas 4: Deploy-bevis

7. Dry-run av landningssidans rsync-filter mot en seedad målkatalog i scratchpad, exakt som i #55:
   - `rsync -avn --delete --include='index.html' --include='llms.txt' --include='assets/' --include='assets/*.svg' --exclude='*' ./ <mål>/`
   - Förväntat: `assets/favicon.svg` finns med bland de överförda sökvägarna, tillsammans med `index.html`, `llms.txt` och de tre befintliga SVG-filerna; inget ur `design/`, `backend/`, `infra/`.
   - Ingen ändring i `deploy.yml` — det här steget bevisar bara att filtret redan täcker den nya filen.

### Fas 5: Efter release (utanför PR:en)

8. Efter nästa `v*`-tagg: `curl -sI https://klartex.se/assets/favicon.svg` ska ge `200` och `content-type: image/svg+xml`; fliken på `https://klartex.se/` visar ikonen. Samma slags driftkontroll som #55 steg 14.

### Notering för #14 (ingen åtgärd här)

När webbappen checkas in ska den använda **samma fil**: `assets/favicon.svg` är källan; appen kopierar den till sin `public/` (Vite) eller motsvarande, och `app/index.html` länkar `/favicon.svg` med samma `type="image/svg+xml"`. Skriv det som en punkt i #14 vid implementationen, så att de två ytorna inte driver isär. Appens CSP (`img-src 'self'`) hindrar inte en ikon från samma origin.

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `assets/favicon.svg` | Skapa | Symbolen i negativ (oförändrad path-data ur `design/klartex-symbol-v2-reverse.svg`) nästlad på en 64 × 64 Marin 900-platta, symbolhöjd 40 (≈ 0,63 av sidan) |
| `index.html` | Ändra | `<link rel="icon" type="image/svg+xml" sizes="any" href="assets/favicon.svg">` i `<head>` |
| `design/README.md` | Ändra | `assets/`-stycket nämner `favicon.svg` som sammansättning av symbolen, med `design/` som källa |
| `CLAUDE.md` | Ändra | "Landningssidan idag": `assets/` innehåller även `favicon.svg` |

## Berörda kodområden

- `assets/` (repots rot)
- `index.html` (`<head>`)
- `design/README.md`, `CLAUDE.md` (dokumentation)

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Friytan på plattan: synlig luft ur profilens exempel (≈ 0,29 H), inte nominell X (0,44 H)
**Alternativ:** A) nominell X = 0,44 × symbolhöjden runt om → symbol ≈ 0,53 av plattan (≈ 8,5 px på 16 px) · B) den synliga luft profilens eget friyteexempel ger runt symbolen, ≈ 0,27–0,31 H → symbol ≈ 0,63 av plattan (≈ 10 px på 16 px) · C) branschpraxis för ikon-på-platta, ~0,7–0,8 av plattan, utan koppling till profilen
**Beslut:** B (symbolhöjd 40 på en 64-platta).
**Motivering:** Friytan i profilen är definierad mot ordmärkets referenslinjer, som en ensam symbol saknar; profilen säger själv att symbolens ytterdelar går in i friytan och att den synliga luften därför är mindre än X. B är den läsning som både följer profilen och uppfyller issuets krav "reads at 16 and 32 px". A ger en symbol som är för liten för att bandet ska skiljas från kroppen på 16 px; C släpper profilen helt. *Proveniens: agentens bedömning av hur "the profile's clearance" ska översättas — öppet att ifrågasätta. Om användaren vill ha nominell X är ändringen en rad (`x="15" y="15" width="34" height="34"`).*

### 2. Enbart SVG — ingen `favicon.ico`, ingen PNG, ingen `apple-touch-icon`
**Alternativ:** A) bara `assets/favicon.svg` enligt issuet · B) dessutom PNG/ICO-fallback för Safari och äldre klienter · C) dessutom `apple-touch-icon` (180 px PNG)
**Beslut:** A.
**Motivering:** Issuet ber om exakt en SVG och deployens filter täcker bara `assets/*.svg`; B/C kräver rasterfiler, en filterändring och ett byggsteg eller incheckade binärer. Täckningen är känd: SVG-favicon fungerar i aktuella Chrome, Firefox, Edge och Safari 26+ (caniuse, `link-icon-svg`), men inte i Safari ≤ 18.7, äldre klienter eller iOS-hemskärmens Web Clips (som vill ha `apple-touch-icon`). Där blir fliken ikonlös, och `/favicon.ico`-anrop svarar 404 i Caddys logg — båda ofarliga. Om det visar sig störa är det ett eget issue ("PNG/ICO-fallback för favicon"). *Proveniens: användarbeslut i omfattning (issue #57 nämner bara SVG); bedömningen att inte utvidga är agentens — öppen att ifrågasätta.*

### 3. Nästlat `<svg>` med symbolens egen viewBox, inte `<g transform>` eller omskriven path
**Alternativ:** A) nästlat `<svg x y width height viewBox="511 165 569 646">` med symbolens innehåll orört · B) `<g transform="translate(…) scale(…)">` runt innehållet · C) skriva om path-datan till plattans koordinater
**Beslut:** A.
**Motivering:** A behåller path-data, gradienter (`userSpaceOnUse`) och `clipPath` byte-identiska med källan och låter viewBox/`preserveAspectRatio` sköta centreringen — lätt att granska med `grep -o 'd="…"'`-jämförelsen. B fungerar också men kräver handräknade `translate`/`scale`-värden. C bryter mot profilens "använd den som den är" och gör framtida synk med `design/` omöjlig. *Proveniens: agentens bedömning — teknisk, låg insats att ändra.*

### 4. Plats för `<link rel="icon">`: efter `theme-color`, före typsnittsblocket
**Beslut:** raden läggs direkt efter `<meta name="theme-color">`.
**Motivering:** Håller ihop sidmetadata och lämnar typsnittsraderna (som #58 kommer att skriva om) sammanhängande, så att de två PR:erna inte konkurrerar om samma rader. *Proveniens: agentens bedömning — trivial.*

## Verifieringschecklista

- [ ] `assets/favicon.svg` finns, är giltig XML (`xmllint --noout`) med exakt en XML-deklaration, och det kopierade delträdet (`<defs>` … sista `<path>`) är identiskt med `design/klartex-symbol-v2-reverse.svg`
- [ ] Plattan är `#071A43` (Marin 900), kvadratisk, utan rundade hörn; symbolen är den negativa varianten (vit/ljus kropp, klarblå band)
- [ ] Renderad i webbläsare vid exakt 16 CSS-px: stapel, veck och band går att skilja åt (hård grind — kalkylen garanterar inte läsbarheten); vid 32 px: formen är entydigt symbolen; symbolen uppfattas centrerad
- [ ] `index.html` har `<link rel="icon" type="image/svg+xml" sizes="any" href="assets/favicon.svg">` i `<head>`; ikonen syns i fliken i Chrome via `http.server` (nytt/privat fönster), Network visar `200` + `image/svg+xml`
- [ ] Sidan i övrigt oförändrad (diff i `index.html` är en rad)
- [ ] rsync-dry-run visar `assets/favicon.svg` bland de överförda filerna utan ändring av `deploy.yml`
- [ ] `design/README.md` och `CLAUDE.md` nämner `favicon.svg` i nu-state
- [ ] PR-body: `Closes #57`, `Refs #55, #14`
- [ ] Efter nästa release: `https://klartex.se/assets/favicon.svg` → 200, `image/svg+xml`
