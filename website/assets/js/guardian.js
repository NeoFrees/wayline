/* Wayline — Guardian scenario player.
   Plays scripted, simulated incidents (crash, unresponsive driver, false alarm)
   to show how escalation works: a deterministic timer owns the decision to call;
   the AI only listens and drafts the brief. All names/coordinates illustrative. */
(function () {
  'use strict';

  var root = document.getElementById('gp');
  if (!root) return;

  var $ = function (id) { return document.getElementById(id); };
  var E = {
    stage: $('gp-stage'),
    state: $('gp-state'),
    status: $('gp-status'),
    sub: $('gp-substatus'),
    ring: $('gp-ring'),
    ringNum: $('gp-ring-num'),
    ringLabel: $('gp-ring-label'),
    peak: $('gp-m-peak'),
    dv: $('gp-m-dv'),
    speed: $('gp-m-speed'),
    loc: $('gp-m-loc'),
    chipLogic: $('gp-chip-logic'),
    chipAi: $('gp-chip-ai'),
    chipHaz: $('gp-chip-hazard'),
    map: $('gp-map'),
    mapLabel: $('gp-map-label'),
    timeline: $('gp-timeline'),
    transcript: $('gp-transcript'),
    replay: $('gp-replay')
  };
  for (var key in E) {
    if (Object.prototype.hasOwnProperty.call(E, key) && !E[key]) return; // markup mismatch: fail quietly
  }

  var buttons = Array.prototype.slice.call(root.querySelectorAll('.gp-scenario'));
  var CIRC = 2 * Math.PI * 52;
  var timers = [];
  var intervals = [];
  var current = null;

  /* ---------- scheduling ---------- */
  function later(ms, fn) { timers.push(setTimeout(fn, ms)); }
  function every(ms, fn) { var id = setInterval(fn, ms); intervals.push(id); return id; }
  function clearAll() {
    timers.forEach(clearTimeout);
    intervals.forEach(clearInterval);
    timers = [];
    intervals = [];
  }

  /* ---------- UI helpers ---------- */
  function tone(t) { E.stage.setAttribute('data-tone', t); }
  function flash() {
    E.stage.classList.remove('flash');
    void E.stage.offsetWidth; // restart animation
    E.stage.classList.add('flash');
  }
  function status(state, title, sub) {
    E.state.textContent = state;
    E.status.textContent = title;
    E.sub.textContent = sub;
  }
  function chip(el, t, text) {
    if (t) el.setAttribute('data-tone', t); else el.removeAttribute('data-tone');
    el.textContent = text;
  }
  function metrics(m) {
    E.peak.textContent = m.peak;
    E.dv.textContent = m.dv;
    E.speed.textContent = m.speed;
    E.loc.textContent = m.loc;
  }
  function ring(remaining, total, label) {
    E.ring.style.strokeDashoffset = String(CIRC * (1 - remaining / total));
    E.ringNum.textContent = String(remaining);
    if (label) E.ringLabel.textContent = label;
  }
  function share(on) {
    E.map.classList.toggle('is-sharing', on);
    E.mapLabel.textContent = on ? 'Live location · sharing' : 'Location · not shared';
  }

  var NAMES = {
    guardian: 'Guardian',
    driver: 'Driver',
    system: 'System',
    brief: 'Incident brief · AI-drafted',
    center: 'Response center'
  };
  function say(who, text, ts, muted) {
    var empty = E.transcript.querySelector('.gp-empty');
    if (empty) empty.remove();
    var msg = document.createElement('div');
    msg.className = 'msg' + (muted ? ' muted' : '');
    msg.setAttribute('data-who', who);
    var head = document.createElement('header');
    var w = document.createElement('span');
    w.className = 'who';
    w.textContent = NAMES[who] || who;
    var t = document.createElement('span');
    t.textContent = ts;
    head.appendChild(w);
    head.appendChild(t);
    var p = document.createElement('p');
    p.textContent = text;
    msg.appendChild(head);
    msg.appendChild(p);
    E.transcript.appendChild(msg);
    E.transcript.scrollTop = E.transcript.scrollHeight;
  }

  function renderTimeline(steps) {
    E.timeline.textContent = '';
    steps.forEach(function (s) {
      var li = document.createElement('li');
      li.setAttribute('data-state', 'pending');
      var dot = document.createElement('span');
      dot.className = 'tl-dot';
      dot.setAttribute('aria-hidden', 'true');
      var body = document.createElement('div');
      var tt = document.createElement('span');
      tt.className = 'tl-t';
      tt.textContent = s.t;
      var b = document.createElement('b');
      b.textContent = s.label;
      var sm = document.createElement('small');
      sm.textContent = s.detail;
      body.appendChild(tt);
      body.appendChild(b);
      body.appendChild(sm);
      li.appendChild(dot);
      li.appendChild(body);
      E.timeline.appendChild(li);
    });
  }
  function stepState(i, state) {
    var li = E.timeline.children[i];
    if (li) li.setAttribute('data-state', state);
  }
  function advance(i) {
    for (var k = 0; k < i; k++) stepState(k, 'done');
    stepState(i, 'active');
  }
  function finish(i) {
    for (var k = 0; k <= i; k++) stepState(k, 'done');
  }

  function countdown(total, tickMs) {
    var remaining = total;
    ring(remaining, total, 'sec to call');
    var id = every(tickMs, function () {
      remaining -= 1;
      ring(Math.max(remaining, 0), total);
      if (remaining <= 0) clearInterval(id);
    });
    return {
      stop: function () { clearInterval(id); return remaining; }
    };
  }

  function countNumber(el, from, to, ms, fmt) {
    var steps = Math.max(1, Math.round(ms / 60));
    var i = 0;
    el.textContent = fmt(from);
    var id = every(60, function () {
      i += 1;
      var p = i / steps;
      var eased = 1 - Math.pow(1 - p, 2);
      el.textContent = fmt(Math.round(from + (to - from) * Math.min(1, eased)));
      if (i >= steps) clearInterval(id);
    });
  }

  function reset() {
    clearAll();
    tone('ok');
    E.stage.classList.remove('flash');
    status('Armed', 'Guardian is standing by', 'Choose a scenario above to start the simulation.');
    ring(10, 10, 'sec check-in');
    metrics({ peak: '—', dv: '—', speed: '—', loc: '—' });
    chip(E.chipLogic, null, 'Escalation timer · armed');
    chip(E.chipAi, null, 'AI · idle');
    chip(E.chipHaz, null, 'Hazards · off');
    share(false);
    renderTimeline(SCENARIOS[current || 'crash'].steps); // pending preview of the escalation path
    E.transcript.textContent = '';
    var hint = document.createElement('p');
    hint.className = 'gp-empty';
    hint.textContent = 'Transcript will appear here.';
    E.transcript.appendChild(hint);
  }

  /* ---------- Scenarios ---------- */
  var SCENARIOS = {
    crash: {
      steps: [
        { t: 't+0.0s', label: 'Impact detected', detail: 'Peak 21.4 g · Δv 38 km/h · wheel speed corroborated' },
        { t: 't+0.4s', label: 'Voice check-in + hazards on', detail: '“Are you okay?” · 10-second window' },
        { t: 't+10.4s', label: 'No response — timer fires', detail: 'Deterministic escalation; the AI gets no vote' },
        { t: 't+11.2s', label: 'Incident brief drafted', detail: 'AI summary · template fallback ready' },
        { t: 't+11.6s', label: 'Emergency contacts alerted', detail: 'SMS + call with live location' },
        { t: 't+14.0s', label: 'Response center connected', detail: 'Plus · emergency services requested' }
      ],
      run: function () {
        later(300, function () {
          advance(0);
          tone('alert');
          flash();
          status('Crash detected', 'Impact detected', 'Crash signature confirmed by the IMU and wheel speed.');
          metrics({ peak: '21.4 g', dv: '38 km/h', speed: '54 → 0 km/h', loc: '37.7749, −122.4194' });
          chip(E.chipLogic, 'warn', 'Escalation timer · starting');
          say('system', 'Crash signature: peak 21.4 g, Δv 38 km/h, wheel speed 54 → 0 km/h in 0.9 s. Severity: serious.', 't+0.0s');
        });
        later(1100, function () {
          advance(1);
          chip(E.chipHaz, 'alert', 'Hazards · on');
          chip(E.chipAi, 'info', 'AI · listening');
          status('Check-in', 'Are you okay?', 'Listening for a response — say “I’m okay” to cancel.');
          say('guardian', 'Are you okay? I’ll call for help in 10 seconds. Say “I’m okay” to cancel.', 't+0.4s');
        });
        later(1500, function () {
          chip(E.chipLogic, 'warn', 'Escalation timer · running');
          countdown(10, 500);
        });
        later(4100, function () {
          say('system', 'No speech detected · no steering or pedal input.', 't+5.6s', true);
        });
        later(6550, function () {
          advance(2);
          tone('alert');
          chip(E.chipLogic, 'alert', 'Escalation timer · fired');
          status('Escalating', 'Calling for help', 'No response within 10 seconds.');
          say('guardian', 'No response. I’m calling for help now. Stay where you are if it’s safe.', 't+10.4s');
        });
        later(7300, function () {
          advance(3);
          chip(E.chipAi, 'info', 'AI · drafting brief');
        });
        later(8100, function () {
          chip(E.chipAi, 'ok', 'AI · brief ready');
          say('brief', 'Vehicle collision, serious severity (Δv 38 km/h). One occupant, unresponsive to voice check-in. Grey hatchback, hazards on. GPS 37.7749, −122.4194 (±4 m), heading north.', 't+11.2s');
        });
        later(8900, function () {
          advance(4);
          share(true);
          say('system', 'SMS + call → Jordan (partner) ✓ delivered · Riley (sister) ✓ delivered. Live location link shared.', 't+11.6s');
        });
        later(10300, function () {
          advance(5);
          tone('help');
          status('Help requested', 'Help is on the way', 'Response center connected · location updates every 60 s.');
          say('center', 'Wayline Response here. We have your location and the crash details, and we’ve requested emergency services. I’m staying on the line with you.', 't+14.0s');
        });
        later(11300, function () {
          finish(5);
          chip(E.chipLogic, 'ok', 'Escalation · complete');
          say('system', 'Guardian Reserve ready · location updates continue until help arrives.', 't+14.6s', true);
        });
      }
    },

    unresponsive: {
      steps: [
        { t: 't+0.0s', label: 'Eyes closed 2.1 s', detail: 'IR driver monitoring · visual alert' },
        { t: 't+3.0s', label: 'Audible alert', detail: 'Chime + “Eyes on the road”' },
        { t: 't+6.0s', label: 'Take control — no response', detail: 'No steering, pedal or gaze recovery' },
        { t: 't+8.0s', label: 'Emergency Stop Assist', detail: 'Slows in lane · hazards · horn pulses' },
        { t: 't+26s', label: 'Stopped · voice check-in', detail: 'Doors unlocked · 10-second window' },
        { t: 't+36s', label: 'Contacts + response center', detail: 'Brief: possible medical emergency' }
      ],
      run: function () {
        later(300, function () {
          advance(0);
          tone('warn');
          status('Drowsiness', 'Eyes closed for 2.1 seconds', 'Visual alert on the display.');
          metrics({ peak: '—', dv: '—', speed: '101 km/h', loc: '37.8044, −122.2712' });
          chip(E.chipLogic, 'warn', 'Attention · 58%');
          say('system', 'Driver monitoring: eyes closed 2.1 s, head pitched down, no steering input.', 't+0.0s');
        });
        later(1300, function () {
          advance(1);
          chip(E.chipLogic, 'warn', 'Attention · 31%');
          status('Alert', 'Eyes on the road, please', 'Audible alert.');
          say('guardian', 'Eyes on the road, please.', 't+3.0s');
        });
        later(2300, function () {
          advance(2);
          tone('alert');
          flash();
          chip(E.chipLogic, 'alert', 'Attention · 0%');
          status('Unresponsive', 'Take control immediately', 'No response to alerts.');
          say('guardian', 'Take control now!', 't+6.0s');
        });
        later(3300, function () {
          advance(3);
          chip(E.chipHaz, 'alert', 'Hazards · on');
          status('Emergency Stop Assist', 'Slowing to a stop in lane', 'Lane centering stays active · hazards on · horn pulses.');
          say('system', 'Emergency Stop Assist: holding the lane, decelerating smoothly, hazards on, horn pulsing.', 't+8.0s');
          countNumber(E.speed, 101, 0, 3200, function (v) { return v + ' km/h'; });
        });
        later(6700, function () {
          advance(4);
          tone('warn');
          chip(E.chipAi, 'info', 'AI · listening');
          chip(E.chipLogic, 'warn', 'Escalation timer · running');
          status('Check-in', 'Vehicle stopped safely', 'Doors unlocked · checking on the driver.');
          say('guardian', 'I’ve stopped the car. Are you okay? I’ll call for help in 10 seconds.', 't+26s');
        });
        later(7100, function () { countdown(10, 500); });
        later(12150, function () {
          advance(5);
          tone('alert');
          chip(E.chipLogic, 'alert', 'Escalation timer · fired');
          chip(E.chipAi, 'info', 'AI · drafting brief');
          status('Escalating', 'Calling for help', 'No response within 10 seconds.');
          say('guardian', 'No response. Calling for help now.', 't+36s');
        });
        later(12900, function () {
          chip(E.chipAi, 'ok', 'AI · brief ready');
          say('brief', 'Driver became unresponsive at highway speed; vehicle brought to a controlled stop in its lane with hazards on. Possible medical emergency. One occupant. GPS 37.8044, −122.2712 (±3 m).', 't+36.8s');
        });
        later(13600, function () {
          share(true);
          say('system', 'SMS + call → Jordan (partner) ✓ delivered · Riley (sister) ✓ delivered.', 't+37.2s');
        });
        later(14800, function () {
          tone('help');
          status('Help requested', 'Help is on the way', 'Response center connected.');
          say('center', 'Wayline Response here. We have your location and we’ve requested emergency medical services. Help is on the way.', 't+39.5s');
        });
        later(15600, function () {
          finish(5);
          chip(E.chipLogic, 'ok', 'Escalation · complete');
        });
      }
    },

    falsealarm: {
      steps: [
        { t: 't+0.0s', label: 'Impact detected', detail: 'Peak 6.8 g · Δv 11 km/h · minor' },
        { t: 't+0.4s', label: 'Voice check-in', detail: '10-second window · hazards on' },
        { t: 't+3.4s', label: 'Driver: “I’m okay”', detail: 'AI intent and on-device keyword check agree' },
        { t: 't+3.6s', label: 'Cancelled — nobody contacted', detail: 'Incident clip saved to your drive log' }
      ],
      run: function () {
        var cd = null;
        later(300, function () {
          advance(0);
          tone('warn');
          status('Impact', 'Minor impact detected', 'Low-speed collision signature.');
          metrics({ peak: '6.8 g', dv: '11 km/h', speed: '23 → 0 km/h', loc: '37.7599, −122.4148' });
          chip(E.chipLogic, 'warn', 'Escalation timer · starting');
          say('system', 'Impact: peak 6.8 g, Δv 11 km/h, wheel speed 23 → 0 km/h. Severity: minor.', 't+0.0s');
        });
        later(1100, function () {
          advance(1);
          chip(E.chipHaz, 'alert', 'Hazards · on');
          chip(E.chipAi, 'info', 'AI · listening');
          status('Check-in', 'Are you okay?', 'Listening for a response.');
          say('guardian', 'Are you okay? I’ll call for help in 10 seconds. Say “I’m okay” to cancel.', 't+0.4s');
        });
        later(1500, function () {
          chip(E.chipLogic, 'warn', 'Escalation timer · running');
          cd = countdown(10, 500);
        });
        later(3000, function () {
          advance(2);
          say('driver', 'I’m okay — it was just a fender bender.', 't+3.4s');
          chip(E.chipAi, 'ok', 'AI · intent: cancel (0.97)');
        });
        later(3500, function () {
          if (cd) cd.stop();
          tone('ok');
          E.ringLabel.textContent = 'cancelled';
          chip(E.chipLogic, 'ok', 'Rule check · no distress words');
          say('system', 'Cancel accepted: the AI intent and the on-device keyword check agree. Words like “help” or “hurt” would have overridden a cancel.', 't+3.5s');
        });
        later(4300, function () {
          advance(3);
          status('Cancelled', 'Glad you’re okay', 'No one was contacted.');
          chip(E.chipHaz, null, 'Hazards · off');
          say('guardian', 'Glad you’re okay. I’ve cancelled — no one was contacted. I saved a clip of the incident to your drive log.', 't+3.6s');
        });
        later(4900, function () {
          finish(3);
          chip(E.chipAi, null, 'AI · idle');
        });
      }
    }
  };

  function play(name) {
    var sc = SCENARIOS[name];
    if (!sc) return;
    reset();
    current = name;
    buttons.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-scenario') === name));
    });
    renderTimeline(sc.steps);
    E.replay.disabled = false;
    sc.run();
  }

  buttons.forEach(function (b) {
    b.addEventListener('click', function () { play(b.getAttribute('data-scenario')); });
  });
  E.replay.addEventListener('click', function () {
    if (current) play(current);
  });

  reset();
})();
