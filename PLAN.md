# MVP-plan för klartex.se

Mål: en webbapp som klarar **Bob-testet** — en 65-årig styrelseledamot ska kunna öppna klartex.se, klicka "Kallelse till årsmöte", redigera texten direkt i sidan och ladda ner en PDF. Utan att se LaTeX, utan att öppna terminal, utan att prata med en chattbot.

Den definitionen kommer från `../projects/klartex/wysiwyg.md`. Detta dokument bryter ner den i körbara faser.

## Status (2026-05-12)

**Fas 0 klar.** **Fas 1 backend feature-komplett.** Stacken är live:

| Endpoint | Servar | Status |
|----------|--------|--------|
| `https://klartex.se` | Repots `index.html` (landningssidan) | ✅ |
| `https://www.klartex.se` | 301 → apex | ✅ |
| `https://app.klartex.se` | Vite-build (kommer senare i fas 1) | ⏳ 404 |
| `https://api.klartex.se/health` | `klartex_se` backend status | ✅ |
| `https://api.klartex.se/templates` | Mall-discovery (passthrough klartex library) | ✅ |
| `https://api.klartex.se/blocks` | Block-discovery | ✅ |
| `https://api.klartex.se/render` | JSON in, PDF ut (med `page_template`-namn eller inline-källa) | ✅ |
| `https://api.klartex.se/page-templates` | Named page-template registry (GET publikt, POST/DELETE admin) | ✅ |

**Arkitekturskifte 2026-05-11:** HTTP-yta flyttad från kärnan (`klartex serve` borttagen i `v0.11.0`) till `backend/` i detta repo — FastAPI som importerar `klartex` som library. Image: `ghcr.io/swedev/klartex-se-backend`.

**Page-template-registry 2026-05-12 (`backend 0.2.1`):** Branding (`.tex.jinja` + assets som logotyper, fonter) laddas upp en gång till `/page-templates/<namn>` med admin-token, lagras persistent i `/srv/klartex/page-templates`, och refereras sedan från `/render` via `page_template: "<namn>"`. Stand-alone-rendering med inline `page_template_source` finns kvar för engångsfall. Microsoft core fonts (Georgia, Arial, Times New Roman) ingår nu i backend-imagen. VKF:s branding ligger i registret som `vkf` och renderar end-to-end mot live-API:t.

Infrastruktur i `infra/` + `deploy/`; backend i `backend/`; runbook i [`infra/README.md`](infra/README.md) + [`backend/README.md`](backend/README.md).

## Vad MVP:n *inte* är

För att hålla scopet ärligt — följande ligger **utanför** MVP:n och får komma efteråt:

- Användarkonton, organisationer, samarbete (`wysiwyg.md` markerar dessa som TBD).
- Filregister/dokumentarkiv (se `filregister.md` — explicit "inte nu").
- AI-assistans ("skriv utkast", "föreslå formulering"). Knappen kan finnas men funktionalitet är post-MVP.
- Open source-mallbibliotek bortom det som redan finns i kärnan.
- Mobilappen / offline-läge.
- Fakturering / betalningar.

MVP:n löser ett enda flöde: **välj mall → redigera → ladda ner PDF.**

## Antaganden som styr scopet

1. **Auth.** MVP är open access — dokument lever i sessionen, ingen inloggning. Konton kommer i fas 5.
2. **First-users.** VKF är primär målgrupp under fas 1–3; deras branding hårdkodas. Branding-vyn (fas 4) öppnar för andra organisationer.
3. **Hosting.** Hetzner-VM med Docker Compose — Caddy serverar landningssida + frontend och proxar API:t (se "Tagna beslut" och `infra/`).
4. **Frontend-stack.** React + Vite + Tiptap (se "Tagna beslut").

## Faser

Varje fas slutar i något körbart som kan demas. Ingen fas blockas av "perfekt" föregående fas.

### Fas 0 — Fundament ✅ (klar 2026-05-11)

Mål: kärnan körs som API någonstans nåbart, hela domänen levande, smoke-test funkar.

