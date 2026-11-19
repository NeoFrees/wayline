from wayline.monitoring.driver import AlertLevel, DriverMonitor, DriverObservation

DT = 0.05
ASLEEP = DriverObservation(eyes_closed=0.95)
LOOKING_AWAY = DriverObservation(gaze_on_road=False)
ATTENTIVE = DriverObservation()


def run(monitor, obs, seconds, active=True):
    state = None
    for _ in range(int(round(seconds / DT))):
        state = monitor.update(obs, DT, active=active)
    return state


def test_escalation_timeline_for_a_sleeping_driver():
    m = DriverMonitor()
    assert run(m, ASLEEP, 1.0).level == AlertLevel.NONE
    assert run(m, ASLEEP, 0.6).level == AlertLevel.AUDIBLE      # microsleep > 1.5 s
    assert run(m, ASLEEP, 7.5).level == AlertLevel.CRITICAL     # awareness hits 0 at 9 s
    s = run(m, ASLEEP, 6.0)
    assert s.unresponsive


def test_looking_away_gives_visual_then_audible():
    m = DriverMonitor()
    assert run(m, LOOKING_AWAY, 3.5).level == AlertLevel.VISUAL
    assert run(m, LOOKING_AWAY, 3.0).level == AlertLevel.AUDIBLE


def test_attention_restores_awareness():
    m = DriverMonitor()
    run(m, LOOKING_AWAY, 8.0)
    s = run(m, ATTENTIVE, 0.6)
    assert s.level == AlertLevel.NONE and s.awareness == 1.0


def test_deliberate_input_counts_as_a_response():
    m = DriverMonitor()
    run(m, ASLEEP, 12.0)
    s = m.update(DriverObservation(eyes_closed=0.95, interacted=True), DT)
    assert s.awareness == 1.0 and not s.unresponsive


def test_never_unresponsive_when_wayline_is_not_steering():
    m = DriverMonitor()
    s = run(m, ASLEEP, 30.0, active=False)
    assert not s.unresponsive and s.level < AlertLevel.CRITICAL
