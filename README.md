# A spasso con Daisy · Chianti Home

Due appartamenti nel cuore del Chianti Classico a Barberino Tavarnelle: un bilocale e un monolocale. Cani di piccola taglia benvenuti.

Sito vetrina statico (HTML + CSS, poco JavaScript, nessun framework) in **italiano, inglese e tedesco**, pubblicato con GitHub Pages.

| Pagina | Italiano | English | Deutsch |
| --- | --- | --- | --- |
| Home | `index.html` | `en/index.html` | `de/index.html` |
| Privacy | `privacy/` | `en/privacy/` | `de/privacy/` |
| Cookie | `cookie/` | `en/cookie/` | `de/cookie/` |

## Come modificare i testi

Le pagine HTML sono **generate**: non modificarle a mano.

1. Testi delle pagine: `src/content/it.json`, `en.json`, `de.json` (stessa struttura).
2. Privacy, cookie, banner del consenso e calendario: `src/content/legal/it.json`, `en.json`, `de.json`.
3. Contatti, titolare, Airbnb e consenso: `src/site.json` (vedi sotto).
4. Rigenera le pagine:

```bash
pip install jinja2
```

```bash
python3 build.py
```

Template: `src/base.html` (struttura comune: header, footer, banner cookie), `src/home.html`, `src/legal.html`, `src/macros.html`. Stile: `assets/css/style.css`.

### Impostazioni in `src/site.json`

| Campo | Esempio | Note |
| --- | --- | --- |
| `whatsapp` | `393331234567` | Solo cifre, con prefisso. Se è vuoto, il pulsante WhatsApp fa scegliere il contatto. |
| `phone` | `+39 333 123 4567` | Se è vuoto, non viene mostrato. |
| `instagram` | `aspassocondaisy` | Senza @. |
| `owner.name`, `owner.address` | `Ilaria …`, `Via …, 50028 Barberino Tavarnelle (FI)` | Titolare del trattamento. Finché mancano, le pagine legali mostrano un segnaposto giallo «[da completare]». |
| `owner.tax_id` / `owner.vat` | codice fiscale / partita IVA | La P. IVA, se presente, compare anche nel footer. |
| `owner.cin` | `IT048…` | **Codice Identificativo Nazionale**: obbligatorio in ogni annuncio di locazione turistica, sito compreso. Compare nel footer. |
| `legal_updated` | `2026-11-11` | Data «Ultimo aggiornamento» di privacy e cookie policy. |
| `airbnb.bilocale.listing_id` | `12345678` | Numero dell'annuncio (dall'URL `airbnb.it/rooms/12345678`). Attiva il widget Airbnb, bloccato fino al consenso. |
| `airbnb.<unità>.url` | link all'annuncio | Facoltativo: pulsante «Apri su Airbnb». |
| `consent.banner` | `always` / `auto` | `auto` mostra il banner solo se nella pagina ci sono contenuti di terze parti, cioè quando l'annuncio Airbnb è collegato. |
| `consent.version` | `1` | Aumentalo quando cambi la cookie policy: il consenso viene richiesto di nuovo a tutti. |
| `consent.days` | `180` | Dopo quanti giorni il consenso viene richiesto di nuovo (Garante: non prima di 6 mesi). |
| `consent.categories` | `["embeds"]` | Aggiungi `"analytics"` solo se introduci strumenti di statistica (e aggiorna la cookie policy). |
| `noindex` | `true` | Tiene l'anteprima fuori da Google. Mettere `false` alla pubblicazione definitiva. |

## Cookie e consenso

Il sito, da solo, **non usa cookie**. Salva solo la scelta sui cookie (`localStorage`, chiave `daisy-consent`). Font, foto e icone sono ospitati nel sito.

Il banner (`assets/js/consent.js`) segue le linee guida del Garante privacy del 10 giugno 2021:
- **Accetta tutti** e **Rifiuta** hanno pari evidenza; c'è il link **Personalizza**; la **X** chiude e rifiuta.
- Nessuna casella pre-selezionata. Lo scroll non vale come consenso.
- La scelta dura 6 mesi ed è modificabile in ogni momento dal link «Preferenze cookie» nel footer.

I contenuti di terze parti restano bloccati finché l'ospite non dà il consenso. Al loro posto compare un riquadro «Mostra il contenuto». Per aggiungerne altri (es. una mappa Google incorporata):

```html
<div class="embed" data-consent="embeds" data-embed="iframe" data-src="https://…" data-title="Mappa">
  …segnaposto…
</div>
```

Gli script di statistica vanno inseriti come `<script type="text/plain" data-consent="analytics" data-src="https://…"></script>`.

## Calendario Airbnb

