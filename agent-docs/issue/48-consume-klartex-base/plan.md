# Plan: Issue #48 — Consume ghcr.io/swedev/klartex-base: remove local base image build

## Mål

Basimagen med TeX Live + mscorefonts byggs och publiceras numera från `swedev/klartex` (`docker/Dockerfile.base` → `ghcr.io/swedev/klartex-base` via dess `base-image.yml`, med hela klartex-testsviten körd i den nybyggda amd64-imagen före push). Det lokala basbygget i detta repo är därmed överflödigt: ta bort `backend/Dockerfile.base` och `.github/workflows/backend-base.yml`, peka om `backend/Dockerfile`s `FROM`-pin till den nya basen, och uppdatera dokumentationen så att den beskriver det nya flödet.

## Triagering

> Beslutsunderlag för detta issue.

| Fält | Värde |
|------|-------|
| **Blockeras av** | Inget — förarbetet (swedev/klartex#56, swedev/klartex#57) är levererat och taggen `20260828-3` är publicerad |
| **Blockerar** | Inget |
| **Relaterade issues** | #32 (stängt — införde det lokala basbygget som nu tas bort); swedev/klartex#55 (refereras i issuet) |
| **Omfattning** | 5 filer: 2 raderas, 3 ändras (`backend/`, `.github/workflows/`, `PLAN.md`) |
| **Risk** | Låg |
| **Komplexitet** | Låg |
| **Säker för junior** | Ja |
| **Konfliktrisk** | Låg — #20:s implementation landade i PR #25 (mergad 2026-08-27), så dess lagrade plan är inaktuell; kvarvarande #20-scope överlappar högst `backend/README.md`, i andra avsnitt än de som ändras här |

### Triagemässiga noteringar

- Den nya basen `ghcr.io/swedev/klartex-base` (byggd från `docker/Dockerfile.base` i `swedev/klartex`, infört i swedev/klartex#56) är runtime-ekvivalent med den lokala `backend/Dockerfile.base` men med starkare bygg-/testproveniens: samma TeX Live-bas, apt-paket, mscorefonts och samma `/usr/local/texlive-bin`-symlänk som app-Dockerfilens `ENV PATH` förlitar sig på, plus per-bygge-pinnad `TEXLIVE_REF` och OCI-labels. App-imagen fungerar oförändrad ovanpå den, förutom `FROM`-raden.
- Testtäckningen ska beskrivas rättvist: `base-image.yml` kör hela klartex-testsviten i den nybyggda **amd64**-imagen; arm64-varianten täcks av Dockerfilens inbyggda sanity-check (xelatex, kpsewhich, fontlista). Release-smoke-testet i detta repos `deploy.yml` är också amd64, medan produktion kör ARM (cax11). Gapet fanns redan med det lokala bygget (som inte körde några tester alls i imagen) och accepteras som kvarstående risk — höjer inte helhetsrisken över Låg.
- Paketet `ghcr.io/swedev/klartex-base` är publikt — inga pull-credentials behövs (varken i CI eller lokalt).

## Angreppssätt

Detta är ren konsolidering: samma bild byggs på två ställen, och `swedev/klartex`-varianten är den bättre (testsviten körs i amd64-imagen före publicering, `TEXLIVE_REF` pinnas per bygge, OCI-labels). Kopian här raderas och konsumtionen pekas om.

Issuet lämnar ompekningen av `FROM`-pinnen öppen ("kan följa vid nästa bump"), men taggen + digesten att pinna står redan i issuet (`20260828-3@sha256:b01105…`). Planen gör därför ompekningen i samma PR — se designbeslut 1.

Tre saker att hålla i ordning:

1. **Radera** de två filerna som utgör det lokala bygget. `ci.yml` och `deploy.yml` refererar dem inte (verifierat med grep), så inga workflow-ändringar utöver raderingen behövs.
2. **Peka om** `FROM`-raden i `backend/Dockerfile` till `ghcr.io/swedev/klartex-base:20260828-3@sha256:b011056413d449bdc41b893ff1bd538a2be46d78d3794698eb134f45936d6ff2` och skriv om filens huvudkommentar: basen byggs nu i `swedev/klartex`, och bump-proceduren är att läsa av tagg + digest ur step-summaryn för respektive `base-image.yml`-körning där.
3. **Uppdatera dokumentationen** i nu-läge (inga "numera"/"tidigare"-formuleringar): `backend/README.md`s Docker-avsnitt och "Bumpa basimagen", samt de två raderna i `PLAN.md`s beslutstabell som nämner `klartex-se-base` respektive `backend/Dockerfile.base`.

De redan publicerade taggarna under `ghcr.io/swedev/klartex-se-base` lämnas orörda på GHCR — historikens `Dockerfile`-versioner pinnar dem, och publicerade bastaggar som refereras i historiken får inte raderas (etablerad konvention, dokumenterad i både `backend/README.md` och den nya basens header).

## Steg

### Fas 0: Verifiera den nya basimagen

1. Verifiera pinnen mot GHCR innan något ändras (anonymt, ingen 7 GB-pull)
   - `docker buildx imagetools inspect ghcr.io/swedev/klartex-base:20260828-3`
   - Kontrollera: manifest-digesten är exakt `sha256:b011056413d449bdc41b893ff1bd538a2be46d78d3794698eb134f45936d6ff2`, manifestet innehåller både `linux/amd64` och `linux/arm64`, och kommandot lyckas utan inloggning (paketet är publikt)
   - Avviker digesten från issuets: stanna och stäm av med issuet i stället för att pinna något annat

### Fas 1: Ta bort det lokala basbygget

1. Radera `backend/Dockerfile.base`
   - `git rm backend/Dockerfile.base`
2. Radera `.github/workflows/backend-base.yml`
   - `git rm .github/workflows/backend-base.yml`

### Fas 2: Peka om FROM-pinnen

1. Uppdatera `FROM`-raden i `backend/Dockerfile`
   - Ny rad: `FROM ghcr.io/swedev/klartex-base:20260828-3@sha256:b011056413d449bdc41b893ff1bd538a2be46d78d3794698eb134f45936d6ff2`
   - Filer att ändra: `backend/Dockerfile`
2. Skriv om huvudkommentaren i `backend/Dockerfile` (rad 1–10)
   - Basen är `ghcr.io/swedev/klartex-base`, byggd från `docker/Dockerfile.base` i `swedev/klartex` av dess `base-image.yml`, med klartex-testsviten körd i amd64-imagen före push
   - Bump-procedur: image-referensen `ghcr.io/swedev/klartex-base:<tagg>@<digest>` kopieras ur step-summaryn för publiceringskörningen i `swedev/klartex` (summaryn skriver referensen, inte en färdig `FROM`-rad) och sätts in i `FROM`-raden; pinnen flyttas i egen PR här
   - Behåll poängen om att pinnen bär både tagg (läsbarhet) och digest (immutabilitet)

### Fas 3: Uppdatera dokumentationen

1. `backend/README.md` — Docker-avsnittet
   - Beskriv tvådelningen med `ghcr.io/swedev/klartex-base` som bas (byggd i `swedev/klartex`); ta bort omnämnandena av `Dockerfile.base` och `backend-base.yml` i detta repo
2. `backend/README.md` — avsnittet "Bumpa basimagen"
   - Ny procedur: (1) bumpa basen i `swedev/klartex` (dess `docker/Dockerfile.base`) och invänta `base-image.yml`-publiceringen där, (2) kopiera image-referensen `ghcr.io/swedev/klartex-base:<tagg>@<digest>` ur körningens step-summary (alternativt läs digesten med `docker buildx imagetools inspect ghcr.io/swedev/klartex-base:<tagg>`), (3) uppdatera `FROM`-pinnen i `backend/Dockerfile` i egen PR
   - Behåll regeln att publicerade bastaggar som refereras i historiken aldrig får raderas
3. `PLAN.md` — beslutstabellen (rad ~51–52)
   - **API-image**-raden: basimagen är `ghcr.io/swedev/klartex-base` (byggd i `swedev/klartex`)
   - **Bygge och deploy**-raden: ta bort bisatsen om att basimagen har egen workflow i detta repo; basen byggs och publiceras från `swedev/klartex`

## Filöversikt

| Fil | Åtgärd | Syfte |
|-----|--------|-------|
| `backend/Dockerfile.base` | Radera | Superseded — basen byggs från `docker/Dockerfile.base` i `swedev/klartex` |
| `.github/workflows/backend-base.yml` | Radera | Superseded — publiceringen sker via `base-image.yml` i `swedev/klartex` |
| `backend/Dockerfile` | Ändra | `FROM`-pin → `ghcr.io/swedev/klartex-base:20260828-3@sha256:b01105…`; huvudkommentar om bas och bump-procedur |
| `backend/README.md` | Ändra | Docker-avsnitt + "Bumpa basimagen" beskriver den nya basen och proceduren via `swedev/klartex` |
| `PLAN.md` | Ändra | Beslutstabellens **API-image**- och **Bygge och deploy**-rader pekar på `ghcr.io/swedev/klartex-base` |

## Berörda kodområden

Lista de primära kataloger/områden som planen berör (för konfliktdetektering):
- `backend/` (Dockerfile, Dockerfile.base, README.md)
- `.github/workflows/`
- `PLAN.md`

## Designbeslut

> Icke-triviala val gjorda under planeringen. Feedback välkommen; annars implementeras enligt dessa.

### 1. Ompekningen görs i samma PR som raderingen
**Alternativ:** A) radera nu, peka om vid nästa basbump (issuets minimala läsning) vs B) radera och peka om i samma PR
**Beslut:** B
**Motivering:** Issuet tillåter uttryckligen båda ("nothing forces an immediate repoint") och anger själv taggen + digesten att pinna, så ompekningen är en enradsändring utan eget utredningsbehov. Med A måste dokumentationen beskriva ett övergångsläge — pinnen kvar på den pensionerade `klartex-se-base` medan bump-proceduren pekar på `swedev/klartex` — och beroendet av det gamla GHCR-paketet lever kvar i onödan. Den nya basen är verifierad (klartex-testsviten körs i amd64-imagen före push, fas 0 verifierar manifestet) och `deploy.yml` smoke-testar app-imagen före publicering, så risken är låg. *Proveniens: agentens egen bedömning — öppen att ifrågasätta; att i stället bara radera nu är helt i linje med issuet.*

