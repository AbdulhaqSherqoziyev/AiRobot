"""Relational schema. Money columns are floats rounded by the accounting layer; this is a
single-owner research system with small balances, and Binance quantities fit a double."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Stamped:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class User(Base, Stamped):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ExchangeConnection(Base, Stamped):
    """Encrypted exchange credentials. Secrets are never returned by any API."""

    __tablename__ = "exchange_connections"
    id: Mapped[int] = mapped_column(primary_key=True)
    environment: Mapped[str] = mapped_column(String(16), unique=True)  # testnet | live
    api_key_enc: Mapped[str] = mapped_column(Text)
    api_secret_enc: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(16), default="")


class TradingPair(Base, Stamped):
    __tablename__ = "trading_pairs"
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_notional: Mapped[float] = mapped_column(Float, default=5.0)
    step_size: Mapped[float] = mapped_column(Float, default=0.0)
    tick_size: Mapped[float] = mapped_column(Float, default=0.0)
    quote_volume_24h: Mapped[float] = mapped_column(Float, default=0.0)
    spread_bps: Mapped[float] = mapped_column(Float, default=0.0)
    volatility: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class MarketDataset(Base, Stamped):
    __tablename__ = "market_datasets"
    __table_args__ = (UniqueConstraint("symbol", "timeframe"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(128))
    path: Mapped[str] = mapped_column(String(512))
    first_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rows: Mapped[int] = mapped_column(Integer, default=0)
    gaps: Mapped[int] = mapped_column(Integer, default=0)
    duplicates_dropped: Mapped[int] = mapped_column(Integer, default=0)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class Strategy(Base, Stamped):
    __tablename__ = "strategies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    engine: Mapped[str] = mapped_column(String(64))  # registry key
    kind: Mapped[str] = mapped_column(String(16), default="technical")  # technical | ml
    description: Mapped[str] = mapped_column(Text, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    color: Mapped[str] = mapped_column(String(16), default="#3B82F6")
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    versions: Mapped[list["StrategyVersion"]] = relationship(back_populates="strategy", cascade="all, delete-orphan", order_by="StrategyVersion.version")


class StrategyVersion(Base, Stamped):
    """Immutable: an edit creates a new row, so past results stay reproducible."""

    __tablename__ = "strategy_versions"
    __table_args__ = (UniqueConstraint("strategy_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    pairs: Mapped[list] = mapped_column(JSON, default=list)
    timeframe: Mapped[str] = mapped_column(String(8), default="1h")
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(Text, default="")
    strategy: Mapped[Strategy] = relationship(back_populates="versions")
    parameters: Mapped[list["StrategyParameter"]] = relationship(cascade="all, delete-orphan")

    def params(self) -> dict:
        return {p.name: p.value for p in self.parameters}


class StrategyParameter(Base):
    __tablename__ = "strategy_parameters"
    __table_args__ = (UniqueConstraint("version_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    value: Mapped[float | int | str | bool | None] = mapped_column(JSON)


class BacktestSession(Base, Stamped):
    __tablename__ = "backtest_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"), index=True)
    pair: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    start_ts: Mapped[int] = mapped_column(Integer)
    end_ts: Mapped[int] = mapped_column(Integer)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # full input, for reproducibility
    data_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str] = mapped_column(Text, default="")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped["BacktestResult | None"] = relationship(back_populates="session", cascade="all, delete-orphan", uselist=False)


class BacktestResult(Base, Stamped):
    __tablename__ = "backtest_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("backtest_sessions.id", ondelete="CASCADE"), unique=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    trades: Mapped[list] = mapped_column(JSON, default=list)
    equity: Mapped[list] = mapped_column(JSON, default=list)
    monthly: Mapped[list] = mapped_column(JSON, default=list)
    session: Mapped[BacktestSession] = relationship(back_populates="result")


class PaperSession(Base, Stamped):
    __tablename__ = "paper_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    pair: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)  # running paused stopped halted
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fee: Mapped[float] = mapped_column(Float, default=0.001)
    slippage: Mapped[float] = mapped_column(Float, default=0.0005)
    risk: Mapped[dict] = mapped_column(JSON, default=dict)
    last_candle_ts: Mapped[int] = mapped_column(Integer, default=0)
    pending_signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    halt_reason: Mapped[str] = mapped_column(Text, default="")
    eval_run_id: Mapped[int | None] = mapped_column(ForeignKey("evaluation_runs.id"), nullable=True, index=True)
    portfolio: Mapped["VirtualPortfolio"] = relationship(back_populates="session", cascade="all, delete-orphan", uselist=False)
    trades: Mapped[list["PaperTrade"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class VirtualPortfolio(Base, Stamped):
    """One per session, so balances cannot be shared between strategies."""

    __tablename__ = "virtual_portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("paper_sessions.id", ondelete="CASCADE"), unique=True)
    initial_balance: Mapped[float] = mapped_column(Float)
    peak_equity: Mapped[float] = mapped_column(Float)
    session: Mapped[PaperSession] = relationship(back_populates="portfolio")
    balances: Mapped[list["VirtualBalance"]] = relationship(cascade="all, delete-orphan")

    def balance(self, asset: str) -> "VirtualBalance | None":
        return next((b for b in self.balances if b.asset == asset), None)


class VirtualBalance(Base):
    __tablename__ = "virtual_balances"
    __table_args__ = (UniqueConstraint("portfolio_id", "asset"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("virtual_portfolios.id", ondelete="CASCADE"), index=True)
    asset: Mapped[str] = mapped_column(String(16))
    free: Mapped[float] = mapped_column(Float, default=0.0)


class PaperTrade(Base):
    __tablename__ = "paper_trades"
    # One entry per signal candle: the guard against duplicate orders after a restart.
    __table_args__ = (UniqueConstraint("session_id", "entry_signal_ts"), Index("ix_paper_open", "session_id", "exit_ts"))
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("paper_sessions.id", ondelete="CASCADE"), index=True)
    entry_signal_ts: Mapped[int] = mapped_column(Integer)
    entry_ts: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    entry_fee: Mapped[float] = mapped_column(Float)
    exit_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_fee: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    exit_reason: Mapped[str] = mapped_column(String(32), default="")
    session: Mapped[PaperSession] = relationship(back_populates="trades")


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    __table_args__ = (UniqueConstraint("scope", "scope_id", "ts"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(8))  # paper | live
    scope_id: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[int] = mapped_column(Integer)
    equity: Mapped[float] = mapped_column(Float)


class LivePortfolio(Base, Stamped):
    __tablename__ = "live_portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    environment: Mapped[str] = mapped_column(String(16))  # testnet | live
    authorization_id: Mapped[int | None] = mapped_column(ForeignKey("live_authorizations.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="stopped")  # stopped running halted
    halt_reason: Mapped[str] = mapped_column(Text, default="")
    initial_capital: Mapped[float] = mapped_column(Float, default=0.0)
    peak_equity: Mapped[float] = mapped_column(Float, default=0.0)
    last_candle_ts: Mapped[int] = mapped_column(Integer, default=0)


class LiveOrder(Base, Stamped):
    __tablename__ = "live_orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("live_portfolios.id"), index=True)
    # Deterministic client id: Binance rejects a repeat, the second guard against duplicates.
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    symbol: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(8))
    quote_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_qty: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    exchange_order_id: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)


class LiveTrade(Base):
    __tablename__ = "live_trades"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("live_portfolios.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    entry_ts: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float] = mapped_column(Float)
    qty: Mapped[float] = mapped_column(Float)
    entry_fee: Mapped[float] = mapped_column(Float, default=0.0)
    exit_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_fee: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    exit_reason: Mapped[str] = mapped_column(String(32), default="")


class MLModel(Base, Stamped):
    __tablename__ = "ml_models"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    algo: Mapped[str] = mapped_column(String(32))
    versions: Mapped[list["ModelVersion"]] = relationship(back_populates="model", cascade="all, delete-orphan", order_by="ModelVersion.version")


class ModelVersion(Base, Stamped):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("ml_models.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    pair: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    dataset_hash: Mapped[str] = mapped_column(String(64))
    train_start_ts: Mapped[int] = mapped_column(Integer)
    train_end_ts: Mapped[int] = mapped_column(Integer)
    features: Mapped[list] = mapped_column(JSON, default=list)
    hyperparameters: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    oos_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_importance: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact_path: Mapped[str] = mapped_column(String(512), default="")
    # candidate -> promoted -> archived; promotion is always an explicit owner action.
    status: Mapped[str] = mapped_column(String(16), default="candidate", index=True)
    model: Mapped[MLModel] = relationship(back_populates="versions")


class Job(Base, Stamped):
    """Background work queue; workers claim rows, so a job survives a process restart."""

    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)  # backtest train optimize sync evaluate
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)  # queued running done error cancelled
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)


class OptimizationJob(Base, Stamped):
    __tablename__ = "optimization_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), index=True)
    pair: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    top: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(16), default="queued")


class TrainingJob(Base, Stamped):
    __tablename__ = "training_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    algo: Mapped[str] = mapped_column(String(32))
    pair: Mapped[str] = mapped_column(String(32))
    timeframe: Mapped[str] = mapped_column(String(8))
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="queued")


class EvaluationRun(Base, Stamped):
    """A 30-day evaluation window. Criteria are stored at the start and never edited after."""

    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running finished


class EvaluationReport(Base, Stamped):
    __tablename__ = "evaluation_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    rows: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[dict] = mapped_column(JSON, default=dict)


class LiveAuthorization(Base, Stamped):
    __tablename__ = "live_authorizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("evaluation_reports.id"))
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    environment: Mapped[str] = mapped_column(String(16), default="live")
    pairs: Mapped[list] = mapped_column(JSON, default=list)
    max_capital: Mapped[float] = mapped_column(Float)
    max_position: Mapped[float] = mapped_column(Float)
    daily_loss_limit: Mapped[float] = mapped_column(Float)
    max_drawdown_pct: Mapped[float] = mapped_column(Float)
    fee_assumption: Mapped[float] = mapped_column(Float)
    stop_conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmation_text: Mapped[str] = mapped_column(String(128))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AnalysisReport(Base, Stamped):
    __tablename__ = "analysis_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    strategies: Mapped[list] = mapped_column(JSON, default=list)
    models: Mapped[list] = mapped_column(JSON, default=list)
    market: Mapped[list] = mapped_column(JSON, default=list)
    findings: Mapped[list] = mapped_column(JSON, default=list)


class Experiment(Base, Stamped):
    """One parameter sweep. Failed and rejected runs stay: the record of what did not work is
    part of the result."""

    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    strategy_key: Mapped[str] = mapped_column(String(64), index=True)
    strategy_version: Mapped[str] = mapped_column(String(16), default="1")
    pairs: Mapped[list] = mapped_column(JSON, default=list)
    timeframe: Mapped[str] = mapped_column(String(8))
    start_ts: Mapped[int] = mapped_column(Integer)
    end_ts: Mapped[int] = mapped_column(Integer)
    backend: Mapped[str] = mapped_column(String(16), index=True)
    grid: Mapped[dict] = mapped_column(JSON, default=dict)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    n_combos: Mapped[int] = mapped_column(Integer, default=0)
    runtime_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    repro: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class ExperimentResult(Base):
    """Train and validation results of one parameter set. The test segment is in the summary,
    only for the chosen set."""

    __tablename__ = "experiment_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    train: Mapped[dict] = mapped_column(JSON, default=dict)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
    per_pair: Mapped[dict] = mapped_column(JSON, default=dict)


class AiReport(Base, Stamped):
    """One analyst run: inputs, output, cost and later what the market did. Only a record: no
    code path reads this table to trade."""

    __tablename__ = "ai_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    pair: Mapped[str] = mapped_column(String(32), index=True)
    timeframe: Mapped[str] = mapped_column(String(8))
    engine: Mapped[str] = mapped_column(String(24), index=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="error", index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    data_pack: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[dict] = mapped_column(JSON, default=dict)
    raw: Mapped[str] = mapped_column(Text, default="")
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_candle_ts: Mapped[int] = mapped_column(Integer)
    reference_price: Mapped[float] = mapped_column(Float)
    outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    outcome_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RiskEvent(Base, Stamped):
    __tablename__ = "risk_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(8))
    scope_id: Mapped[int] = mapped_column(Integer, index=True)
    rule: Mapped[str] = mapped_column(String(48))
    detail: Mapped[str] = mapped_column(Text, default="")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Notification(Base, Stamped):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(24), index=True)
    tone: Mapped[str] = mapped_column(String(8), default="info")
    title: Mapped[str] = mapped_column(String(256))
    text: Mapped[str] = mapped_column(Text, default="")
    route: Mapped[str] = mapped_column(String(32), default="dashboard")
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    telegram_sent: Mapped[bool] = mapped_column(Boolean, default=False)


class SystemLog(Base, Stamped):
    __tablename__ = "system_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(8), index=True)
    component: Mapped[str] = mapped_column(String(32), index=True)
    message: Mapped[str] = mapped_column(Text)


class ComponentHeartbeat(Base):
    __tablename__ = "component_heartbeats"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
