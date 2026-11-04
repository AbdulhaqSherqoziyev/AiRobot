"""Train, validate walk-forward, hold out a final out-of-sample block, register a version.
A new version is always a `candidate`: nothing replaces a promoted model automatically."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score

from quantlab.backtest.core import ExecConfig
from quantlab.backtest.engine import run_on_signals
from quantlab.market.store import CandleStore
from quantlab.ml.features import build_features, build_labels, walk_forward_folds
from quantlab.ml.models import make_model
from quantlab.models import MLModel, ModelVersion

ENTER_P, EXIT_P = 0.55, 0.48


def classification(y: np.ndarray, p: np.ndarray) -> dict:
    pred = (p >= 0.5).astype(int)
    out = {
        "accuracy": round(float(accuracy_score(y, pred)), 4), "precision": round(float(precision_score(y, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y, pred, zero_division=0)), 4), "f1": round(float(f1_score(y, pred, zero_division=0)), 4),
        "base_rate": round(float(y.mean()), 4), "samples": len(y),
    }
    if len(set(y.tolist())) > 1 and len(set(p.tolist())) > 1:
        out["auc"] = round(float(roc_auc_score(y, p)), 4)
    return out


def prepare(df: pd.DataFrame, horizon: int) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, np.ndarray]:
    X = build_features(df)
    y = build_labels(df, horizon)
    ok = X.notna().all(axis=1) & y.notna()
    idx = np.where(ok.to_numpy())[0]
    return X, X.to_numpy()[idx], y.to_numpy()[idx], idx


def train_version(db, data_dir: Path, store: CandleStore, algo: str, pair: str, timeframe: str, name: str | None = None, horizon: int = 6, oos_frac: float = 0.2, folds: int = 4, hyper: dict | None = None, seed: int = 42, progress=None) -> int:
    df = store.load(pair, timeframe)
    if len(df) < 1000:
        raise ValueError(f"need at least 1000 candles of {pair} {timeframe}, have {len(df)}. Sync data first.")
    Xf, X, y, idx = prepare(df, horizon)
    names = list(Xf.columns)
    split = int(len(X) * (1 - oos_frac))
    # The purge keeps training labels from reaching into the out-of-sample block.
    dev_X, dev_y = X[: split - horizon], y[: split - horizon]
    oos_X, oos_y = X[split:], y[split:]
    hyper = hyper or {}
    fwd = df["close"].pct_change().shift(-1).to_numpy()[idx]

    def fit(a, b, r):
        m = make_model(algo, seed=seed, **hyper)
        if algo == "rl":
            m.fit(a, b, names=names, returns=r)
        else:
            m.fit(a, b)
        return m

    ps, ys = [], []
    for k, (tr, te) in enumerate(walk_forward_folds(len(dev_X), folds, purge=horizon)):
        ps.append(fit(dev_X[tr], dev_y[tr], fwd[: split - horizon][tr]).predict_proba(dev_X[te]))
        ys.append(dev_y[te])
        if progress:
            progress(0.1 + 0.6 * (k + 1) / folds, f"walk-forward {k + 1}/{folds}")
    validation = classification(np.concatenate(ys), np.concatenate(ps))
    validation["folds"] = folds
    final = fit(dev_X, dev_y, fwd[: split - horizon])
    if progress:
        progress(0.85, "out-of-sample")
    p_oos = final.predict_proba(oos_X)
    oos = classification(oos_y, p_oos)
    oos_rows = idx[split:]
    oos_df = df.iloc[oos_rows].reset_index(drop=True)
    enter, exit_ = p_oos >= ENTER_P, p_oos < EXIT_P
    bt = run_on_signals(oos_df, enter, exit_, timeframe, 100.0, ExecConfig(stake_pct=0.95, stoploss_pct=0.03))
    oos["trading"] = {k: bt.metrics[k] for k in ("total_return", "max_drawdown", "profit_factor", "total_trades", "sharpe")}
    oos["buy_hold_return"] = round(float((oos_df["close"].iloc[-1] / oos_df["close"].iloc[0] - 1) * 100), 4)

    with db.session() as s:
        label = name or f"{algo}-{pair.replace('/', '')}-{timeframe}"
        model = s.query(MLModel).filter_by(name=label).one_or_none()
        if model is None:
            model = MLModel(name=label, algo=algo)
            s.add(model)
            s.flush()
        ver = (s.query(ModelVersion).filter_by(model_id=model.id).count()) + 1
        path = Path(data_dir) / "models" / f"{label}-v{ver}.joblib"
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": final, "features": names, "algo": algo, "horizon": horizon}, path)
        mv = ModelVersion(
            model_id=model.id, version=ver, pair=pair, timeframe=timeframe, dataset_hash=CandleStore.data_hash(df),
            train_start_ts=int(df["ts"].iloc[idx[0]]), train_end_ts=int(df["ts"].iloc[idx[split - horizon - 1]]), features=names,
            hyperparameters={"horizon": horizon, "seed": seed, **hyper}, validation_metrics=validation, oos_metrics=oos,
            feature_importance=final.importance(names), artifact_path=str(path), status="candidate",
        )
        s.add(mv)
        s.flush()
        return mv.id


def promote(db, version_id: int) -> None:
    """Explicit owner action. Archives the previously promoted version of the same model."""
    with db.session() as s:
        mv = s.get(ModelVersion, version_id)
        if mv is None:
            raise ValueError("unknown model version")
        for other in s.query(ModelVersion).filter_by(model_id=mv.model_id, status="promoted"):
            other.status = "archived"
        mv.status = "promoted"
