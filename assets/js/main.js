/* A spasso con Daisy · Chianti Home — piccoli comportamenti, nessuna dipendenza. */
(function () {
  'use strict';

  var doc = document;
  var root = doc.documentElement;
  var header = doc.querySelector('.site-header');
  var hero = doc.querySelector('.hero');
  var toggle = doc.querySelector('.menu-toggle');
  var nav = doc.getElementById('nav');
  var hasIO = 'IntersectionObserver' in window;

  /* Header: diventa scuro e sfocato quando si lascia l'apertura */
  if (header && hero && hasIO) {
    new IntersectionObserver(function (entries) {
      header.classList.toggle('is-solid', !entries[0].isIntersecting);
    }, { rootMargin: '-72px 0px 0px 0px' }).observe(hero);
  } else if (header) {
    header.classList.add('is-solid');
  }

  /* Menu mobile */
  function setMenu(open) {
    root.classList.toggle('menu-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.querySelector('.sr-only').textContent = toggle.getAttribute(open ? 'data-close' : 'data-open');
  }
  if (toggle && nav) {
    toggle.addEventListener('click', function () {
      setMenu(toggle.getAttribute('aria-expanded') !== 'true');
    });
    nav.addEventListener('click', function (e) {
      if (e.target.closest('a')) setMenu(false);
    });
    doc.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && root.classList.contains('menu-open')) { setMenu(false); toggle.focus(); }
    });
    window.matchMedia('(min-width: 1181px)').addEventListener('change', function (mq) {
      if (mq.matches) setMenu(false);
    });
  }

  /* Comparsa morbida delle sezioni */
  var reveals = doc.querySelectorAll('.reveal');
  if (hasIO) {
    var revealIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          revealIO.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    reveals.forEach(function (el) { revealIO.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add('is-visible'); });
  }

  /* Voce di menu attiva in base alla sezione visibile */
  var links = doc.querySelectorAll('.nav__link');
  if (hasIO && links.length) {
    var byId = {};
    links.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var activeIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        var link = byId[entry.target.id];
        if (link && entry.isIntersecting) {
          links.forEach(function (a) { a.classList.remove('is-active'); });
          link.classList.add('is-active');
        }
      });
    }, { rootMargin: '-45% 0px -50% 0px' });
    Object.keys(byId).forEach(function (id) {
      var section = doc.getElementById(id);
      if (section) activeIO.observe(section);
    });
  }

  /* Calendario disponibilità (date occupate sincronizzate da Airbnb in assets/data/availability.json) */
  var availability = null;          // { unitId: [[inizio, fine), …] } — fine esclusa (giorno di partenza libero)
  var calendarApi = null;
  var calBox = doc.getElementById('availability');

  function isoDate(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }
  function nightBooked(unit, iso) {
    var ranges = availability && availability[unit];
    if (!ranges) return false;
    for (var i = 0; i < ranges.length; i++) if (iso >= ranges[i][0] && iso < ranges[i][1]) return true;
    return false;
  }

  if (calBox && window.fetch) {
    var calI18n = JSON.parse(doc.getElementById('calendar-i18n').textContent);
    var locale = calI18n.locale.replace('_', '-');
    fetch(calBox.getAttribute('data-src'), { cache: 'no-cache' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.updated || !data.units) return;
        var units = Object.keys(data.units).filter(function (u) { return calI18n.units[u]; });
        if (!units.length) return;
        availability = {};
        units.forEach(function (u) { availability[u] = data.units[u].booked || []; });
        buildCalendar(units, data.updated);
      })
      .catch(function () { /* nessun dato: resta il riquadro «In arrivo» */ });

    var buildCalendar = function (units, updated) {
      calBox.querySelectorAll('[data-cal-soon]').forEach(function (el) { el.hidden = true; });
      doc.querySelectorAll('[data-intro-soon]').forEach(function (el) { el.hidden = true; });
      doc.querySelectorAll('[data-intro-live]').forEach(function (el) { el.hidden = false; });
      var wrap = calBox.querySelector('.calendar');
      var tabs = wrap.querySelector('.calendar__tabs');
      var grid = wrap.querySelector('.calendar__grid');
      var title = wrap.querySelector('.calendar__month');
      var prev = wrap.querySelector('[data-cal-prev]');
      var next = wrap.querySelector('[data-cal-next]');
      var now = new Date();
      var first = new Date(now.getFullYear(), now.getMonth(), 1);
      var view = new Date(first);
      var maxMonths = 17;
      var unit = units[0];
      var today = isoDate(now);

      units.forEach(function (u) {
        var b = doc.createElement('button');
        b.type = 'button';
        b.className = 'calendar__tab';
        b.setAttribute('role', 'tab');
        b.dataset.unit = u;
        b.textContent = calI18n.units[u];
        b.addEventListener('click', function () { select(u); });
        tabs.appendChild(b);
      });
      if (units.length < 2) tabs.hidden = true;

      // intestazione giorni (lunedì → domenica)
      var weekdays = [];
      for (var i = 0; i < 7; i++) {
        weekdays.push(new Date(2024, 0, 1 + i).toLocaleDateString(locale, { weekday: 'narrow' }));
      }

      function render() {
        tabs.querySelectorAll('.calendar__tab').forEach(function (b) {
          b.setAttribute('aria-selected', String(b.dataset.unit === unit));
        });
        var label = view.toLocaleDateString(locale, { month: 'long', year: 'numeric' });
        title.textContent = label.charAt(0).toUpperCase() + label.slice(1);
        var html = '<div class="calendar__row calendar__row--head" role="row">';
        weekdays.forEach(function (w) { html += '<span role="columnheader">' + w + '</span>'; });
        html += '</div><div class="calendar__row" role="row">';
        var offset = (view.getDay() + 6) % 7;
        for (var k = 0; k < offset; k++) html += '<span role="gridcell" aria-hidden="true"></span>';
        var days = new Date(view.getFullYear(), view.getMonth() + 1, 0).getDate();
        for (var d = 1; d <= days; d++) {
          var date = new Date(view.getFullYear(), view.getMonth(), d);
          var iso = isoDate(date);
          var booked = nightBooked(unit, iso);
          var past = iso < today;
          var cls = 'calendar__day' + (booked ? ' is-booked' : '') + (past ? ' is-past' : '') + (iso === today ? ' is-today' : '');
          var aria = date.toLocaleDateString(locale, { day: 'numeric', month: 'long' }) + ': ' + (booked ? calI18n.booked : calI18n.free);
          html += '<span role="gridcell" class="' + cls + '" aria-label="' + aria + '">' + d + '</span>';
          if ((offset + d) % 7 === 0 && d < days) html += '</div><div class="calendar__row" role="row">';
        }
        html += '</div>';
        grid.innerHTML = html;
        var monthsAhead = (view.getFullYear() - first.getFullYear()) * 12 + view.getMonth() - first.getMonth();
        prev.disabled = monthsAhead <= 0;
        next.disabled = monthsAhead >= maxMonths;
      }

      function select(u) { if (availability[u]) { unit = u; render(); } }
      prev.addEventListener('click', function () { view.setMonth(view.getMonth() - 1); render(); });
      next.addEventListener('click', function () { view.setMonth(view.getMonth() + 1); render(); });

      wrap.querySelector('.calendar__updated').textContent = calI18n.updated + ' ' +
        new Date(updated).toLocaleString(locale, { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
      wrap.hidden = false;
      render();
      calendarApi = { select: select };
      if (typeof checkOverlap === 'function') checkOverlap();
    };
  }

  /* Modulo di richiesta → WhatsApp o email già compilati */
  var form = doc.getElementById('booking-form');
  if (!form) return;
  var i18n = JSON.parse(doc.getElementById('form-i18n').textContent);
  var checkin = form.elements.checkin;
  var checkout = form.elements.checkout;
  var dogCheck = doc.getElementById('dog-check');
  var dogField = doc.getElementById('dog-field');
  var dateError = doc.getElementById('date-error');

  function iso(d) {
    var off = d.getTimezoneOffset();
    return new Date(d.getTime() - off * 60000).toISOString().slice(0, 10);
  }
  function addDays(value, n) {
    var d = new Date(value + 'T12:00:00');
    d.setDate(d.getDate() + n);
    return iso(d);
  }
  function pretty(value) {
    if (!value) return '—';
    try {
      return new Date(value + 'T12:00:00').toLocaleDateString(i18n.locale.replace('_', '-'), { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' });
    } catch (e) { return value; }
  }

  var today = iso(new Date());
  checkin.min = today;
  checkout.min = addDays(today, 1);
  checkin.addEventListener('change', function () {
    if (checkin.value) {
      checkout.min = addDays(checkin.value, 1);
      if (checkout.value && checkout.value <= checkin.value) checkout.value = checkout.min;
    }
    validateDates();
  });
  checkout.addEventListener('change', validateDates);

  function validateDates() {
    var bad = checkin.value && checkout.value && checkout.value <= checkin.value;
    dateError.hidden = !bad;
    checkout.setAttribute('aria-invalid', bad ? 'true' : 'false');
    return !bad;
  }

  var dateWarn = doc.getElementById('date-warn');
  var aptSelect = form.elements.apartment;
  var checkOverlap = function () {
    if (!dateWarn) return;
    var unit = aptSelect.value;
    var clash = false;
    if (availability && availability[unit] && checkin.value && checkout.value && checkout.value > checkin.value) {
      for (var d = checkin.value; d < checkout.value; d = addDays(d, 1)) {
        if (nightBooked(unit, d)) { clash = true; break; }
      }
    }
    dateWarn.hidden = !clash;
  };
  [checkin, checkout].forEach(function (input) { input.addEventListener('change', checkOverlap); });
  aptSelect.addEventListener('change', function () {
    if (calendarApi) calendarApi.select(aptSelect.value);
    checkOverlap();
  });

  dogCheck.addEventListener('change', function () {
    dogField.hidden = !dogCheck.checked;
    if (dogCheck.checked) dogField.querySelector('input').focus();
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (!validateDates()) { checkout.focus(); return; }
    var via = (e.submitter && e.submitter.value) || 'whatsapp';
    var el = form.elements;
    var dog = dogCheck.checked ? i18n.yes + (el.dog_details.value.trim() ? ' (' + el.dog_details.value.trim() + ')' : '') : i18n.no;
    var lines = [
      i18n.greeting,
      '',
      i18n.checkin + ': ' + pretty(el.checkin.value),
      i18n.checkout + ': ' + pretty(el.checkout.value),
      i18n.guests + ': ' + el.guests.value,
      i18n.apartment + ': ' + el.apartment.options[el.apartment.selectedIndex].text,
      i18n.stay + ': ' + el.stay.value,
      '🐾 ' + i18n.dog + ': ' + dog
    ];
    if (el.name.value.trim()) lines.push(i18n.name + ': ' + el.name.value.trim());
    if (el.message.value.trim()) lines.push('', el.message.value.trim());
    var text = lines.join('\n');

    if (via === 'email') {
      window.location.href = 'mailto:' + form.dataset.email +
        '?subject=' + encodeURIComponent(i18n.subject + ' · A spasso con Daisy') +
        '&body=' + encodeURIComponent(text);
    } else {
      var number = (form.dataset.whatsapp || '').replace(/\D/g, '');
      window.open('https://wa.me/' + number + '?text=' + encodeURIComponent(text), '_blank', 'noopener');
    }
  });
})();
