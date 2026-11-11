/* A spasso con Daisy — gestione del consenso cookie, nessuna dipendenza.
 *
 * Secondo le linee guida del Garante privacy (10 giugno 2021):
 *  - banner alla prima visita con «Accetta tutti», «Rifiuta», «Personalizza»; la X chiude e rifiuta;
 *  - nessuna casella pre-selezionata, lo scroll non vale come consenso;
 *  - scelta ricordata per `days` giorni (default 180), poi richiesta di nuovo;
 *  - scelta modificabile in ogni momento («Preferenze cookie» nel footer).
 *
 * I contenuti di terze parti restano bloccati finché la loro categoria non è accettata:
 *   <div class="embed" data-consent="embeds" data-embed="airbnb" data-id="12345">…segnaposto…</div>
 *   <div class="embed" data-consent="embeds" data-embed="iframe" data-src="https://…" data-title="…">…</div>
 *   <script type="text/plain" data-consent="analytics" data-src="https://…"></script>
 *
 * API: window.DaisyConsent.get(categoria) · .open() · .onChange(fn)
 */
(function () {
  'use strict';

  var KEY = 'daisy-consent';
  var doc = document;
  var cfgEl = doc.getElementById('consent-config');
  if (!cfgEl) return;
  var cfg = JSON.parse(cfgEl.textContent);
  var banner = doc.getElementById('consent');
  var dialog = doc.getElementById('consent-dialog');
  var listeners = [];
  var sdkLoaded = {};

  function read() {
    try {
      var data = JSON.parse(localStorage.getItem(KEY));
      if (!data || data.v !== cfg.version) return null;
      if (Date.now() - data.ts > cfg.days * 864e5) return null;
      return data;
    } catch (e) { return null; }
  }

  var state = read();

  function get(cat) {
    if (cat === 'necessary') return true;
    return !!(state && state.choices && state.choices[cat]);
  }

  function all(value) {
    var o = {};
    cfg.categories.forEach(function (c) { o[c] = value; });
    return o;
  }

  function current() {
    var o = {};
    cfg.categories.forEach(function (c) { o[c] = get(c); });
    return o;
  }

  function save(choices) {
    var before = current();
    var clean = {};
    cfg.categories.forEach(function (c) { clean[c] = !!choices[c]; });
    state = { v: cfg.version, ts: Date.now(), choices: clean };
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* modalità privata: vale per la sessione */ }
    hideBanner();
    closeDialog();

    // Consenso revocato dopo aver già caricato contenuti esterni: si ricarica la pagina per rimuoverli.
    var revoked = cfg.categories.some(function (c) { return before[c] && !clean[c]; });
    if (revoked && doc.querySelector('[data-consent-active]')) { location.reload(); return; }

    apply();
    listeners.forEach(function (fn) { try { fn(clean); } catch (e) { /* ignora */ } });
  }

  /* ---------- Banner e pannello ---------- */
  function showBanner() { if (banner) banner.hidden = false; }
  function hideBanner() { if (banner) banner.hidden = true; }

  function open() {
    if (!dialog) return;
    dialog.querySelectorAll('[data-consent-category]').forEach(function (input) {
      input.checked = get(input.getAttribute('data-consent-category'));
    });
    if (typeof dialog.showModal === 'function') {
      if (!dialog.open) dialog.showModal();
    } else {
      dialog.setAttribute('open', '');
    }
  }

  function closeDialog() {
    if (!dialog) return;
    if (typeof dialog.close === 'function' && dialog.open) dialog.close();
    else dialog.removeAttribute('open');
  }

  doc.addEventListener('click', function (e) {
    var actionEl = e.target.closest('[data-consent-action]');
    if (actionEl) {
      var action = actionEl.getAttribute('data-consent-action');
      if (action === 'accept') save(all(true));
      else if (action === 'reject') save(all(false));
      else if (action === 'customize') open();
      else if (action === 'dismiss') closeDialog();
      else if (action === 'save') {
        var choices = {};
        dialog.querySelectorAll('[data-consent-category]').forEach(function (input) {
          choices[input.getAttribute('data-consent-category')] = input.checked;
        });
        save(choices);
      }
      return;
    }
    // «Mostra il contenuto» dentro un segnaposto: consenso esplicito per quella sola categoria
    var grantEl = e.target.closest('[data-consent-grant]');
    if (grantEl) {
      var next = current();
      next[grantEl.getAttribute('data-consent-grant')] = true;
      save(next);
    }
  });

  if (dialog) {
    // clic sullo sfondo del pannello = chiudi senza modificare
    dialog.addEventListener('click', function (e) { if (e.target === dialog) closeDialog(); });
  }

  /* ---------- Attivazione dei contenuti bloccati ---------- */
  function loadScript(src) {
    if (sdkLoaded[src]) return;
    sdkLoaded[src] = true;
    var s = doc.createElement('script');
    s.src = src;
    s.async = true;
    doc.body.appendChild(s);
  }

  function activate(el) {
    el.setAttribute('data-consent-active', '');

    if (el.tagName === 'SCRIPT') {
      var s = doc.createElement('script');
      if (el.getAttribute('data-src')) s.src = el.getAttribute('data-src');
      else s.text = el.text;
      s.async = true;
      el.parentNode.insertBefore(s, el.nextSibling);
      return;
    }

    var kind = el.getAttribute('data-embed');
    if (kind === 'airbnb') {
      var id = el.getAttribute('data-id') || '';
      var domain = el.getAttribute('data-domain') || 'www.airbnb.it';
      if (!/^\d+$/.test(id) || !/^www\.airbnb\.[a-z.]{2,10}$/.test(domain)) return;
      var url = 'https://' + domain + '/rooms/' + id + '?source=embed_widget';
      el.innerHTML =
        '<div class="airbnb-embed-frame" data-id="' + id + '" data-view="home" data-hide-price="true" ' +
        'style="width:100%;max-width:450px;height:300px;margin:auto">' +
        '<a href="' + url + '">Airbnb</a><a href="' + url + '" rel="nofollow">Airbnb</a></div>';
      el.classList.add('is-loaded');
      loadScript('https://' + domain + '/embeddable/airbnb_jssdk');
      return;
    }

    if (kind === 'iframe') {
      var src = el.getAttribute('data-src') || '';
      if (!/^https:\/\//.test(src)) return;
      var frame = doc.createElement('iframe');
      frame.src = src;
      frame.title = el.getAttribute('data-title') || '';
      frame.loading = 'lazy';
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      frame.setAttribute('allowfullscreen', '');
      el.innerHTML = '';
      el.appendChild(frame);
      el.classList.add('is-loaded');
    }
  }

  function apply() {
    doc.querySelectorAll('[data-consent]:not([data-consent-active])').forEach(function (el) {
      if (get(el.getAttribute('data-consent'))) activate(el);
    });
  }

  /* ---------- Avvio ---------- */
  var needsConsent = cfg.categories.length > 0 &&
    (cfg.banner === 'always' || (cfg.banner === 'auto' && doc.querySelector('[data-consent]')));

  if (state) apply();
  else if (needsConsent) showBanner();

  window.DaisyConsent = {
    get: get,
    open: open,
    onChange: function (fn) { listeners.push(fn); }
  };
})();
