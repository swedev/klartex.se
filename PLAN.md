# MVP-plan för klartex.se

Mål: en webbapp som klarar **styrelsetestet** — en 65-årig styrelseledamot ska kunna öppna klartex.se, klicka "Kallelse till årsmöte", redigera texten direkt i sidan och ladda ner en PDF. Utan att se LaTeX, utan att öppna terminal, utan att prata med en chattbot.

Definitionen kommer från `../projects/klartex/wysiwyg.md`. Det här dokumentet bryter ner den i faser.

## Vad som står var

Dokumentet beskriver **formen** på arbetet: målet, faserna, de tvärgående besluten och varför de blev som de blev.

**Det som ska göras spåras i issues**, inte här. En checklista i det här dokumentet och en issue för samma sak driver isär, och den som läser vet inte vilken som gäller. Aktuellt läge för endpoints och drift står i [`infra/README.md`](infra/README.md) och [`backend/README.md`](backend/README.md), som ligger nära det de beskriver.

## Vad MVP:n *inte* är

För att hålla scopet ärligt — följande ligger **utanför** MVP:n och får komma efteråt:

- Filregister/dokumentarkiv (se `filregister.md` — explicit "inte nu").
- AI-assistans ("skriv utkast", "föreslå formulering"). Knappen kan finnas men funktionalitet är post-MVP.
- Open source-mallbibliotek bortom det som redan finns i kärnan.
- Mobilappen / offline-läge.
- Fakturering / betalningar.

MVP:n löser ett enda flöde: **välj mall → redigera → ladda ner PDF.**

## Faser

Faserna beskriver ordningen arbetet är tänkt att växa i, inte en tidsplan. Varje fas slutar i något körbart som kan demas, och ingen fas blockas av att den föregående är perfekt.

**Fas 0 — Fundament.** Klar. Kärnan körs som API, domänen är levande, stacken deployas från CI.

**Fas 1 — Minimal Tiptap end-to-end.** Bevisa hela kedjan Tiptap-editor → klartex-JSON → PDF med minsta möjliga block-set, utan formulär-mellansteg. Backend-delen är klar; frontenden är #14.

**Fas 2 — Custom block-typer.** Från fritt skrivande till klartex-block med eget JSON-schema. Block-formulär autogenereras från `/api/templates/_block/schema` — ingen hårdkodning per block. Rundresan Tiptap-state → klartex-JSON → Tiptap-state ska vara förlustfri mot kärnans fixtures; det är ett krav, inte en ambition.

**Fas 3 — Mallväljare + sidopanel.** Alla åtta mallar går att välja, var och en med en förifylld startstruktur. Mall-specifik metadata flyttas till en sidopanel genererad från mallens schema. Distinktionen mellan recipe-mallar och block engine hålls dold för användaren.

**Fas 4 — Branding-vy.** En organisation ska kunna sätta upp egen branding utan att skriva LaTeX: ladda upp logotyp, välja färger, fylla i namn och adress. Vyn genererar `.tex.jinja` + assets från formulärfälten och laddar upp dem till page-template-registret.

