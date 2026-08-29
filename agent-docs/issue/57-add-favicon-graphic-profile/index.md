# Issue #57: Add the favicon from the graphic profile

**Baserad på:** main

## Sammanfattning

Landningssidan saknar favicon. Profilen (§01) anger symbolen ensam vid 16 px; issue #57 bestämmer utförandet: symbolen i negativ på en Marin 900-platta. Planen bygger `assets/favicon.svg` som en 64 × 64-kvadrat i `#071A43` med `klartex-symbol-v2-reverse.svg` nästlad orörd (egen viewBox, symbolhöjd 40 ≈ 0,63 av plattan — friytan översatt från den synliga luften i profilens eget friyteexempel), länkar den från `<head>` i `index.html` med `rel="icon" type="image/svg+xml"`, och bevisar med en rsync-dry-run att deployens befintliga `assets/*.svg`-filter redan tar med filen. `design/README.md` och `CLAUDE.md` uppdateras med en rad var. Enbart SVG — ingen ICO/PNG-fallback (Safari ≤ 18.7 och iOS Web Clips får då ingen ikon; känt och accepterat). Återanvändningen i webbappen noteras för #14.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Låg |
| **Säker för junior** | Ja |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-29
**Feedback:** Codex bekräftade det nästlade `<svg>`-upplägget (userSpaceOnUse-gradienter och clipPath förblir korrekta) och stegordningen. Tillämpat: Safari-påståendet korrigerat (SVG-favicon stöds i Safari 26+, inte ≤ 18.7/Web Clips); proveniensen skärpt (profilen anger symbolen ensam vid 16 px, issuet anger negativ på platta); path-jämförelsen ersatt med diff av hela det kopierade delträdet; explicit XML-deklarations- och `preserveAspectRatio`-instruktion; `sizes="any"` på länken; HTTP som acceptanskriterium med cache-buster och Network-kontroll, `file://` borttaget; 16 px-rendering i webbläsare som hård grind; villkorad samordning med #14 och "kontrollera öppna PR:er igen före implementation".

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #55 — Restyle the landing page to the graphic profile (stängt via PR #56; favicon lämnades medvetet utanför)
- #14 — MVP fas 1 — minimal Tiptap end-to-end (öppet; webbappen ska dela samma ikonfil)
- #58 — Self-host the landing page fonts (öppet; rör samma `<head>` i `index.html`, andra rader)
