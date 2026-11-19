/* Wayline — lane-fit visualization (bird's-eye view).
   Noisy lane-marking detections scroll toward the car; every frame each lane
   line is re-fitted with a robust quadratic least-squares fit, and the
   readouts (offset, heading, curve radius, fit RMS, steer request) update. */
(function () {
  'use strict';

  var canvas = document.getElementById('lane-fit-canvas');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var byId = function (id) { return document.getElementById(id); };
  var ro = {
    offset: byId('ro-offset'),
    heading: byId('ro-heading'),
    radius: byId('ro-radius'),
    rms: byId('ro-rms'),
    torque: byId('ro-torque')
  };
  var marker = byId('offset-marker');
  var torqueFill = byId('torque-fill');

  var LANE = 3.7;
  var RANGE = 50;     // meters ahead shown
  var HALF = 4.6;     // meters either side shown
  var SPEED = 15;     // m/s (slowed for readability)
  var PAD_B = 30, PAD_T = 16;

  var W = 1, H = 1;
  var dist = 0, time = 0, lastTs = 0, raf = 0, uiAcc = 1;
  var inView = false, pageVisible = !document.hidden;
  var pts = { L: [], R: [] };
  var nextS = { L: 0, R: 0 };
  var fits = { L: null, R: null };
  var rmsVal = 0;

  function prng(seed) {
    var s = seed;
    return function () {
      s = (s * 16807) % 2147483647;
      return (s - 1) / 2147483646;
    };
  }
  var rnd = prng(11);
  function gauss() {
    var u = 1 - rnd(), v = rnd();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  // Ground-truth lane-center lateral position (m, left +) at distance x ahead
  function truth(x) {
    var t = time;
    var c = -(0.32 * Math.sin(t * 0.5) + 0.08 * Math.sin(t * 1.6));
    var b = -0.018 * Math.sin(t * 0.33 + 0.6);
    var a = 0.0011 * Math.sin(t * 0.17 + 1.2);
    return c + b * x + a * x * x;
  }

  function spawn(side) {
    var list = pts[side];
    while (nextS[side] < dist + RANGE) {
      var s = nextS[side];
      nextS[side] += 0.9 + rnd() * 1.1;
      if (side === 'L' && (((s % 12) + 12) % 12) > 4.5) continue; // dashed line gaps
      var outlier = rnd() < 0.05;
      list.push({
        s: s,
        n: outlier ? (rnd() < 0.5 ? -1 : 1) * (0.45 + rnd() * 0.5) : gauss() * (side === 'L' ? 0.075 : 0.06),
        out: false
      });
    }
    while (list.length && list[0].s < dist + 0.5) list.shift();
  }

  // Quadratic least squares in scaled coordinates (u = x / RANGE) for conditioning
  function quadFit(xsArr, ysArr) {
    var n = xsArr.length;
    if (n < 4) return null;
    var S0 = 0, S1 = 0, S2 = 0, S3 = 0, S4 = 0, T0 = 0, T1 = 0, T2 = 0;
    for (var i = 0; i < n; i++) {
      var u = xsArr[i] / RANGE, y = ysArr[i], u2 = u * u;
      S0 += 1; S1 += u; S2 += u2; S3 += u2 * u; S4 += u2 * u2;
      T0 += y; T1 += u * y; T2 += u2 * y;
    }
    var m = [S4, S3, S2, S3, S2, S1, S2, S1, S0];
    var D = det3(m);
    if (Math.abs(D) < 1e-12) return null;
    var au = det3([T2, S3, S2, T1, S2, S1, T0, S1, S0]) / D;
    var bu = det3([S4, T2, S2, S3, T1, S1, S2, T0, S0]) / D;
    var cu = det3([S4, S3, T2, S3, S2, T1, S2, S1, T0]) / D;
    return { a: au / (RANGE * RANGE), b: bu / RANGE, c: cu };
  }
  function det3(m) {
    return m[0] * (m[4] * m[8] - m[5] * m[7]) - m[1] * (m[3] * m[8] - m[5] * m[6]) + m[2] * (m[3] * m[7] - m[4] * m[6]);
  }
  function evalFit(f, x) { return f.a * x * x + f.b * x + f.c; }

  function fitSide(side) {
    var list = pts[side];
    var sign = side === 'L' ? 1 : -1;
    var X = [], Y = [], i;
    for (i = 0; i < list.length; i++) {
      var x = list[i].s - dist;
      if (x < 0.5 || x > RANGE) continue;
      X.push(x);
      Y.push(truth(x) + sign * LANE / 2 + list[i].n);
    }
    var f = quadFit(X, Y);
    if (!f) return { fit: null, sq: 0, n: 0 };
    // Reject outliers, then refit
    var X2 = [], Y2 = [];
    for (i = 0; i < list.length; i++) {
      var xx = list[i].s - dist;
      if (xx < 0.5 || xx > RANGE) continue;
      var yy = truth(xx) + sign * LANE / 2 + list[i].n;
      var bad = Math.abs(yy - evalFit(f, xx)) > 0.25;
      list[i].out = bad;
      if (!bad) { X2.push(xx); Y2.push(yy); }
    }
    var f2 = quadFit(X2, Y2) || f;
    var sq = 0;
    for (i = 0; i < X2.length; i++) {
      var r = Y2[i] - evalFit(f2, X2[i]);
      sq += r * r;
    }
    return { fit: f2, sq: sq, n: X2.length };
  }

  function update() {
    spawn('L');
    spawn('R');
    var l = fitSide('L');
    var r = fitSide('R');
    fits.L = l.fit;
    fits.R = r.fit;
    var n = l.n + r.n;
    rmsVal = n ? Math.sqrt((l.sq + r.sq) / n) : 0;
  }

  function center() {
    if (fits.L && fits.R) {
      return { a: (fits.L.a + fits.R.a) / 2, b: (fits.L.b + fits.R.b) / 2, c: (fits.L.c + fits.R.c) / 2 };
    }
    if (fits.L) return { a: fits.L.a, b: fits.L.b, c: fits.L.c - LANE / 2 };
    if (fits.R) return { a: fits.R.a, b: fits.R.b, c: fits.R.c + LANE / 2 };
    return null;
  }

  // ---- Drawing ----
  function resize() {
    var rect = canvas.getBoundingClientRect();
    W = Math.max(1, rect.width);
    H = Math.max(1, rect.height);
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  function px(lat) { return W / 2 - lat * (W / (2 * HALF)); }
  function py(x) { return H - PAD_B - x * ((H - PAD_B - PAD_T) / RANGE); }

  function strokeCurve(f, dx, style, width, dash) {
    ctx.beginPath();
    for (var x = 0; x <= RANGE; x += 1) {
      var X = px(evalFit(f, x) + (dx || 0)), Y = py(x);
      if (x === 0) ctx.moveTo(X, Y); else ctx.lineTo(X, Y);
    }
    ctx.setLineDash(dash || []);
    ctx.strokeStyle = style;
    ctx.lineWidth = width;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function draw() {
    ctx.clearRect(0, 0, W, H);

    // Grid
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(150,175,210,0.07)';
    ctx.beginPath();
    for (var lat = -4; lat <= 4; lat++) {
      var gx = Math.round(px(lat)) + 0.5;
      ctx.moveTo(gx, PAD_T); ctx.lineTo(gx, H - PAD_B + 8);
    }
    for (var m = 0; m <= RANGE; m += 10) {
      var gy = Math.round(py(m)) + 0.5;
      ctx.moveTo(0, gy); ctx.lineTo(W, gy);
    }
    ctx.stroke();
    ctx.font = '10px "JetBrains Mono", ui-monospace, monospace';
    ctx.fillStyle = 'rgba(117,131,154,0.9)';
    ctx.textBaseline = 'middle';
    for (m = 10; m <= RANGE; m += 10) ctx.fillText(m + ' m', W - 38, py(m) - 7);

    var c = center();

    // Ego lane fill
    if (fits.L && fits.R) {
      ctx.beginPath();
      var x;
      for (x = 0; x <= RANGE; x += 1) {
        var lx = px(evalFit(fits.L, x)), ly = py(x);
        if (x === 0) ctx.moveTo(lx, ly); else ctx.lineTo(lx, ly);
      }
      for (x = RANGE; x >= 0; x -= 1) ctx.lineTo(px(evalFit(fits.R, x)), py(x));
      ctx.closePath();
      var g = ctx.createLinearGradient(0, H, 0, 0);
      g.addColorStop(0, 'rgba(60,242,176,0.12)');
      g.addColorStop(1, 'rgba(60,242,176,0.02)');
      ctx.fillStyle = g;
      ctx.fill();
    }

    // Detections
    ['L', 'R'].forEach(function (side) {
      var sign = side === 'L' ? 1 : -1;
      var list = pts[side];
      for (var i = 0; i < list.length; i++) {
        var xx = list[i].s - dist;
        if (xx < 0 || xx > RANGE) continue;
        var X = px(truth(xx) + sign * LANE / 2 + list[i].n), Y = py(xx);
        if (list[i].out) {
          ctx.strokeStyle = 'rgba(255,181,71,0.9)';
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(X - 3, Y - 3); ctx.lineTo(X + 3, Y + 3);
          ctx.moveTo(X + 3, Y - 3); ctx.lineTo(X - 3, Y + 3);
          ctx.stroke();
        } else {
          ctx.fillStyle = 'rgba(233,238,245,0.7)';
          ctx.beginPath();
          ctx.arc(X, Y, 2.1, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    });

    // Fitted lines (glow + core)
    ['L', 'R'].forEach(function (side) {
      var f = fits[side];
      if (!f) return;
      strokeCurve(f, 0, 'rgba(60,242,176,0.18)', 8);
      strokeCurve(f, 0, 'rgba(60,242,176,0.95)', 2.2);
    });

    // Planned path: from the car back to lane center
    if (c) {
      var c0 = c.c;
      ctx.beginPath();
      for (var xp = 0; xp <= RANGE; xp += 1) {
        var lat2 = evalFit(c, xp) - c0 * Math.exp(-xp / 12);
        if (xp === 0) ctx.moveTo(px(lat2), py(xp)); else ctx.lineTo(px(lat2), py(xp));
      }
      ctx.setLineDash([6, 6]);
      ctx.strokeStyle = 'rgba(90,168,255,0.95)';
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Ego vehicle
    var carW = (1.85 * W) / (2 * HALF);
    var top = py(2.6);
    var bottom = py(-1.6);
    ctx.fillStyle = '#0f1722';
    ctx.strokeStyle = 'rgba(233,238,245,0.85)';
    ctx.lineWidth = 1.5;
    roundRectPath(W / 2 - carW / 2, top, carW, bottom - top, 7);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = 'rgba(90,168,255,0.9)';
    ctx.fillRect(W / 2 - carW * 0.3, top + 4, carW * 0.6, 3);

    // Model text
    if (c) {
      ctx.font = '11px "JetBrains Mono", ui-monospace, monospace';
      ctx.textBaseline = 'top';
      var fmt = function (v, d) { return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(d); };
      var label = 'center: y = ' + fmt(c.a, 4) + 'x² ' + fmt(c.b, 3) + 'x ' + fmt(c.c, 2);
      var tw = ctx.measureText(label).width;
      ctx.fillStyle = 'rgba(7,11,17,0.82)';
      roundRectPath(8, 6, tw + 12, 20, 6);
      ctx.fill();
      ctx.fillStyle = 'rgba(170,181,197,0.95)';
      ctx.fillText(label, 14, 10);
    }
  }

  function roundRectPath(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function updateUi() {
    var c = center();
    if (!c) return;
    var offset = -c.c;                 // + = car is left of lane center
    var psi = -Math.atan(c.b);         // + = car heading points right of the lane
    var curv = 2 * c.a;
    var side = function (v) { return Math.abs(v) < 0.005 ? '' : (v > 0 ? ' L' : ' R'); };

    if (ro.offset) ro.offset.textContent = Math.abs(offset).toFixed(2) + ' m' + side(offset);
    if (ro.heading) ro.heading.textContent = (psi >= 0 ? '+' : '−') + Math.abs(psi * 180 / Math.PI).toFixed(1) + '°';
    if (ro.radius) ro.radius.textContent = Math.abs(curv) < 1 / 4000 ? 'straight' : '~' + Math.round(1 / Math.abs(curv) / 10) * 10 + ' m';
    if (ro.rms) ro.rms.textContent = rmsVal.toFixed(2) + ' m';

    if (marker) {
      var clamped = Math.max(-1, Math.min(1, offset));
      marker.style.left = (50 - clamped * 46).toFixed(1) + '%';
    }

    // Illustrative steering request (+ = left): offset + heading feedback, curvature feed-forward
    var t = -0.85 * offset - 6 * psi + 160 * c.a;
    t = Math.max(-1, Math.min(1, t));
    if (ro.torque) ro.torque.textContent = Math.round(Math.abs(t) * 100) + '%' + (Math.abs(t) < 0.005 ? '' : (t > 0 ? ' L' : ' R'));
    if (torqueFill) {
      var w = Math.abs(t) * 50;
      torqueFill.style.width = w.toFixed(1) + '%';
      torqueFill.style.left = (t > 0 ? 50 - w : 50).toFixed(1) + '%';
    }
  }

  function shouldRun() { return inView && pageVisible && !motion.matches; }

  function frame(ts) {
    raf = 0;
    var dt = lastTs ? Math.min(0.05, (ts - lastTs) / 1000) : 0.016;
    lastTs = ts;
    time += dt;
    dist += SPEED * dt;
    uiAcc += dt;
    update();
    draw();
    if (uiAcc > 0.2) { uiAcc = 0; updateUi(); }
    if (shouldRun()) raf = requestAnimationFrame(frame);
  }

  function sync() {
    if (shouldRun()) {
      if (!raf) { lastTs = 0; raf = requestAnimationFrame(frame); }
    } else if (raf) {
      cancelAnimationFrame(raf);
      raf = 0;
    }
  }

  // Init with a populated, fitted still frame
  time = 3;
  dist = 0;
  nextS.L = 0.5;
  nextS.R = 0.5;
  resize();
  update();
  draw();
  updateUi();

  var queued = false;
  var onResize = function () {
    if (queued) return;
    queued = true;
    requestAnimationFrame(function () { queued = false; resize(); draw(); });
  };
  if ('ResizeObserver' in window) new ResizeObserver(onResize).observe(canvas);
  else window.addEventListener('resize', onResize);

  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      inView = entries[0].isIntersecting;
      sync();
    }, { threshold: 0.05 }).observe(canvas);
  } else {
    inView = true;
  }
  document.addEventListener('visibilitychange', function () {
    pageVisible = !document.hidden;
    sync();
  });
  if (motion.addEventListener) motion.addEventListener('change', sync);
  else if (motion.addListener) motion.addListener(sync);
  sync();
})();