### 2. GHCR-paketet `klartex-se-base` lämnas orört
**Alternativ:** A) radera/avpublicera paketet när sista referensen försvinner vs B) lämna publicerade taggar orörda
**Beslut:** B
**Motivering:** Historikens `Dockerfile`-versioner pinnar `klartex-se-base:20260828-1` — raderas taggen går de byggena inte att reproducera. Regeln "publicerade bastaggar refererade i historiken får inte raderas" är etablerad konvention i `backend/README.md` och upprepas i den nya basens header i `swedev/klartex`. Ingen åtgärd på GHCR ingår i denna PR.

## Verifieringschecklista

- [ ] Fas 0 utförd: `docker buildx imagetools inspect ghcr.io/swedev/klartex-base:20260828-3` lyckas anonymt, digesten matchar issuets `sha256:b01105…`, och manifestet innehåller `linux/amd64` + `linux/arm64`
- [ ] `test ! -e backend/Dockerfile.base && test ! -e .github/workflows/backend-base.yml`
- [ ] Efter dokumentationsuppdateringen: `grep -rn 'klartex-se-base\|backend/Dockerfile\.base\|backend-base\.yml' backend/ .github/ PLAN.md index.html llms.txt` ger noll träffar (referenser till uppströms `docker/Dockerfile.base` i `swedev/klartex` är legitima och matchas inte av mönstret)
- [ ] `FROM`-pinnen i `backend/Dockerfile` är exakt `ghcr.io/swedev/klartex-base:20260828-3@sha256:b011056413d449bdc41b893ff1bd538a2be46d78d3794698eb134f45936d6ff2` (från issuet)
- [ ] `backend/README.md`s bump-procedur beskriver flödet via `swedev/klartex` (image-referensen ur `base-image.yml`-körningens step-summary)
- [ ] Dokumentationen är skriven i nu-läge — inga "numera"/"tidigare"-spår av flytten
- [ ] CI (`ci.yml`) grönt — Docker-fritt, så raderingen påverkar det inte
- [ ] (Valfritt, tungt: ~7 GB pull) `docker build -t klartex-se-backend:dev backend/` lyckas mot den nya basen. Hoppas det över är den accepterade kvarstående risken att första fullständiga app-bygget mot nya basen sker i release-workflowns smoke-test vid nästa `v*`-tagg — fas 0 har då redan verifierat att pinnen är pullbar och komplett