**Fas 5 — Konton + persistens.** Dokument överlever sessionen. Konton, organisationer och tokens byggs på parla (#19), inte på en egen inloggningslösning.

**Fas 6 — Polish + ship.** Onboarding, begripliga felmeddelanden på svenska, mobilanpassad landningssida och mallväljare, uppdaterad `index.html` som länkar till appen.

**Öppen fråga:** var konton hamnar relativt frontend-arbetet. Ordningen ovan lägger dem sist, men parla-spåret i #19 och den anonyma nivån i #23 rör samma yta och kan behöva komma tidigare. Det avgörs i issues, inte här.

## Tagna beslut

| Område | Val | Anteckning |
|--------|-----|-----------|
| **Hosting (API + frontend)** | Hetzner Cloud `cax11` (ARM, nbg1), Ubuntu 24.04, Docker Compose | Egen VM ger XeLaTeX out-of-the-box och billigare än Fly.io. Inte Cloudflare Pages — Caddy serverar redan statiska filer. Tre containrar: `caddy`, `backend`, `render`. Postgres (#19) blir den fjärde och ryms inte i minnesmarginalen utan att `render`s tak sänks eller värden storleksändras. |
| **Reverse proxy / TLS** | Caddy 2 med automatisk Let's Encrypt, byggd med rate limit-modulen | `Caddyfile` och `caddy/Dockerfile` i `infra/`. Tre vhosts. |
| **API-image** | Två images med egna versionsserier: `ghcr.io/swedev/klartex-se-backend:<version>` på `python:3.12-slim` och `ghcr.io/swedev/klartex-se-render:<version>` på basimagen `ghcr.io/swedev/klartex-base` med TeX Live + mscorefonts | Pinnade versioner i serverns `.env` (`BACKEND_VERSION`, `RENDER_VERSION`), aldrig `:latest` i prod. Produktkod ändras varje vecka, TeX-miljön några gånger om året — därför får en produktrelease aldrig flytta TeX-basen genom CI. Basen pinnas med tagg + digest i `render/Dockerfile` och bumpas i egen PR. Samma `klartex`-pin i båda tjänsterna; CI kontrollerar det. |
| **Bygge och deploy** | `v*`-tagg släpper `backend`, `render-v*` släpper `render`; båda kör `.github/workflows/deploy.yml`: test → bygge → smoke-test → publicering → utrullning | En push till `main` bygger ingenting; `ci.yml` kör testerna. Basimagen byggs och publiceras från `swedev/klartex`. Kärnbump rullas ut `render` först, `backend` sedan. |
| **Page-template-registry** | Filbaserad (`~klartex/klartex/page-templates/<namn>/`), base64-JSON-upload, gränser 1 MB template / 5 MB asset / 10 assets per namn | Writes kräver `API_TOKEN`. Per-org-auth kommer med #19. |
| **Repo-struktur** | Webbappen i `app/` i detta repo, landningssidan i roten | Bryts ut till eget repo om scopet växer. |
| **Domängräns** | `klartex.se` = landningssida, `app.klartex.se` = webbapp och API i ett ursprung: `backend/` i detta repo servas under `/api` | DNS hos Loopia, servern i Hetzner. Ett ursprung betyder ingen CORS. HTTP-ytan togs bort ur kärnan i `v0.11.0`. |
| **Frontend-stack** | React 19 + TypeScript + Vite 6 + Tailwind 4 + Radix Themes + Tiptap | Beslutad i #14, med `~/repos/openvera/frontend` som referens. |
| **Auth** | parla — device flow, scopes, rotation, revokering | Beslutad i #19. Clerk och Supabase Auth är avförda. Förutsätter Postgres och konton i backenden, som är samma issues första lager. |

### Varför Hetzner istället för Fly.io

- **Billigare.** €3.79/mån mot Fly.io ~€8–15 för motsvarande resurs.
- **EU-jurisdiktion.** Hetzner är tyskt; viktigt eftersom användardata (när konton kommer) faller under GDPR.
- **Färre rörliga delar.** Compose + Caddy är genomskinligare än Fly.io-machines.
- **Skalningsbehov saknas.** En `cax11` räcker långt på MVP-volymer.

Tradeoff: vi sköter OS-uppdateringar och backups själva. `unattended-upgrades` är aktiverat; backups behövs först när det finns data att förlora, alltså med fas 5.

## Lärdomar — TeX Live-imagen

Tre iterationer krävdes för att få TeX Live-imagen (idag basen för `render/`) att rendera klartex korrekt:

1. **`tabularx` → `tools`.** I TL2026 finns `tabularx` bara som del av `tools`-paketet. Gammal vana från TL ≤2024.
2. **`xelatex` inte på PATH.** `texlive/texlive`-basimagen sätter PATH via `/etc/profile` (login-shell), uvicorn körs non-interactive. Symlink `/usr/local/texlive/*/bin/<arch>` → `/usr/local/texlive-bin` + `ENV PATH=` fixar det.
3. **Cherry-picking är tröttsamt.** `tcolorbox` behöver `tikz` behöver `tikzfill` behöver … Bytet till `collection-latexextra` täcker alla transitivt och ger plats för framtida block.

Slutsats för framtida bygg: börja brett, inte smalt.

## Risker

| Risk | Mitigering |
|------|-----------|
| Tiptap ↔ klartex-JSON-rundresan blir lossy (inline-formatering, kapslade block) | Fas 2 har testsvit mot kärnans fixtures. Om förlustfrihet inte går: kör Tiptap som rendering-only och behåll JSON som källan — osmidigt UX, men det funkar. |
| XeLaTeX-fel som är obegripliga för slutanvändare | Fas 6 har felöversättning. Kärnan exponerar redan strukturerade valideringsfel — det räcker långt. |
| `/api/render` kör anropar-styrd LaTeX på en delad VM | Rate limit och resurstak finns (#20). Kompileringen kör i `render`-containern, som varken har hemligheter i miljön, volymer eller väg ut till internet — det den läser kan alltså inte lämna containern annat än i den returnerade PDF:en. Filläsning *inom* containern kvarstår: TeX Live 2026 tillämpar inte längre `openin_any`, så det skyddet måste bli process- eller OS-isolering i kärnan (`swedev/klartex#51`). `latex`-blocket kräver därför fortfarande en token: ett anonymt anrop som innehåller ett sådant block avvisas med `403`. |
| Branding-fragment-formatet ändras i kärnan | Branding-vyn ska bara generera fragment via kärnans schema, inte handgissa LaTeX. Ändras formatet, ändras genereringen — inte alla sparade brandings. |
| Dokumentlagring (fas 5) växer till en filregister-design som inte är genomtänkt | Håll persistent storage minimal: bara `document_id → klartex_json`. Filregister-skissen i `filregister.md` aktiveras senare. |

## Definition av "klar för MVP-launch"

Allt nedan måste vara sant innan vi annonserar publikt:

- [ ] Styrelsetestet går: en ny styrelseledamot lyckas, utan handledning, producera en kallelse på 10 minuter.
- [ ] Minst tre olika dokumenttyper (kallelse, protokoll, motion) renderar korrekt med en organisations egen branding.
- [ ] En andra organisation har satt upp sin branding via branding-vyn.
- [ ] Inga obegripliga LaTeX-felmeddelanden visas för slutanvändaren.
- [ ] `index.html` är uppdaterad så att den länkar till appen.
- [ ] CHANGELOG / release notes finns på en publik plats.
- [ ] Privacy / villkor-sida finns (även minimal — GDPR kräver det).
