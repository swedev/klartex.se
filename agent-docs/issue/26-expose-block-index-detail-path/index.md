# Issue #26: Expose the block index as a structured detail.path on validation errors

**Baserad på:** main

## Sammanfattning

`POST /api/render` skickar i dag kärnans blockvalideringsfel vidare som en ren sträng (`detail.type = "input_error"`, `detail.message = "Invalid 'text' block at body[1]: …"`), medan `jsonschema.ValidationError`-fallet redan har ett strukturerat `detail.path`. Planen lägger till en liten hjälpfunktion i `backend/src/klartex_se/render.py` som matchar de tre exakta felformerna från kärnans `_validate_blocks()` och exponerar blockpositionen — plus positionen inne i blocket från `__cause__.absolute_path` — som `detail.path` i samma listform (`["body", 1, "items", 0, "text"]`). `type` förblir `input_error`; `path` läggs bara till när ett block kan pekas ut. Tester körs mot den riktiga kärnan (pinnad `klartex==0.15.0`) så att ett formatbyte i kärnan upptäcks vid nästa pin-bump. README får ett avsnitt om felkontraktet.

## Triageringsstatus

| Fält | Värde |
|------|-------|
| **Redo att arbeta** | Ja |
| **Risk** | Låg |
| **Säker för junior** | Ja |

## Plangranskning

**Status:** Granskad
**Granskad:** 2026-08-30
**Feedback:** Codex bekräftade angreppssättet (inga blockerare, kärnans beteende matchar planen). Rättat: #15 är en samordningsrisk (ändrar `/render`-dependencyn, tester och README) snarare än konsument; saknad/ogiltig `body` går redan `validation_error`-vägen; #14-branchen ändrar bara `app/`. Tillagt: uppdatera även `test_render_validation_error_returns_structured_400`, ett kombinerat nästlat-block-plus-fält-testfall, README-notis om FastAPI:s 422 och `path == []`, samt att OpenAPI-prosan är otestad dokumentation.

## Relaterade filer

- [plan.md](plan.md) — Fullständig implementationsplan
- [progress.md](progress.md) — Implementationsframsteg
- [research.md](research.md) — Forskningsresultat (om finns)

## Relaterade issues

- #17 — Kom ikapp klartex 0.14.0 (stängd); behovet noterades där, och dess test pinnar dagens strängbeteende
- #14 — MVP fas 1, Tiptap end-to-end; konsument av `detail.path` för blockmarkering
- #15 — Auth/API_TOKEN; rör `/render`-dependencyn i `render.py`, tester och README — samordningsrisk, den som landar sist rebasar
