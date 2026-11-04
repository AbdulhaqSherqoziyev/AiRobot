"""Runtime settings, all from environment variables. Safe defaults: live trading off."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_WATCHLIST = "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT,XRP/USDT,DOGE/USDT,ADA/USDT,LINK/USDT,AVAX/USDT"
TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.environ.get("QL_DATABASE_URL", "sqlite:///quantlab_data/quantlab.db"))
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("QL_DATA_DIR", "quantlab_data")))
    binance_public_url: str = field(default_factory=lambda: os.environ.get("QL_BINANCE_PUBLIC_URL", "https://data-api.binance.vision"))
    binance_ws_url: str = field(default_factory=lambda: os.environ.get("QL_BINANCE_WS_URL", "wss://data-stream.binance.vision/stream"))
    binance_live_url: str = field(default_factory=lambda: os.environ.get("QL_BINANCE_LIVE_URL", "https://api.binance.com"))
    binance_testnet_url: str = field(default_factory=lambda: os.environ.get("QL_BINANCE_TESTNET_URL", "https://testnet.binance.vision"))
    watchlist: tuple[str, ...] = field(default_factory=lambda: tuple(p.strip() for p in os.environ.get("QL_WATCHLIST", DEFAULT_WATCHLIST).split(",") if p.strip()))
    # Signs login tokens and derives the at-rest encryption key. Required outside tests.
    secret_key: str = field(default_factory=lambda: os.environ.get("QL_SECRET_KEY", ""))
    owner_password: str = field(default_factory=lambda: os.environ.get("QL_OWNER_PASSWORD", ""))
    # Master switch checked by the live engine in addition to the approval record.
    live_enabled: bool = field(default_factory=lambda: _bool("QL_LIVE_ENABLED", False))
    telegram_token: str = field(default_factory=lambda: os.environ.get("QL_TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("QL_TELEGRAM_CHAT_ID", ""))
    secure_cookies: bool = field(default_factory=lambda: _bool("QL_SECURE_COOKIES", True))
    default_fee: float = 0.001
    default_slippage: float = 0.0005
    evaluation_days: int = 30


def get_settings() -> Settings:
    return Settings()