- [x] **GHCR-publishing i kärnan.** Multi-arch (amd64 + arm64) image via release-trigger. Första publika versionen: `ghcr.io/swedev/klartex:0.10.1`.
- [x] **Hosting bestämd.** Hetzner Cloud `cax11` (ARM, nbg1), Ubuntu 24.04, ~€3.79/mån.
- [x] **Provisioneringsskript** (`infra/provision.sh` + `infra/cloud-init.yaml`) — idempotent, installerar Docker + ufw + fail2ban + klartex-user + systemd-unit.
- [x] **Stack live.** Docker Compose med Caddy + klartex-API, version-pinnad via `infra/.env`. Caddy hanterar TLS via Let's Encrypt, tre vhosts (`klartex.se`, `app.klartex.se`, `api.klartex.se`).
- [x] **DNS uppdaterat** i Loopia. Wildcard borttaget, explicita A-records för alla fyra hostnamn. Loopia-mail intakt (MX, SPF, DKIM, autodiscover).
- [x] **Deploy-flöde** (`deploy/deploy.sh`) — rsync compose+Caddyfile+statiska filer, `docker compose pull`, systemd-restart.
- [x] **Smoke-test grön.** `https://klartex.se` servar landningssidan, `https://api.klartex.se/templates` returnerar mall-listan.

**Inte** med i fas 0 (medvetet, kommer i fas 1):
- Frontend (Vite + React + Tiptap) — scaffoldas i `app/` när fas 1 börjar.
- CORS-modell — Caddy har en strikt `Access-Control-Allow-Origin: https://app.klartex.se`; om dev-flödet behöver annat tar vi det då.

### Fas 1 — Minimal Tiptap end-to-end (1 vecka)

Mål: Bevisa hela kedjan — Tiptap-editor → klartex-JSON → PDF — med minsta möjliga block-set. Inget kasserat formulär-mellansteg.

- [x] Backend `/render` live med `klartex==0.11.1`. VKF:s page-template finns i registret som `vkf` och renderar end-to-end.
- [ ] Frontend-scaffold i `app/` enligt referensstacken (`~/repos/openvera`), deployad till `app.klartex.se`.
- [ ] Tiptap monterad med basblock: `heading`, `paragraph` (med inline-formatering: fet, kursiv, länk), `bulletList`, `orderedList`. Inga custom-block än.
- [ ] Serialisering: Tiptap-state → klartex-JSON för basblock-setet. Inline-markup mappar mot kärnans `inline_markup.py`.
- [ ] Submit → POST till `https://api.klartex.se/render` med `page_template: "vkf"` → PDF nedladdas i webbläsaren.
- [ ] Felhantering: schema-valideringsfel från API:t mappas till begripliga svenska meddelanden.

**Acceptans:** Du kan öppna `app.klartex.se`, skriva en rubrik + några stycken + en punktlista i editorn, klicka "Ladda ner PDF" och få tillbaka en VKF-formaterad PDF (Georgia-rubriker, rätt marginaler). Ingen mallväljare, ingen sidopanel, inga klartex-specifika block — bara grundfundamentet.

Detta är den minsta Tiptap-baserade MVP:n. Allt nedan utökar block-täckning, mall-val och persistens.

### Fas 2 — Custom block-typer (1–2 veckor)

Mål: Utöka från "fritt skrivande" till klartex-specifika block med eget JSON-schema.

- [ ] Custom Tiptap-noder för klartex-block i priordning utifrån VKF-flödet:
  - `signatures` — enklast, finns i nästan alla dokumenttyper.
  - `agenda` — bevis-of-concept för block med egen JSON-struktur och rad-redigering.
  - `description_list`, `clause` — formulär per block.
  - Resten (`table`, `callout`, `quote`, `parties`, `name_roster`, `columns`, `page_break`, `latex` etc.) tas i prio efter VKF-användning.
- [ ] Block-formulär autogenereras från `/templates/_block/schema`. Fältlabels, typer, required, descriptions från schemat — ingen hårdkodning per block.
- [ ] "+"-meny för att infoga block. Drag-and-drop för att flytta. Delete för att ta bort.
- [ ] Rundresa-testsvit: Tiptap-state → klartex-JSON → Tiptap-state ska vara förlustfri mot fixtures i `../klartex/tests/fixtures/block_*.json`. Krav, inte nice-to-have.

