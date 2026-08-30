# Framsteg: Issue #26 — Expose the block index as a structured detail.path on validation errors

**Påbörjad:** 2026-08-30
**Senast uppdaterad:** 2026-08-30
**Status:** Klar

## Genomförda steg

- [x] Fas 1, steg 1: `_block_error_path()` + `_BLOCK_ERROR_RE` i `render.py`
- [x] Fas 1, steg 2: `detail["path"]` sätts i `except ValueError`-grenen när en blockposition finns
- [x] Fas 1, steg 3: Modulens docstring och `responses[400]`-beskrivningen nämner `detail.path`
- [x] Fas 2, steg 1: `test_render_validation_error_returns_structured_400` asserterar `path`; det gamla `body[i]`-testet ersatt
- [x] Fas 2, steg 2: Endpoint-tester mot den riktiga kärnan (nästlade block, fält-path, okänd blocktyp, injektionsfall, `validation_error`-likformighet)
- [x] Fas 2, steg 3: Enhetstester direkt på `_block_error_path()`
- [x] Fas 3, steg 1: Avsnittet "Felsvar från `/api/render`" i `backend/README.md`

## Pågående arbete

Inget — alla faser genomförda.

## Anteckningar

- Kärnans felsträngar verifierade mot pinnad `klartex==0.15.0`: alla sju fall i planens tabell stämmer.
- `test_render_unknown_template_returns_400` fick `"path" not in detail`-asserten i stället för ett eget nytt test — samma request, inget behov av två.
- Verifieringschecklistan i `plan.md` genomgången: `pytest -rs` grönt (43 passed, inga skips), `/api/openapi.json` genereras och 400-beskrivningen nämner `detail.path`.
- Ingen versionsbump (designbeslut 6).
