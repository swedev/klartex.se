# Framsteg: Issue #57 — Add the favicon from the graphic profile

**Påbörjad:** 2026-08-29
**Senast uppdaterad:** 2026-08-29
**Status:** Klar

## Genomförda steg

- [x] Fas 1, steg 1: `assets/favicon.svg` byggd — 64 × 64 Marin 900-platta med `klartex-symbol-v2-reverse.svg` nästlad orörd (`x="12" y="12" width="40" height="40"`, symbolens egen viewBox). `xmllint --noout` tyst, exakt en XML-deklaration, delträdet `<defs>` … sista `<path>` byte-identiskt med källan (diff tom). 2 931 byte.
- [x] Fas 1, steg 2: Renderad i Chrome vid 16/32/48/64/256 px och via `qlmanage` + `sips`-nedsampling. Vid 16 px går stapel, veck och band att skilja åt mot marinen; vid 32 px är formen entydigt symbolen; nästlade gradienter (`userSpaceOnUse`), `clipPath` och `<use>` renderas korrekt. 0,70-varianten jämförd — ingen läsbarhetsvinst, så 0,63 behålls (Designbeslut 1). Symbolen uppfattas centrerad; ingen optisk justering behövd.
- [x] Fas 2, steg 3: `<link rel="icon" type="image/svg+xml" sizes="any" href="assets/favicon.svg">` i `<head>`, direkt efter `theme-color`. Diffen i `index.html` är en rad.
- [x] Fas 2, steg 4: Kontrollerad över HTTP (`python3 -m http.server`, `?v=1`-cache-buster på testsidan). DevTools Network: `assets/favicon.svg` → `200`, `content-type: image/svg+xml`, `sec-fetch-dest: image`. Sidan i övrigt oförändrad.
- [x] Fas 3, steg 5: `design/README.md` — `assets/`-stycket beskriver `favicon.svg` som sammansättning och att den ska byggas om när symbolfilen ändras.
- [x] Fas 3, steg 6: `CLAUDE.md`, "Landningssidan idag" — `assets/` täcker även `favicon.svg`.
- [x] Fas 4, steg 7: rsync-dry-run med deployens filter listar `assets/favicon.svg` bland de 8 överförda sökvägarna, tillsammans med `index.html`, `llms.txt` och de tre befintliga SVG-filerna. Inget ur `design/`, `backend/`, `infra/`. `deploy.yml` orörd.

## Pågående arbete

Inget. Implementationen ligger på `issue/57-add-favicon-graphic-profile`.

## Anteckningar

- Fas 5 (steg 8) ligger utanför PR:en: efter nästa `v*`-tagg ska `curl -sI https://klartex.se/assets/favicon.svg` ge `200` och `image/svg+xml`.
- Noteringen för #14 kvarstår: webbappen ska hämta `assets/favicon.svg`, inte rita en egen ikon.
- Designbeslut 2 (enbart SVG, ingen ICO/PNG/`apple-touch-icon`) tillämpat som planerat.