**Acceptans:** Användaren skriver brödtext fritt, infogar `agenda` via "+"-meny, fyller i formuläret för det blocket, ser blocket i editorn (rimlig preview, inte slutgiltig PDF), klickar "Ladda ner PDF" och får tillbaka samma typografi som CLI-flödet.

### Fas 3 — Mallväljare + sidopanel (3–5 dagar)

Mål: Flera mallar ska gå att välja, mall-specifik metadata flyttas till sidopanel.

- [ ] Startsida med mallväljare: `kallelse`, `protokoll`, `motion`, `verksamhetsberättelse`, `revisionsberättelse`, `budget`, `valberedningens-förslag`, `styrelsens-yttrande`. Plus `faktura` om någon småföretagar-spår finns.
- [ ] Varje mall har en **starter** — en pre-fylld blockstruktur (heading + tom dagordning + signaturblock för kallelse, t.ex.). Spegla `tests/fixtures/block_*.json` som utgångsläge.
- [ ] Sidopanel till höger med metadata (datum, plats, justerare, mötestyp). Genererad från mallens schema. Toggleras av/på.
- [ ] Recipe-mallar (`protokoll`, `faktura`) renderas via recipe-pathen — block engine-mallar via `_block`. Webappen håller distinktionen dold för användaren.

**Acceptans:** Användaren kan välja vilken som helst av de listade dokumenttyperna, redigera ett färdigt utkast, fylla metadata i sidopanelen och få korrekt PDF.

### Fas 4 — Branding-vy (1 vecka)

Mål: Användare som inte är VKF kan sätta upp sin egen branding utan att skriva LaTeX.

- [ ] Sida `/branding` med formulär: ladda upp logotyp (PNG/SVG → konverteras till PDF via klartex), välj primär- och sekundärfärg, fyll i organisationsnamn och adress.
- [ ] Förhandsgranskning mot en testmall (samma som CLI-flödet kan göra idag).
- [ ] Sparad branding laddas upp via `POST /page-templates/<namn>` (registret finns redan, se status ovan) och refereras sen i `/render` med `page_template: "<namn>"`. Branding-vyn genererar `.tex.jinja` + assets från formulärfälten — den skriver inte LaTeX för hand.
- [ ] Lagring: page-template-registret på servern är källan. Lokal `localStorage`-kopia kan användas för utkast innan första uppladdning.

**Acceptans:** En ny användare kan på 5 minuter ladda upp logotyp, välja färger, och få samma typografi som VKF — fast med sin egen branding.

### Fas 5 — Konton + persistens (1–2 veckor)

Mål: Dokument överlever sessionen.

- [ ] Auth: magic link via e-post är enklast och passar målgruppen (en koloniförening är inte van vid OAuth-popups). Alt: Google login för de tekniskt vana.
- [ ] Datamodell: `user`, `organization` (med branding), `document` (med klartex-JSON). Användare kan tillhöra flera organisationer.
- [ ] "Mina dokument"-sida med listning per organisation.
- [ ] Autospar i editorn (var X sekunder eller vid blockändring).
- [ ] Versionering — minst en "ångra till föregående version"-funktion. Full versionshistorik kan vänta.

**Acceptans:** Användare loggar in, ser sina dokument från förra veckan, fortsätter redigera där hen slutade.

Frågor som behöver besvaras i detta steg är listade under "TBD" i `../projects/klartex/wysiwyg.md`.

### Fas 6 — Polish + ship (1 vecka)

