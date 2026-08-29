# Klartex design

Källdokument för grafisk profil och appdesign. Öppna `.dc.html`-filerna i en webbläsare; `support.js` är deras gemensamma runtime. Logotyp- och komplementgrafikfilerna (`*.svg`) ligger i samma katalog eftersom canvaserna refererar dem med relativa namn.

`assets/` i repots rot bär kopior av de filer landningssidan refererar (`klartex-lockup-reverse.svg`, `klartex-blad-arm.svg`, `klartex-blad-omvant.svg`) — den katalogen är det som deployas. `design/` är källan: ändras någon av dem här ska kopian uppdateras. `assets/favicon.svg` är inte en kopia utan en sammansättning: `klartex-symbol-v2-reverse.svg` nästlad orörd på en kvadratisk Marin 900-platta. Ändras symbolfilen ska favicon byggas om. `assets/fonts/` bär profilens tre typsnitt som självhostade woff2; `assets/fonts/README.md` beskriver hur de byggs och varför två av dem heter Klartex Serif och Klartex Sans.

| Fil | Innehåll |
|-----|----------|
| `Klartex grafisk profil.dc.html` | **Auktoriteten.** Logotyp, färgroller, typografi, ikonspråk (Lucide), dokumentmall (brevpapper) och komplementgrafik (bladet). |
| `Klartex logotyp.dc.html` | Den låsta lockupen: metrik, filer, symbolens placering mot ordmärket, samt rundorna som ledde dit. |
| `Klartex appvyer.dc.html` | Översikt över webbappens vyer. |
| `Dokument*.dc.html`, `Dokumentredigering.dc.html` | Dokumentlista, dokumentdetalj, tomt läge och redigeringsvyn. |
| `Mallar.dc.html`, `Mallredigering.dc.html` | Mallbibliotek och mallredigering. |
| `Genererade filer.dc.html`, `Installningar.dc.html` | Filhistorik och inställningar. |
| `Logga in - *.dc.html` | Inloggning med e-post och engångskod, inklusive felläge. |
| `Fel - *.dc.html` | Felsidor: saknad behörighet, sidan finns inte. |
| `klartex-lockup*.svg` | Logotypen: standard, negativ (`-reverse`), enfärg svart och vit. Ordmärke och symbol i samma fil, inga typsnittsberoenden. |
| `klartex-wordmark.svg` | Ordmärket ensamt. |
| `klartex-symbol-v2*.svg` | Symbolen ensam, beskuren till bläck (viewBox 569 × 646), standard och negativ. |
| `klartex-symbol*.svg` | Symbolen med luft runt om (viewBox 610 × 675), samma path; används i vyerna där symbolen behöver marginal. |
| `klartex-blad*.svg` | Komplementgrafiken: bladet med tät rot, tät spets (`-omvant`) respektive armen (`-arm`). Endast på marint underlag; skalas fritt, roteras eller speglas aldrig. |

Snabbreferens (detaljer i profildokumentet):

- **Färg:** Marin 900 `#071A43` (text, rubriker, mörka ytor), Marin 700 `#0B2B65` (skiljelinjer och hover på mörk yta), Klarblå 500 `#0870FF` (accent: symbolens band, ikonaccent), Klarblå 600 `#0A5FD8` (interaktiv: länkar, primärknapp, fokusram — enda blå som får bära text), Klarblå 100 `#DCE9FF` (markerad rad), Papper `#FBFAF8` (sidbakgrund, dokumentets ark), Linje `#E3E1DB` (ramar och avdelare, 1 px), Grå 600 `#6B6A63` (sekundär text, metadata), Tegel 600 `#9E3B22` (fel och varning, aldrig dekor).
- **Typografi:** Source Serif 4 (400/600/700) för levererade dokument, rubriker och ordmärket; Source Sans 3 (400/600/700) för gränssnittet; JetBrains Mono (400/700) enbart för kod, kommandon och identifierare. Skala: Display 56/1,05 serif · Rubrik 1 32/1,15 serif · Rubrik 2 21/1,3 serif · Bröd 16/1,6 sans · Liten 13/1,5 sans.
- **Ikoner:** Lucide, oförändrade — inga egna ikoner.
- **Ton:** få beslut, hårt hållna, upprepade utan variation. Innehållet får variera, aldrig ramen runt det.
