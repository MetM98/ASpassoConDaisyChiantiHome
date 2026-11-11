# A spasso con Daisy · Chianti Home

Due appartamenti nel cuore del Chianti Classico a Barberino Tavarnelle: un bilocale e un monolocale. Cani di piccola taglia benvenuti.

Sito vetrina statico (HTML + CSS, ~3 KB di JavaScript, nessun framework) in **italiano, inglese e tedesco**, pensato per GitHub Pages.

| Pagina | File |
| --- | --- |
| Italiano | `index.html` |
| English | `en/index.html` |
| Deutsch | `de/index.html` |

## Come modificare i testi

I file HTML sono **generati**: non modificarli a mano.

1. Modifica i testi in `src/content/it.json`, `en.json` e `de.json`. I tre file hanno la stessa struttura.
2. Per contatti e impostazioni generali usa `src/site.json`: email, numero WhatsApp, telefono, Instagram, link a Google Maps, URL del sito.
3. Rigenera le pagine:

```bash
pip install jinja2
```

```bash
python3 build.py
```

Il layout di tutte le lingue è in `src/template.html`; lo stile è in `assets/css/style.css`.

### Impostazioni in `src/site.json`

| Campo | Esempio | Note |
| --- | --- | --- |
| `whatsapp` | `393331234567` | Solo cifre, con prefisso internazionale. Se è vuoto, il pulsante "Invia su WhatsApp" fa scegliere il contatto. |
| `phone` | `+39 333 123 4567` | Se è vuoto, non viene mostrato. |
| `instagram` | `aspassocondaisy` | Senza @. Se è vuoto, non viene mostrato. |
| `noindex` | `true` | Tiene l'anteprima fuori da Google. Mettere `false` alla pubblicazione definitiva. |
| `base_url` | URL pubblico del sito | Serve per i link di condivisione e per l'hreflang. |

## Pubblicazione su GitHub Pages

1. Su GitHub apri il repository → **Settings → Pages**.
2. In **Build and deployment** scegli **Deploy from a branch**.
3. Seleziona il branch (`main`, dopo il merge) e la cartella **/ (root)**, poi salva.
4. Dopo un paio di minuti il sito è online su `https://metm98.github.io/ASpassoConDaisyChiantiHome/`.

Il file `.nojekyll` evita che GitHub rielabori i file. Tutti i percorsi sono relativi, quindi il sito funziona anche in una sottocartella o con un dominio proprio (ad es. `aspassocondaisy.com`, da configurare in **Settings → Pages → Custom domain**).

Per vederlo in locale:

```bash
python3 -m http.server 8000
```

Poi apri http://localhost:8000. Il doppio clic su `index.html` funziona, ma conviene il server locale.

## Struttura

```
index.html, en/, de/          pagine generate (IT/EN/DE)
assets/css/style.css          stile (palette notte/luce, tipografia, layout responsive)
assets/js/main.js             header, menu mobile, animazioni, modulo → WhatsApp/email
assets/fonts/                 Cormorant Garamond, Jost, Sacramento (OFL, ospitati in locale per GDPR e velocità)
assets/img/brand/             logo (chiaro/scuro trasparente), favicon, immagine social
assets/img/illustrations/     illustrazioni SVG originali (colline, appartamenti, mappa, Daisy)
assets/img/icons.svg          set di icone SVG (incorporate nelle pagine solo quelle usate)
assets/img/photos/            foto del territorio da Unsplash in WebP + credits.json
src/                          template, contenuti e impostazioni
build.py                      generatore
```

## Prima della pubblicazione definitiva

- [ ] Foto vere degli appartamenti: sostituire le illustrazioni in `apartments.units[].illustration`. Le foto di Unsplash mostrano solo il territorio.
- [ ] Numero WhatsApp/telefono (`src/site.json`).
- [ ] Capienza, posti letto e metratura dei due appartamenti. I valori attuali ("fino a 4 ospiti", "2 ospiti") sono ipotesi.
- [ ] Politica di cancellazione: è ancora segnata "Da confermare".
- [ ] Link Airbnb e calendario delle disponibilità (il riquadro "In arrivo").
- [ ] Peso massimo dei cani accettati ed eventuali supplementi.
- [ ] Privacy policy/cookie: il sito non usa cookie né tracciamenti, ma una pagina privacy è consigliata.
- [ ] `noindex` → `false` in `src/site.json`, poi `python3 build.py`.