- [ ] Onboarding-flöde för första-gångs-användare: tre skärmar som förklarar mallväljare → editor → branding.
- [ ] Felmeddelanden: alla LaTeX-kompileringsfel översätts till begripliga svenska meddelanden ("Fakturanumret saknas", inte "! Undefined control sequence").
- [ ] Mobilanpassning: editorn behöver inte vara fullt mobilstöd, men landningssida + mallväljare + nedladdning ska funka på telefon.
- [ ] Ersätt nuvarande `index.html` med en uppdaterad landningssida som länkar till webappen.
- [ ] Analytics (Plausible eller motsvarande, GDPR-vänlig) — bara så vi vet vad första-användarna gör.
- [ ] Klartext-domän: bekräfta att `klartex.se` pekar på rätt deploy. Eventuellt subdomain `app.klartex.se` för webappen.

**Acceptans:** En länk kan delas publikt utan skämsel.

## Tidslinje (grov uppskattning)

| Fas | Insats | Kalender (1 person, deltid) |
|-----|--------|----------------------------|
| 0 | 1–2 dagar | Vecka 1 |
| 1 | 1 vecka | Vecka 1 |
| 2 | 1–2 veckor | Vecka 2–4 |
| 3 | 3–5 dagar | Vecka 5 |
| 4 | 1 vecka | Vecka 6 |
| 5 | 1–2 veckor | Vecka 7–9 |
| 6 | 1 vecka | Vecka 10 |

**Tidigaste demo-bar MVP:** efter fas 1 (ca 1 vecka).
**Tidigaste publik MVP:** efter fas 3 + fas 6 light, alltså ca 6 veckor om man hoppar över branding och konton (hårdkoda VKF, ingen inloggning, dokument lever bara i sessionen).
**Full MVP enligt vision:** ca 10 veckor.

## Tagna beslut

| Område | Val | Anteckning |
|--------|-----|-----------|
| **Hosting (API + frontend)** | Hetzner Cloud `cax11` (ARM, nbg1), Ubuntu 24.04, Docker Compose | Egen VM ger XeLaTeX out-of-the-box och billigare än Fly.io. Inte Cloudflare Pages — vi har redan Caddy som kan servera statiska filer. |
| **Reverse proxy / TLS** | Caddy 2 med automatisk Let's Encrypt | `Caddyfile` i `infra/`. Tre vhosts. |
| **API-image** | `ghcr.io/swedev/klartex-se-backend:<version>` (multi-arch, `texlive/texlive:latest`-bas + mscorefonts) | Pinad version i `infra/.env`, aldrig `:latest` i prod. CI smoke-testar amd64-bygget innan multi-arch-push. |
| **Page-template-registry** | Filbaserad (`/srv/klartex/page-templates/<namn>/`), base64-JSON-upload, gränser 1 MB template / 5 MB asset / 10 assets per namn | Live sedan `backend 0.2.1` (2026-05-12). Auth via `API_TOKEN` (samma token gate:ar `/render` + writes på `/page-templates`, se "API-auth" nedan). Per-user-auth med Clerk planeras. |
| **API-auth** | Shared `API_TOKEN` bearer på alla write-endpoints (`/render`, `POST/DELETE /page-templates`). Discovery + `/health` publika. | Live sedan `backend 0.3.0` (2026-05-12). Stopgap innan Clerk landar på frontenden + JWT-validering här. |
| **Repo-struktur** | Webbappen i `app/` i detta repo, landningssidan i roten | (a)-alternativet. Bryts ut till eget repo om scopet växer. |
| **Domängräns** | `klartex.se` = landningssida, `app.klartex.se` = webbapp, `api.klartex.se` = klartex serve | DNS hos Loopia, kärnan i Hetzner. |
| **Frontend-stack** | **Förslag (inte beslutat):** React + Vite + Tiptap + TanStack Query + TailwindCSS | Bestäms vid fas 1-start. Alt: Svelte/SvelteKit. |
| **Auth-leverantör** | **Förslag (fas 5):** Supabase Auth eller magic-link + egen backend | Inte aktuellt under fas 0–4. |

### Varför Hetzner istället för Fly.io

Tidigare utkast nämnde Fly.io. Skälen att gå Hetzner istället:

