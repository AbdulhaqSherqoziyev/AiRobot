from datetime import timedelta

from quantlab.config import Settings
from quantlab.models import ComponentHeartbeat, Notification, PaperSession, Strategy, StrategyVersion, utcnow
from quantlab.paper.engine import create_session
from quantlab.services import seed
from quantlab.watchdog import REPEAT_SECONDS, check, find_problems

S = Settings(watchlist=("BTC/USDT",), secret_key="x" * 40)


def beat(db, name, ago=0):
    with db.session() as s:
        s.merge(ComponentHeartbeat(name=name, at=utcnow() - timedelta(seconds=ago), detail={}))


def alerts(db):
    with db.session() as s:
        return [(n.title, n.text) for n in s.query(Notification).filter_by(category="system").order_by(Notification.id)]


def test_healthy_system_is_silent(db, tmp_path):
    for n in ("market", "paper", "jobs", "trainer"):
        beat(db, n, 5)
    assert check(db, tmp_path) == 0 and alerts(db) == []


def test_stuck_worker_alerts_once_repeats_rarely_and_reports_recovery(db, tmp_path):
    import time

    beat(db, "paper", 1200)
    now = time.time()
    assert check(db, tmp_path, now) == 1
    assert "Paper savdo" in alerts(db)[0][1] and "20 daqiqadan" in alerts(db)[0][1]
    assert check(db, tmp_path, now + 60) == 0  # no spam
    assert check(db, tmp_path, now + REPEAT_SECONDS + 1) == 1  # still broken: a rare reminder
    beat(db, "paper", 0)
    assert check(db, tmp_path, time.time()) == 1
    assert alerts(db)[-1][0] == "Muammo tuzaldi"
    assert check(db, tmp_path, time.time()) == 0


def test_busy_jobs_worker_is_not_a_false_alarm(db, tmp_path):
    beat(db, "jobs", 1800)  # a long training run
    with db.session() as s:
        assert find_problems(s, tmp_path) == {}


def test_stalled_candles_alert_but_a_normal_wait_does_not(db, tmp_path):
    import time

    seed(db, S)
    now = int(time.time())
    with db.session() as s:
        st = s.query(Strategy).filter_by(engine="ema_crossover").one()
        create_session(s, s.get(StrategyVersion, st.current_version_id), "BTC/USDT", "4h", 100.0, now=now)
    with db.session() as s:
        assert not find_problems(s, tmp_path, now)  # waiting for the next candle is normal
        assert "candles:4h" in find_problems(s, tmp_path, now + 3 * 14400)


def test_stopped_sessions_are_not_stalled(db, tmp_path):
    import time

    seed(db, S)
    now = int(time.time())
    with db.session() as s:
        st = s.query(Strategy).filter_by(engine="ema_crossover").one()
        ps = create_session(s, s.get(StrategyVersion, st.current_version_id), "BTC/USDT", "4h", 100.0, now=now)
        ps.status = "stopped"
    with db.session() as s:
        assert not find_problems(s, tmp_path, now + 10 * 14400)
