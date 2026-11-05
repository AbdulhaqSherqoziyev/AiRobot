"""ML strategies. They load an explicit model version from params (`model_path`), never
"the latest", so a retrain cannot silently change what an active session trades."""

from __future__ import annotations

import joblib
import numpy as np
import pandas as pd

from quantlab.ml.features import build_features
from quantlab.strategies.base import Param, RiskDefaults, Strategy


class _MLStrategy(Strategy):
    kind = "ml"
    indicators = ("features",)
    params = {"enter_p": Param(0.55, 0.5, 0.9, 0.01, False), "exit_p": Param(0.48, 0.1, 0.5, 0.01, False)}
    risk = RiskDefaults(stoploss_pct=0.03)
    _cache: dict = {}

    def signals(self, df: pd.DataFrame, params: dict | None = None) -> pd.DataFrame:
        params = dict(params or {})
        path = params.pop("model_path", None)
        p = self.resolve(params)
        if not path:
            # No trained version selected: the safe behaviour is to never trade.
            none = np.zeros(len(df), dtype=bool)
            return pd.DataFrame({"enter": none, "exit": none}, index=df.index)
        if path not in self._cache:  # a pinned version never changes on disk
            self._cache[path] = joblib.load(path)
        bundle = self._cache[path]
        X = build_features(df)[bundle["features"]]
        ok = X.notna().all(axis=1).to_numpy()
        proba = np.full(len(df), 0.5)
        if ok.any():
            proba[ok] = bundle["model"].predict_proba(X.to_numpy()[ok])
        return pd.DataFrame({"enter": ok & (proba >= p["enter_p"]), "exit": ok & (proba < p["exit_p"])}, index=df.index)

    def compute(self, df, p):  # pragma: no cover - signals() is overridden
        raise NotImplementedError


class LightgbmStrategy(_MLStrategy):
    """Enter when the model's P(up) reaches enter_p; exit below exit_p."""
    key, name, color = "ml_lightgbm", "LightGBM", "#22C55E"
    description = "Gradient boosted trees predicting a net-of-cost up move."


class XgboostStrategy(_MLStrategy):
    """Enter when the model's P(up) reaches enter_p; exit below exit_p."""
    key, name, color = "ml_xgboost", "XGBoost", "#14B8A6"
    description = "Gradient boosted trees (XGBoost) predicting a net-of-cost up move."


class RandomForestStrategy(_MLStrategy):
    """Enter when the model's P(up) reaches enter_p; exit below exit_p."""
    key, name, color = "ml_random_forest", "Random Forest", "#84CC16"
    description = "Baseline ensemble. Other models should beat it to earn their complexity."


class LstmStrategy(_MLStrategy):
    """Experimental. Enter when the LSTM's P(up) reaches enter_p; exit below exit_p."""
    key, name, color = "ml_lstm", "LSTM (experimental)", "#A855F7"
    description = "Experimental sequence model."


class RlStrategy(_MLStrategy):
    """Experimental long-only Q-learning: long while the long action has the higher value."""
    key, name, color = "ml_rl", "RL (experimental)", "#F97316"
    description = "Experimental tabular Q-learning agent with flat and long actions only."