- **Billigare.** €3.79/mån mot Fly.io ~€8–15 för motsvarande resurs.
- **EU-jurisdiktion.** Hetzner är tyskt; viktigt eftersom användardata (när konton kommer) faller under GDPR.
- **Färre rörliga delar.** Compose + Caddy är genomskinligare än Fly.io-machines.
- **Skalningsbehov saknas.** En `cax11` räcker långt på MVP-volymer.

Tradeoff: vi sköter OS-uppdateringar och backups själva (`unattended-upgrades` aktiverat; Hetzner snapshots manuellt tills behov uppstår).

## Lärdomar — backend-image (2026-05-11)

Tre iterationer krävdes för att få TeX Live-imagen att rendera klartex korrekt:

1. **`tabularx` → `tools`.** I TL2026 finns `tabularx` bara som del av `tools`-paketet. Gammal vana från TL ≤2024.
2. **`xelatex` inte på PATH.** `texlive/texlive`-bas-imagen sätter PATH via `/etc/profile` (login-shell), uvicorn körs non-interactive. Symlink `/usr/local/texlive/*/bin/<arch>` → `/usr/local/texlive-bin` + `ENV PATH=` fixar.
3. **Cherry-picking är tröttsamt.** `tcolorbox` behöver `tikz` behöver `tikzfill` behöver … Bytte till `collection-latexextra` som täcker alla transitivt + ger plats för framtida block.

Slutsats för framtida bygg: börja brett (`collection-latexextra` + `collection-fontsrecommended` + specifika tools), inte smalt.

## Risker

| Risk | Mitigering |
|------|-----------|
| Tiptap ↔ klartex-JSON-rundresan blir lossy (t.ex. inline-formatering, kapslade block) | Fas 2 har testsvit mot kärnans fixtures. Om förlustfrihet inte går: kör med Tiptap som rendering-only och behåll JSON som källan (osmidigt UX, men funkar). |
| XeLaTeX-fel som är obegripliga för slutanvändare | Fas 6 har felöversättning. Kärnan exponerar redan strukturerade valideringsfel via FastAPI — det räcker långt. |
| Hosting-miljöer som inte stödjer XeLaTeX | Använd kärnans Dockerfile på en plattform som tar Docker (Fly.io / Railway / VPS). Aldrig serverless. |
| Branding-fragment-formatet ändras i kärnan | Branding-vyn ska bara generera fragment via kärnans schema, inte handgissa LaTeX. Ändras formatet, ändras genereringen — inte alla sparade brandings. |
| Dokumentlagring (fas 5) växer till en filregister-design som inte är genomtänkt | Behåll persistent storage minimal i fas 5: bara `document_id → klartex_json`. Filregister-skissen i `filregister.md` aktiveras *senare* när Styrla/OpenVera trycker på. |

## Definition av "klar för MVP-launch"

Allt nedan måste vara sant innan vi annonserar publikt:

- [ ] Bob-testet går: helt nya VKF-styrelseledamoten Bob lyckas, utan handledning, producera en kallelse på 10 minuter.
- [ ] Minst tre olika dokumenttyper (kallelse, protokoll, motion) renderar korrekt med VKF-branding.
- [ ] En andra organisation (utan VKF-branding) har gjort samma sak via branding-vyn.
- [ ] Inga obegripliga LaTeX-felmeddelanden visas för slutanvändaren.
- [ ] `klartex.se` är levande och pekar på rätt sak; `index.html` är uppdaterad så att den länkar till appen.
- [ ] CHANGELOG / release notes finns på en publik plats.
- [ ] Privacy / villkor-sida finns (även minimal — GDPR kräver det).

## Nästa steg

1. **Konkretisera frontend-stacken** mot `~/repos/openvera` som referens — formalisera valet (React + Vite + Tiptap + …) innan scaffold.
2. **Öppna issue `MVP fas 1 — minimal Tiptap end-to-end`** i `swedev/klartex.se`-repot.
3. **Scaffolda `app/`** enligt stacken, deploya första statiska build till `app.klartex.se`.
4. **Implementera Tiptap-editor** med basblock (heading, paragraph, bulletList, orderedList + inline-formatering) som serialiserar till klartex-JSON och POST:ar till `https://api.klartex.se/render` med `page_template: "vkf"`.