Airbnb non offre un calendario da incorporare. Le date occupate arrivano quindi dal **link iCal privato** di ogni annuncio:
1. Ogni 3 ore la GitHub Action `.github/workflows/pages.yml` scarica i calendari.
2. Lo script `tools/sync_airbnb.py` tiene **solo le date**, mai nomi, telefoni o codici di prenotazione.
3. Le date finiscono in `assets/data/availability.json`, che il sito legge.

Nessuna richiesta parte dal browser degli ospiti verso Airbnb, quindi il calendario non richiede consenso. Finché non ci sono dati, il riquadro mostra «In arrivo».

### 1. Copiare il link iCal da Airbnb (per ogni appartamento)

1. Su airbnb.it, in modalità host, apri **Calendario** e seleziona l'annuncio.
2. Apri **Impostazioni disponibilità** e cerca la sezione **Collega calendari**.
3. Scegli **Esporta calendario** e copia il link che finisce in `.ics`.

Il link è privato: trattalo come una password e non metterlo nei file del sito.

### 2. Salvare i link come secret su GitHub

Nel repository vai in **Settings → Secrets and variables → Actions → New repository secret** e crea:
- `AIRBNB_ICAL_BILOCALE`: link del bilocale.
- `AIRBNB_ICAL_MONOLOCALE`: link del monolocale.
- Facoltativi: `AIRBNB_ICAL_BILOCALE_EXTRA` e `AIRBNB_ICAL_MONOLOCALE_EXTRA`, per altri calendari iCal (es. Booking.com) separati da spazi. Le date vengono unite.

Per aggiungere un'unità: chiave in `src/site.json → airbnb`, `id` uguale in `src/content/*.json → apartments.units`, e variabili d'ambiente nel workflow.

### Test dello script

```bash
python3 -B -m unittest discover -s tools
```

## Pubblicazione su GitHub Pages

La pubblicazione avviene con **GitHub Actions**: rigenera le pagine, sincronizza i calendari e pubblica.

1. Nel repository apri **Settings → Pages**.
2. In **Build and deployment → Source** scegli **GitHub Actions**, non «Deploy from a branch».
3. Apri la scheda **Actions** → **Build and deploy site** → **Run workflow** sul branch `main`.
4. Dopo un paio di minuti il sito è online su `https://metm98.github.io/ASpassoConDaisyChiantiHome/`.

Da quel momento il sito si ripubblica:
- a ogni modifica su `main`;
- ogni 3 ore, per aggiornare il calendario.

Se Airbnb non risponde, l'esecuzione mostra un avviso e il sito tiene le ultime date note.

Nei repository pubblici GitHub **sospende le esecuzioni programmate dopo 60 giorni senza attività**, e di solito avvisa via email. Per riattivarle: **Actions → Build and deploy site → Enable workflow**.

Tutti i percorsi sono relativi, quindi il sito funziona anche con un dominio proprio (es. `aspassocondaisy.com`, da impostare in **Settings → Pages → Custom domain**).

Per vederlo in locale:

```bash
python3 -m http.server 8000
```

Poi apri http://localhost:8000.

## Struttura

```
index.html, privacy/, cookie/, en/, de/   pagine generate
assets/css/style.css          stile (palette notte/luce, tipografia, layout responsive)
assets/js/main.js             header, menu mobile, animazioni, calendario, modulo → WhatsApp/email
assets/js/consent.js          banner e preferenze cookie, sblocco dei contenuti di terze parti
assets/data/availability.json date occupate (generato dalla GitHub Action)
assets/fonts/                 Cormorant Garamond, Jost, Sacramento (OFL, ospitati in locale)
assets/img/                   logo, favicon, illustrazioni SVG, icone, foto (Unsplash, credits.json)
src/                          template, contenuti e impostazioni
tools/sync_airbnb.py          sincronizzazione calendari iCal (+ test)
.github/workflows/pages.yml   build, sincronizzazione e pubblicazione
build.py                      generatore
```

## Prima della pubblicazione definitiva

- [ ] Dati del titolare, codice fiscale/P. IVA e **CIN** in `src/site.json → owner`.
- [ ] Rilettura di privacy e cookie policy da parte di chi segue gli adempimenti dell'attività.
- [ ] Link iCal di Airbnb nei secret, `listing_id` degli annunci in `src/site.json`, poi `consent.banner` → `auto`.
- [ ] Foto vere degli appartamenti al posto delle illustrazioni (`apartments.units[].illustration`).
- [ ] Numero WhatsApp/telefono.
- [ ] Capienza e posti letto dei due appartamenti: i valori attuali sono ipotesi.
- [ ] Politica di cancellazione: è ancora segnata «Da confermare».
- [ ] Peso massimo dei cani accettati ed eventuali supplementi.
- [ ] `noindex` → `false`, poi `python3 build.py`.
