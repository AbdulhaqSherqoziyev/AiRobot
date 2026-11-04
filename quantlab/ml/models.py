"""Model wrappers with one interface: fit(X, y), predict_proba(X) -> P(up)."""

from __future__ import annotations

import numpy as np

ALGOS = ("lightgbm", "xgboost", "random_forest", "lstm", "rl")


class SklearnLike:
    def __init__(self, algo: str, seed: int = 42, **hp):
        self.algo, self.seed, self.hp = algo, seed, hp
        self.model = None

    def fit(self, X: np.ndarray, y: np.ndarray):
        if self.algo == "lightgbm":
            import lightgbm as lgb

            self.model = lgb.LGBMClassifier(n_estimators=self.hp.get("n_estimators", 200), learning_rate=self.hp.get("learning_rate", 0.03), num_leaves=self.hp.get("num_leaves", 15), subsample=0.8, subsample_freq=1, colsample_bytree=0.8, random_state=self.seed, verbose=-1, n_jobs=2)
        elif self.algo == "xgboost":
            import xgboost as xgb

            self.model = xgb.XGBClassifier(n_estimators=self.hp.get("n_estimators", 200), learning_rate=self.hp.get("learning_rate", 0.03), max_depth=self.hp.get("max_depth", 4), subsample=0.8, colsample_bytree=0.8, random_state=self.seed, n_jobs=2, eval_metric="logloss")
        else:
            from sklearn.ensemble import RandomForestClassifier

            self.model = RandomForestClassifier(n_estimators=self.hp.get("n_estimators", 200), max_depth=self.hp.get("max_depth", 6), min_samples_leaf=20, random_state=self.seed, n_jobs=2)
        self.model.fit(X, y)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(X)[:, 1]

    def importance(self, names: list[str]) -> dict[str, float]:
        vals = np.asarray(self.model.feature_importances_, dtype=float)
        total = vals.sum() or 1.0
        return {n: round(float(v / total), 5) for n, v in sorted(zip(names, vals), key=lambda x: -x[1])}


class LstmModel:
    """Experimental. Requires torch, an optional dependency. Inputs are standardised with
    statistics from the training set only."""

    def __init__(self, seed: int = 42, seq: int = 32, hidden: int = 32, epochs: int = 6, **_):
        self.seed, self.seq, self.hidden, self.epochs = seed, seq, hidden, epochs
        self.net = None
        self.mean = self.std = None

    def _windows(self, X: np.ndarray) -> np.ndarray:
        idx = np.arange(self.seq)[None, :] + np.arange(len(X) - self.seq + 1)[:, None]
        return X[idx]

    def fit(self, X: np.ndarray, y: np.ndarray):
        import torch
        from torch import nn

        torch.manual_seed(self.seed)
        self.mean, self.std = X.mean(0), X.std(0) + 1e-9
        W = torch.tensor(self._windows((X - self.mean) / self.std), dtype=torch.float32)
        Y = torch.tensor(y[self.seq - 1:], dtype=torch.float32)

        from quantlab.ml.lstm_net import LstmNet

        self.net = LstmNet(X.shape[1], self.hidden)
        opt = torch.optim.Adam(self.net.parameters(), lr=1e-3)
        loss = nn.BCEWithLogitsLoss()
        for _ in range(self.epochs):
            perm = torch.randperm(len(W))
            for i in range(0, len(W), 256):
                b = perm[i:i + 256]
                opt.zero_grad()
                loss(self.net(W[b]), Y[b]).backward()
                opt.step()
        self.net.eval()
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        import torch

        out = np.full(len(X), 0.5)
        if len(X) < self.seq:
            return out
        W = torch.tensor(self._windows((X - self.mean) / self.std), dtype=torch.float32)
        with torch.no_grad():
            out[self.seq - 1:] = torch.sigmoid(self.net(W)).numpy()
        return out

    def importance(self, names: list[str]) -> dict[str, float]:
        return {}


class QLearningModel:
    """Experimental long-only RL: tabular Q-learning over binned features with two actions,
    flat or long. No short action exists, by construction. Reward is the next return
    minus switching costs. predict_proba returns 1 where long has the higher Q value."""

    FEATURES = ("rsi_14", "ema_ratio_20_50", "macd_hist_pct", "atr_pct_14")

    def __init__(self, seed: int = 42, bins: int = 5, alpha: float = 0.1, gamma: float = 0.95, epochs: int = 5, cost: float = 0.001, **_):
        self.seed, self.bins, self.alpha, self.gamma, self.epochs, self.cost = seed, bins, alpha, gamma, epochs, cost
        self.edges = None
        self.q: dict = {}
        self.cols: list[int] = []

    def _state(self, row: np.ndarray) -> tuple:
        return tuple(int(np.searchsorted(self.edges[i], row[c])) for i, c in enumerate(self.cols))

    def fit(self, X: np.ndarray, y: np.ndarray, names: list[str] | None = None, returns: np.ndarray | None = None):
        names = names or []
        self.cols = [names.index(f) for f in self.FEATURES if f in names] or list(range(min(4, X.shape[1])))
        self.edges = [np.quantile(X[:, c], np.linspace(0, 1, self.bins + 1)[1:-1]) for c in self.cols]
        rets = returns if returns is not None else (y - 0.5) * 0.01
        rng = np.random.default_rng(self.seed)
        for ep in range(self.epochs):
            pos, eps = 0, max(0.05, 0.3 - ep * 0.05)
            for t in range(len(X) - 1):
                s = self._state(X[t])
                qs = self.q.setdefault(s, np.zeros(2))
                a = int(rng.integers(2)) if rng.random() < eps else int(qs.argmax())
                r = (rets[t] if a == 1 else 0.0) - (self.cost if a != pos else 0.0)
                nxt = self.q.setdefault(self._state(X[t + 1]), np.zeros(2))
                qs[a] += self.alpha * (r + self.gamma * nxt.max() - qs[a])
                pos = a
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        out = np.zeros(len(X))
        for i, row in enumerate(X):
            q = self.q.get(self._state(row))
            out[i] = 1.0 if q is not None and q[1] > q[0] else 0.0
        return out

    def importance(self, names: list[str]) -> dict[str, float]:
        return {}


def make_model(algo: str, seed: int = 42, **hp):
    if algo in ("lightgbm", "xgboost", "random_forest"):
        return SklearnLike(algo, seed, **hp)
    if algo == "lstm":
        return LstmModel(seed=seed, **hp)
    if algo == "rl":
        return QLearningModel(seed=seed, **hp)
    raise ValueError(f"unknown algo {algo}")
