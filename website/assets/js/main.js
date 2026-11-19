/* Wayline — shared site behaviour (nav, reveal, counters, pricing toggle, calculator) */
(function () {
  'use strict';

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- Header: scrolled state + mobile menu ---------- */
  var header = document.querySelector('[data-header]');
  if (header) {
    var toggle = header.querySelector('.nav-toggle');
    var menu = document.getElementById('nav-menu');

    var onScroll = function () {
      header.classList.toggle('is-scrolled', window.scrollY > 8);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });

    var setOpen = function (open) {
      header.classList.toggle('is-open', open);
      if (toggle) {
        toggle.setAttribute('aria-expanded', String(open));
        toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      }
    };

    if (toggle && menu) {
      toggle.addEventListener('click', function () {
        setOpen(!header.classList.contains('is-open'));
      });
      menu.addEventListener('click', function (e) {
        if (e.target.closest('a')) setOpen(false);
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && header.classList.contains('is-open')) {
          setOpen(false);
          toggle.focus();
        }
      });
      window.addEventListener('resize', function () {
        if (window.innerWidth > 980 && header.classList.contains('is-open')) setOpen(false);
      });
    }
  }

  /* ---------- Footer year ---------- */
  document.querySelectorAll('[data-year]').forEach(function (el) {
    el.textContent = String(new Date().getFullYear());
  });

  /* ---------- Scroll reveal ---------- */
  var reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window && !reduceMotion) {
    var revealIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-in');
          revealIO.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.06 });
    reveals.forEach(function (el) { revealIO.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add('is-in'); });
  }

  /* ---------- Spec counters (target-spec numbers only) ---------- */
  var counters = document.querySelectorAll('[data-count]');
  var runCounter = function (el) {
    var target = parseFloat(el.getAttribute('data-count'));
    var prefix = el.getAttribute('data-prefix') || '';
    var suffix = el.getAttribute('data-suffix') || '';
    if (!isFinite(target)) return;
    var start = null;
    var duration = 1100 + Math.min(target, 200) * 3;
    var frame = function (ts) {
      if (start === null) start = ts;
      var p = Math.min(1, (ts - start) / duration);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = prefix + Math.round(target * eased) + suffix;
      if (p < 1) requestAnimationFrame(frame);
    };
    el.textContent = prefix + '0' + suffix;
    requestAnimationFrame(frame);
  };
  if (counters.length && 'IntersectionObserver' in window && !reduceMotion) {
    var countIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          runCounter(entry.target);
          countIO.unobserve(entry.target);
        }
      });
    }, { threshold: 0.6 });
    counters.forEach(function (el) { countIO.observe(el); });
  }

  /* ---------- Pricing: monthly / yearly toggle for Plus ---------- */
  var billing = document.getElementById('billing-switch');
  if (billing) {
    var plusPrice = document.getElementById('plus-price');
    var plusPeriod = document.getElementById('plus-period');
    var plusNote = document.getElementById('plus-note');
    var lblMonthly = document.getElementById('bill-monthly');
    var lblYearly = document.getElementById('bill-yearly');

    var setYearly = function (yearly) {
      billing.setAttribute('aria-checked', String(yearly));
      if (plusPrice) plusPrice.textContent = yearly ? '$190' : '$19';
      if (plusPeriod) plusPeriod.textContent = yearly ? '/ year' : '/ month';
      if (plusNote) plusNote.textContent = yearly ? '≈ $15.83 / month — save $38' : 'or $190 billed yearly';
      if (lblMonthly) lblMonthly.classList.toggle('on', !yearly);
      if (lblYearly) lblYearly.classList.toggle('on', yearly);
    };

    billing.addEventListener('click', function () {
      setYearly(billing.getAttribute('aria-checked') !== 'true');
    });
    if (lblMonthly) {
      lblMonthly.style.cursor = 'pointer';
      lblMonthly.addEventListener('click', function () { setYearly(false); });
    }
    if (lblYearly) {
      lblYearly.style.cursor = 'pointer';
      lblYearly.addEventListener('click', function () { setYearly(true); });
    }
  }

  /* ---------- Business page: illustrative unit-economics calculator ---------- */
  var calc = document.getElementById('calc');
  if (calc) {
    var $ = function (id) { return document.getElementById(id); };
    var inputs = {
      devices: $('calc-devices'),
      attach: $('calc-attach'),
      fleet: $('calc-fleet')
    };
    var outs = {
      devices: $('calc-devices-out'),
      attach: $('calc-attach-out'),
      fleet: $('calc-fleet-out'),
      hw: $('calc-hw'),
      plus: $('calc-plus'),
      fleetArr: $('calc-fleet-arr'),
      gp: $('calc-gp'),
      recurring: $('calc-recurring'),
      total: $('calc-total')
    };

    var A = {
      devicePrice: 1199,
      hwMargin: 0.25,
      plusMonthly: 19,
      plusMargin: 0.50,
      fleetMonthly: 39,
      fleetMargin: 0.70
    };

    var money = function (n) {
      if (n >= 1e9) return '$' + (n / 1e9).toFixed(2) + 'B';
      if (n >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
      if (n >= 1e3) return '$' + Math.round(n / 1e3) + 'K';
      return '$' + Math.round(n);
    };
    var num = function (n) { return Math.round(n).toLocaleString('en-US'); };

    var update = function () {
      var consumer = Number(inputs.devices.value);
      var attach = Number(inputs.attach.value) / 100;
      var fleet = Number(inputs.fleet.value);

      var hwRevenue = (consumer + fleet) * A.devicePrice;
      var plusArr = consumer * attach * A.plusMonthly * 12;
      var fleetArr = fleet * A.fleetMonthly * 12;
      var total = hwRevenue + plusArr + fleetArr;
      var grossProfit = hwRevenue * A.hwMargin + plusArr * A.plusMargin + fleetArr * A.fleetMargin;
      var recurringShare = total > 0 ? (plusArr + fleetArr) / total : 0;

      outs.devices.textContent = num(consumer);
      outs.attach.textContent = Math.round(attach * 100) + '%';
      outs.fleet.textContent = num(fleet);
      outs.hw.textContent = money(hwRevenue);
      outs.plus.textContent = money(plusArr);
      outs.fleetArr.textContent = money(fleetArr);
      outs.gp.textContent = money(grossProfit) + ' (' + Math.round(total ? (grossProfit / total) * 100 : 0) + '%)';
      outs.recurring.textContent = Math.round(recurringShare * 100) + '%';
      outs.total.textContent = money(total);
    };

    Object.keys(inputs).forEach(function (k) {
      if (inputs[k]) inputs[k].addEventListener('input', update);
    });
    update();
  }
})();
