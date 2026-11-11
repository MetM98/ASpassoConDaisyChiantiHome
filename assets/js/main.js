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
      i18n.apartment + ': ' + el.apartment.value,
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
