# Issue #55: Restyle the landing page to the graphic profile

**Baserad på:** main

## Sammanfattning

Landningssidan `index.html` ska följa den grafiska profilen i `design/`: Papper/Marin/Klarblå-paletten, Source Serif 4 + Source Sans 3 + JetBrains Mono enligt profilens skala, lockupen i sidhuvudet och bladet på en marin yta. Sidan förblir byggfri (inline CSS, Google Fonts via `<link>`). Texten från PR #45 — som redan är mergad till `main` — behålls oförändrad. Refererade SVG-filer kopieras till `assets/` och läggs till i deployens rsync-filter.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Låg |
| **Säker för junior** | Ja |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-29
**Feedback:** Codex (två pass): friytan räknas nu ur profilens eget exempel, bladkompositionen refererar rätt förlaga, DOM/`.container`-struktur och CSS-reset/rytm är utskrivna, fokusram med tillräcklig kontrast på marin, responsiv tabell med linje över, seedad rsync-dry-run som bevisar `--delete`, explicit klart-kriterium (merge; produktion vid nästa tagg), och `CLAUDE.md`:s felaktiga "GitHub Pages" rättas.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #21 — Agent-facing site content: generate llms.txt from the API and lead with the API call (öppet; stängs inte av detta)
- #50 — Single origin: app.klartex.se (stängt; gav sidan dess API-adresser)
- #14 — MVP fas 1 (öppet; appens frontend delar profilen, inga gemensamma filer)
- PR #45 — mergad som `56be0cb`; samordningssteget i issuet är därmed avklarat
