import numpy as np
import pandas as pd
import pytest

from quantlab.db import Database


def synthetic(n=1500, step=3600, seed=7, start=1_700_000_400):
    start = start - start % step
    r = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(0.0002 + 0.008 * np.sin(np.arange(n) / 40) * 0.2 + 0.006 * r.standard_normal(n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) * (1 + 0.002 * r.random(n))
    low = np.minimum(open_, close) * (1 - 0.002 * r.random(n))
    return pd.DataFrame({"ts": start + np.arange(n) * step, "open": open_, "high": high, "low": low, "close": close, "volume": 100 + 50 * r.random(n)})


@pytest.fixture
def candles():
    return synthetic()


@pytest.fixture
def db(tmp_path):
    d = Database(f"sqlite:///{tmp_path}/t.db")
    d.create_all()
    return d


@pytest.fixture(autouse=True)
def _real_registry_only(request, monkeypatch):
    """test_paper registers fake strategies on import. Keep them out of seeded worlds."""
    if request.module.__name__ in ("test_paper", "test_risk_live"):
        return
    from quantlab.strategies.base import REGISTRY

    for k in ("scripted", "exploding"):
        monkeypatch.delitem(REGISTRY, k, raising=False)
