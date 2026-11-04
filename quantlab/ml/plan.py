"""Training plan shared by the CLI and the scheduled trainer. Every result is a `candidate`:
nothing here promotes a model or changes what a session trades."""

from __future__ import annotations

from quantlab.ml.models import ALGOS
from quantlab.models import Job, TrainingJob

# 1h is left out on purpose: .ai/research/2026-11-strategy-optimization.md found it lost heavily
# to costs. Horizons are about one day on 4h and one week on 1d.
PLAN_TIMEFRAMES = {"4h": {"horizon": 6, "candles": 15000}, "1d": {"horizon": 5, "candles": 2500}}
HYPER = {"lstm": {"epochs": 6}}


def enqueue_training(db, pairs: list[str], timeframes: dict | None = None, algos: tuple[str, ...] = ALGOS) -> int:
    """Queues missing work only, so a repeat call cannot pile up duplicate jobs."""
    timeframes = timeframes or PLAN_TIMEFRAMES
    created = 0
    with db.session() as s:
        pending = {(t.algo, t.pair, t.timeframe) for t in s.query(TrainingJob).filter(TrainingJob.status.in_(("queued", "running")))}
        for tf, cfg in timeframes.items():
            for pair in pairs:
                for algo in algos:
                    if (algo, pair, tf) in pending:
                        continue
                    job = Job(kind="train", payload={})
                    s.add(job)
                    s.flush()
                    t = TrainingJob(job_id=job.id, algo=algo, pair=pair, timeframe=tf, status="queued")
                    s.add(t)
                    s.flush()
                    job.payload = {"training_id": t.id, "horizon": cfg["horizon"], "candles": cfg["candles"], "hyper": HYPER.get(algo, {})}
                    created += 1
    return created
