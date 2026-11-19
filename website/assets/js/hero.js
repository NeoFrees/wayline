/* Wayline — hero canvas: a night road with a live lane-detection overlay.
   Pure canvas 2D, no dependencies. Pauses when off-screen, when the tab is
   hidden, and renders a single still frame for prefers-reduced-motion. */
(function () {
  'use strict';

  var canvas = document.getElementById('hero-canvas');
  if (!canvas || !canvas.getContext) return;
  var ctx = canvas.getContext('2d');
  var motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  var speedEl = document.getElementById('hud-speed');
  var leadEl = document.getElementById('hud-lead');
  var offsetEl = document.getElementById('hud-offset');

  // World constants (meters, m/s)
  var LANE = 3.7;
  var CAM_H = 1.3;
  var Z_NEAR = 2.4;
  var Z_FAR = 260;
  var DET_RANGE = 85;
  var SPEED = 27.7;
  var DASH = 3;
  var PERIOD = 12;
  var GROWTH = 1.045;
  var EDGE = 1.5 * LANE + 1.0;

  // Screen state
  var W = 1, H = 1, F = 600, HZ = 300, CX = 300;
  var zs = [], xs = [];
  var dist = 0, time = 0, lastTs = 0, raf = 0, hudAcc = 0;
  var off = 0, leadZ = 36;
  var inView = true, pageVisible = !document.hidden;
  var stars = [], skyline = [];

  function prng(seed) {
    var s = seed % 2147483647;
    if (s <= 0) s += 2147483646;
    return function () {
      s = (s * 16807) % 2147483647;
      return (s - 1) / 2147483646;
    };
  }

  (function buildScenery() {
    var r = prng(7);
    for (var i = 0; i < 160; i++) {
      stars.push({ x: r(), y: r(), a: 0.1 + r() * 0.45, p: r() * Math.PI * 2 });
    }
    var x = -0.08;
    while (x < 1.08) {
      var w = 0.008 + r() * 0.03;
      skyline.push({ x: x, w: w, h: 0.004 + Math.pow(r(), 2.4) * 0.055, lit: r(), lx: r() });
      x += w + r() * 0.004;
    }
  })();

  function resize() {
    var rect = canvas.getBoundingClientRect();
    W = Math.max(1, rect.width);
    H = Math.max(1, rect.height);
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    var narrow = W < 720;
    HZ = H * (narrow ? 0.62 : 0.56);
    F = Math.max(W * 0.6, H * 0.95);
    CX = W * (narrow ? 0.5 : 0.64);

    zs = [];
    for (var z = Z_NEAR; z < Z_FAR; z *= GROWTH) zs.push(z);
    zs.push(Z_FAR);
    xs = new Array(zs.length);
  }

  // Road curvature as a function of distance traveled (1/m)
  function kappa(s) {
    return 0.0012 * Math.sin(s / 610) + 0.0006 * Math.sin(s / 233 + 1.7);
  }

  // Lateral position of the lane center (vehicle frame) at each sampled depth
  function computeRoad() {
    var heading = 0, x = 0, prevZ = 0;
    for (var i = 0; i < zs.length; i++) {
      var z = zs[i];
      var dz = z - prevZ;
      var k = kappa(dist + prevZ + dz * 0.5);
      x += heading * dz + 0.5 * k * dz * dz;
      heading += k * dz;
      xs[i] = x - off;
      prevZ = z;
    }
  }

  function centerAt(z) {
    if (z <= zs[0]) return xs[0];
    var i = Math.floor(Math.log(z / Z_NEAR) / Math.log(GROWTH));
    if (i < 0) i = 0;
    if (i > zs.length - 2) i = zs.length - 2;
    var z0 = zs[i], z1 = zs[i + 1];
    var t = Math.min(1, Math.max(0, (z - z0) / (z1 - z0)));
    return xs[i] + (xs[i + 1] - xs[i]) * t;
  }

  function sx(x, z) { return CX + (x * F) / z; }
  function sy(z, h) { return HZ + ((CAM_H - (h || 0)) * F) / z; }

  function roundRect(x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // Filled strip along the road at a lateral offset (used for paint markings)
  function strip(offset, width, z0, z1, style) {
    z0 = Math.max(z0, Z_NEAR);
    z1 = Math.min(z1, Z_FAR);
    if (z1 <= z0) return;
    var steps = Math.max(2, Math.ceil(Math.log(z1 / z0) / Math.log(GROWTH)) + 1);
    var k, z, x;
    ctx.beginPath();
    for (k = 0; k <= steps; k++) {
      z = z0 * Math.pow(z1 / z0, k / steps);
      x = centerAt(z) + offset - width / 2;
      if (k === 0) ctx.moveTo(sx(x, z), sy(z)); else ctx.lineTo(sx(x, z), sy(z));
    }
    for (k = steps; k >= 0; k--) {
      z = z0 * Math.pow(z1 / z0, k / steps);
      x = centerAt(z) + offset + width / 2;
      ctx.lineTo(sx(x, z), sy(z));
    }
    ctx.closePath();
    ctx.fillStyle = style;
    ctx.fill();
  }

  function drawSky(vpx) {
    var g = ctx.createLinearGradient(0, 0, 0, HZ);
    g.addColorStop(0, '#03050a');
    g.addColorStop(0.7, '#070c16');
    g.addColorStop(1, '#0d1728');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, HZ + 1);

    for (var i = 0; i < stars.length; i++) {
      var s = stars[i];
      var a = s.a * (0.7 + 0.3 * Math.sin(time * 1.3 + s.p));
      ctx.fillStyle = 'rgba(200,215,235,' + a.toFixed(3) + ')';
      ctx.fillRect(s.x * W, s.y * HZ * 0.82, 1.2, 1.2);
    }

    var glow = ctx.createRadialGradient(vpx, HZ, 0, vpx, HZ, Math.max(W, H) * 0.6);
    glow.addColorStop(0, 'rgba(60,242,176,0.10)');
    glow.addColorStop(0.3, 'rgba(90,168,255,0.05)');
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, W, H);

    var shift = (vpx - CX) * 0.22;
    for (var j = 0; j < skyline.length; j++) {
      var b = skyline[j];
      var bx = b.x * W + shift;
      var bh = b.h * H;
      ctx.fillStyle = '#060a11';
      ctx.fillRect(bx, HZ - bh, b.w * W + 1, bh + 1);
      if (b.lit > 0.78 && bh > 6) {
        ctx.fillStyle = 'rgba(255,181,71,0.45)';
        ctx.fillRect(bx + b.w * W * (0.2 + b.lx * 0.6), HZ - bh * 0.62, 1.6, 1.6);
      }
    }

    ctx.fillStyle = '#05080d';
    ctx.fillRect(0, HZ, W, H - HZ);
  }

  function drawRoad() {
    var n = zs.length, i;
    ctx.beginPath();
    for (i = 0; i < n; i++) {
      var p = sx(xs[i] - EDGE, zs[i]);
      if (i === 0) ctx.moveTo(p, sy(zs[i])); else ctx.lineTo(p, sy(zs[i]));
    }
    for (i = n - 1; i >= 0; i--) ctx.lineTo(sx(xs[i] + EDGE, zs[i]), sy(zs[i]));
    ctx.closePath();
    var g = ctx.createLinearGradient(0, HZ, 0, H);
    g.addColorStop(0, '#0a0f16');
    g.addColorStop(1, '#151d28');
    ctx.fillStyle = g;
    ctx.fill();

    // Paint markings, fading into the distance
    var paint = ctx.createLinearGradient(0, H, 0, HZ);
    paint.addColorStop(0, 'rgba(226,233,242,0.85)');
    paint.addColorStop(0.7, 'rgba(226,233,242,0.3)');
    paint.addColorStop(1, 'rgba(226,233,242,0)');

    strip(-1.5 * LANE, 0.15, Z_NEAR, Z_FAR, paint);
    strip(1.5 * LANE, 0.15, Z_NEAR, Z_FAR, paint);

    var k0 = Math.floor((dist + Z_NEAR) / PERIOD) - 1;
    var k1 = Math.floor((dist + Z_FAR) / PERIOD) + 1;
    for (var k = k0; k <= k1; k++) {
      var z0 = k * PERIOD - dist;
      var z1 = z0 + DASH;
      if (z1 <= Z_NEAR || z0 >= Z_FAR) continue;
      strip(-0.5 * LANE, 0.14, z0, z1, paint);
      strip(0.5 * LANE, 0.14, z0, z1, paint);
    }

    // Roadside reflector posts
    var p0 = Math.ceil((dist + Z_NEAR + 1) / 30);
    var p1 = Math.floor((dist + 170) / 30);
    for (var q = p0; q <= p1; q++) {
      var z = q * 30 - dist;
      var fade = Math.max(0, 1 - z / 170);
      var c = centerAt(z);
      for (var side = -1; side <= 1; side += 2) {
        var px = sx(c + side * (EDGE + 0.7), z);
        var yb = sy(z, 0);
        var yt = sy(z, 0.95);
        ctx.strokeStyle = 'rgba(110,125,148,' + (0.55 * fade).toFixed(3) + ')';
        ctx.lineWidth = Math.max(1, (0.1 * F) / z);
        ctx.beginPath();
        ctx.moveTo(px, yb);
        ctx.lineTo(px, yt);
        ctx.stroke();
        ctx.fillStyle = 'rgba(255,181,71,' + (0.9 * fade).toFixed(3) + ')';
        ctx.beginPath();
        ctx.arc(px, yt + ((0.12 * F) / z), Math.max(0.8, (0.06 * F) / z), 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  function pathAt(z) {
    // Planned path: starts at the vehicle (x = 0) and converges to lane center
    return centerAt(z) + off * Math.exp(-z / 14);
  }

  function drawOverlay() {
    var zEnd = DET_RANGE;
    var yEnd = sy(zEnd);
    var steps = 46, k, z;

    // Planned-path corridor
    ctx.beginPath();
    for (k = 0; k <= steps; k++) {
      z = Z_NEAR * Math.pow(zEnd / Z_NEAR, k / steps);
      var xl = sx(pathAt(z) - 0.9, z);
      if (k === 0) ctx.moveTo(xl, sy(z)); else ctx.lineTo(xl, sy(z));
    }
    for (k = steps; k >= 0; k--) {
      z = Z_NEAR * Math.pow(zEnd / Z_NEAR, k / steps);
      ctx.lineTo(sx(pathAt(z) + 0.9, z), sy(z));
    }
    ctx.closePath();
    var cg = ctx.createLinearGradient(0, H, 0, yEnd);
    cg.addColorStop(0, 'rgba(60,242,176,0.24)');
    cg.addColorStop(1, 'rgba(60,242,176,0)');
    ctx.fillStyle = cg;
    ctx.fill();

    // Detected lane lines (glow + core)
    var lg = ctx.createLinearGradient(0, H, 0, yEnd);
    lg.addColorStop(0, 'rgba(60,242,176,0.95)');
    lg.addColorStop(0.75, 'rgba(60,242,176,0.35)');
    lg.addColorStop(1, 'rgba(60,242,176,0)');
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    for (var side = -1; side <= 1; side += 2) {
      ctx.beginPath();
      for (k = 0; k <= steps; k++) {
        z = Z_NEAR * Math.pow(zEnd / Z_NEAR, k / steps);
        var x = sx(centerAt(z) + side * LANE * 0.5, z);
        if (k === 0) ctx.moveTo(x, sy(z)); else ctx.lineTo(x, sy(z));
      }
      ctx.strokeStyle = lg;
      ctx.globalAlpha = 0.22;
      ctx.lineWidth = 9;
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.lineWidth = 2.2;
      ctx.stroke();
    }

    // Detection points anchored to the world
    var d0 = Math.ceil((dist + 4) / 5);
    var d1 = Math.floor((dist + zEnd) / 5);
    for (var d = d0; d <= d1; d++) {
      z = d * 5 - dist;
      var a = 0.9 * (1 - z / zEnd);
      var r = Math.min(3.2, Math.max(1, 30 / z));
      ctx.fillStyle = 'rgba(233,238,245,' + a.toFixed(3) + ')';
      for (var s2 = -1; s2 <= 1; s2 += 2) {
        ctx.beginPath();
        ctx.arc(sx(centerAt(z) + s2 * LANE * 0.5, z), sy(z), r, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  }

  function drawLead() {
    var z = leadZ;
    var c = centerAt(z);
    var xL = sx(c - 0.92, z);
    var xR = sx(c + 0.92, z);
    var yB = sy(z, 0.22);
    var yT = sy(z, 1.48);
    var w = xR - xL;
    var h = yB - yT;

    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.fillRect(xL - w * 0.05, yB - h * 0.02, w * 1.1, h * 0.14);

    var body = ctx.createLinearGradient(0, yT, 0, yB);
    body.addColorStop(0, '#131a24');
    body.addColorStop(1, '#090d13');
    ctx.fillStyle = body;
    roundRect(xL, yT + h * 0.06, w, h * 0.94, w * 0.1);
    ctx.fill();

    ctx.fillStyle = '#1b2533';
    roundRect(xL + w * 0.15, yT + h * 0.12, w * 0.7, h * 0.28, w * 0.06);
    ctx.fill();

    var ty = yT + h * 0.55;
    var th = Math.max(1.5, h * 0.1);
    var tw = w * 0.2;
    var lights = [xL + w * 0.05, xR - w * 0.05 - tw];
    for (var i = 0; i < 2; i++) {
      var gx = lights[i] + tw / 2;
      var glow = ctx.createRadialGradient(gx, ty + th / 2, 0, gx, ty + th / 2, w * 0.45);
      glow.addColorStop(0, 'rgba(255,59,79,0.45)');
      glow.addColorStop(1, 'rgba(255,59,79,0)');
      ctx.fillStyle = glow;
      ctx.fillRect(gx - w * 0.45, ty + th / 2 - w * 0.45, w * 0.9, w * 0.9);
      ctx.fillStyle = '#ff3b4f';
      ctx.fillRect(lights[i], ty, tw, th);
    }

    // Detection brackets
    var pad = w * 0.12;
    var bx0 = xL - pad, bx1 = xR + pad, by0 = yT - pad, by1 = yB + pad * 0.6;
    var len = Math.max(6, w * 0.22);
    ctx.strokeStyle = 'rgba(90,168,255,0.95)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(bx0, by0 + len); ctx.lineTo(bx0, by0); ctx.lineTo(bx0 + len, by0);
    ctx.moveTo(bx1 - len, by0); ctx.lineTo(bx1, by0); ctx.lineTo(bx1, by0 + len);
    ctx.moveTo(bx0, by1 - len); ctx.lineTo(bx0, by1); ctx.lineTo(bx0 + len, by1);
    ctx.moveTo(bx1 - len, by1); ctx.lineTo(bx1, by1); ctx.lineTo(bx1, by1 - len);
    ctx.stroke();

    ctx.font = '600 11px "JetBrains Mono", ui-monospace, monospace';
    ctx.fillStyle = 'rgba(90,168,255,0.95)';
    ctx.textBaseline = 'bottom';
    ctx.fillText('LEAD ' + Math.round(z) + ' m', bx0, by0 - 6);
  }

  function drawFade() {
    var g = ctx.createLinearGradient(0, H * 0.8, 0, H);
    g.addColorStop(0, 'rgba(5,7,11,0)');
    g.addColorStop(1, 'rgba(5,7,11,1)');
    ctx.fillStyle = g;
    ctx.fillRect(0, H * 0.8, W, H * 0.2 + 1);
  }

  function draw() {
    off = 0.16 * Math.sin(time * 0.37) + 0.05 * Math.sin(time * 1.3);
    leadZ = 36 + 7 * Math.sin(time * 0.18);
    computeRoad();
    var vpx = sx(xs[xs.length - 1], Z_FAR);
    ctx.clearRect(0, 0, W, H);
    drawSky(vpx);
    drawRoad();
    drawOverlay();
    drawLead();
    drawFade();
  }

  function updateHud() {
    if (speedEl) speedEl.textContent = String(62 + Math.round(Math.sin(time * 0.21) * 1.4));
    if (leadEl) leadEl.textContent = String(Math.round(leadZ));
    if (offsetEl) offsetEl.textContent = (off >= 0 ? '+' : '−') + Math.abs(off).toFixed(2);
  }

  function shouldRun() {
    return inView && pageVisible && !motion.matches;
  }

  function frame(ts) {
    raf = 0;
    var dt = lastTs ? Math.min(0.05, (ts - lastTs) / 1000) : 0.016;
    lastTs = ts;
    time += dt;
    dist += SPEED * dt;
    hudAcc += dt;
    draw();
    if (hudAcc > 0.35) {
      hudAcc = 0;
      updateHud();
    }
    if (shouldRun()) raf = requestAnimationFrame(frame);
  }

  function sync() {
    if (shouldRun()) {
      if (!raf) {
        lastTs = 0;
        raf = requestAnimationFrame(frame);
      }
    } else {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      draw();
    }
  }

  // Init
  time = 12;
  dist = 400;
  resize();
  draw();
  updateHud();

  var resizeQueued = false;
  var onResize = function () {
    if (resizeQueued) return;
    resizeQueued = true;
    requestAnimationFrame(function () {
      resizeQueued = false;
      resize();
      draw();
    });
  };
  if ('ResizeObserver' in window) {
    new ResizeObserver(onResize).observe(canvas);
  } else {
    window.addEventListener('resize', onResize);
  }

  if ('IntersectionObserver' in window) {
    new IntersectionObserver(function (entries) {
      inView = entries[0].isIntersecting;
      sync();
    }, { threshold: 0 }).observe(canvas);
  }

  document.addEventListener('visibilitychange', function () {
    pageVisible = !document.hidden;
    sync();
  });

  if (motion.addEventListener) motion.addEventListener('change', sync);
  else if (motion.addListener) motion.addListener(sync);

  sync();
})();
