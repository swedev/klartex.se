# Typsnitt

Landningssidans tre typsnitt ligger här som variabla woff2 och laddas från
`klartex.se` med `@font-face` i `index.html`. Sidan gör därmed inga anrop
utanför sitt eget origin.

| Fil | Innehåll | Storlek |
|-----|----------|---------|
| `klartex-serif.woff2` | Modified Version av Source Serif 4 4.004 — `wght` 200–900, `opsz` 8–60 | ≈ 118 kB |
| `klartex-sans.woff2` | Modified Version av Source Sans 3 3.052 — `wght` 200–900 | ≈ 28 kB |
| `jetbrains-mono.woff2` | JetBrains Mono 2.211 — `wght` 100–800 | ≈ 39 kB |

`index.html` deklarerar `font-weight: 400 700` i sina `@font-face`-regler, så
det är det intervallet sidan använder av viktaxeln.

Alla tre är subsettade till exakt det latin-subset Google Fonts levererar
sidan (`U+0000-00FF`, `U+0131`, `U+0152-0153`, `U+02BB-02BC`, `U+02C6`,
`U+02DA`, `U+02DC`, `U+0304`, `U+0308`, `U+0329`, `U+2000-206F`, `U+20AC`,
`U+2122`, `U+2191`, `U+2193`, `U+2212`, `U+2215`, `U+FEFF`, `U+FFFD`), så
glyfer och metrik är desamma som tidigare. `≥` i "Python ≥ 3.12" ligger
utanför subsetet och sätts ur fallback-stacken.

## Källa och bygge

`build.sh` bygger filerna från de variabla TTF-filerna i
[google/fonts](https://github.com/google/fonts), pinnade till en commit per
familj, med SHA-256-kontroll på varje hämtad fil. Bygget döper om
Source-derivaten och subsettar till woff2 (`fontTools.subset`) med pinnade
`fonttools` och `brotli`. Allt sker i en tempkatalog; filerna kopieras hit
först när skriptets kontroll av axlar, cmap, namn- och licensposter gått
igenom. Två körningar ger byte-identiska filer.

Variationsaxlarna lämnas orörda. Att smalna av viktaxeln med
`fontTools.varLib.instancer` löser om variationsmodellen och flyttar
teckenbredderna hundradels pixlar, vilket förskjuter varje tecken efter det
första — CSS begränsar vikterna i stället.

```
bash assets/fonts/build.sh
```

Utfilerna är incheckade — landningssidan har ingen build. Skriptet är
verktyget för den som ska uppdatera typsnitten:

1. Byt commit-SHA för familjen i `FAMILIES` i `build.sh`.
2. Kör `bash assets/fonts/build.sh --print-sums`, skriv in de nya
   SHA-256-summorna, kör skriptet skarpt.
3. Granska diffen och verifiera i webbläsare enligt planens fas 4
   (elementhöjder, pixeldiff, nätverkslista).

## Licens

Alla tre familjerna är licensierade under
[SIL Open Font License 1.1](https://openfontlicense.org). Licenstexten ligger
bredvid varje typsnitt (`*-OFL.txt`) och i filernas egen name-tabell
(name-ID 0, 7, 13 och 14).

Både Source Serif 4 och Source Sans 3 bär det reserverade typsnittsnamnet
(Reserved Font Name) **'Source'**. Att subsetta och instansiera gör filerna
till *Modified Versions* under licensen, och OFL 1.1 villkor 3 tillåter då
inte det reserverade namnet. Derivaten heter därför **Klartex Serif** och
**Klartex Sans** i alla name-poster utom copyright, varumärkesnot och
licens, som är ordagrant kvar från originalen. JetBrains Mono har inget
reserverat namn och behåller sitt.

## Webbappen

Webbappen (#14) ligger på `app.klartex.se` med `Content-Security-Policy:
default-src 'self'` och måste servera typsnitten från sitt eget origin.
Kopiera in samma `*.woff2` (och `*-OFL.txt`) i appens bundle och deklarera
samma tre `@font-face` med samma familjenamn — ladda dem inte från
`klartex.se`.
