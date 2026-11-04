"""The authorization record that real trading depends on. Nothing here is automatic: time
passing never creates a row, and the owner must submit every limit explicitly."""

from __future__ import annotations

from quantlab.config import Settings
from quantlab.market.universe import screen_pair
from quantlab.models import EvaluationReport, EvaluationRun, ExchangeConnection, LiveAuthorization, utcnow
from quantlab.notify.service import notify, syslog

# Raising the first allocation is a code change on purpose, not a form field.
HARD_CAPITAL_CAP_USDT = 100.0
CONFIRMATION = "REAL PUL BILAN SAVDONI TASDIQLAYMAN"
TESTNET_CONFIRMATION = "TESTNET"


def active_authorization(s, environment: str) -> LiveAuthorization | None:
    return s.query(LiveAuthorization).filter(LiveAuthorization.environment == environment, LiveAuthorization.revoked_at.is_(None)).order_by(LiveAuthorization.id.desc()).first()


def gate_reasons(s, settings: Settings, environment: str) -> list[str]:
    """Every reason real orders may not be sent. Empty means all gates are open."""
    reasons = []
    if environment == "live" and not settings.live_enabled:
        reasons.append("QL_LIVE_ENABLED o'chirilgan")
    if active_authorization(s, environment) is None:
        reasons.append("egasining tasdig'i yo'q")
    if s.query(ExchangeConnection).filter_by(environment=environment).one_or_none() is None:
        reasons.append("API kalitlar kiritilmagan")
    return reasons


def authorize(db, *, report_id: int | None, strategy_version_id: int, pairs: list[str], max_capital: float, max_position: float, daily_loss_limit: float, max_drawdown_pct: float, fee_assumption: float, stop_conditions: dict, confirmation: str, environment: str = "live") -> int:
    if len(pairs) != 1:
        raise ValueError("the first authorization covers exactly one pair")
    for p in pairs:
        if (r := screen_pair(p)):
            raise ValueError(f"{p}: {r}")
    if not 0 < max_capital <= HARD_CAPITAL_CAP_USDT:
        raise ValueError(f"max_capital must be within (0, {HARD_CAPITAL_CAP_USDT}]")
    if not 0 < max_position <= max_capital:
        raise ValueError("max_position must be within (0, max_capital]")
    if not 0 < daily_loss_limit <= max_capital:
        raise ValueError("daily_loss_limit must be within (0, max_capital]")
    if not 0 < max_drawdown_pct <= 50:
        raise ValueError("max_drawdown_pct must be within (0, 50]")
    if not 0 <= fee_assumption <= 0.01:
        raise ValueError("fee_assumption must be within [0, 0.01]")
    with db.session() as s:
        if environment == "live":
            if confirmation != CONFIRMATION:
                raise ValueError("confirmation text does not match")
            rep = s.get(EvaluationReport, report_id) if report_id else None
            if rep is None or not rep.is_final:
                raise ValueError("a final evaluation report is required")
            run = s.get(EvaluationRun, rep.run_id)
            if run.status != "finished":
                raise ValueError("the evaluation run has not finished")
            row = next((r for r in rep.rows if r["strategy_version_id"] == strategy_version_id), None)
            if row is None:
                raise ValueError("this strategy version was not part of the evaluation")
            if not row["eligible"]:
                raise ValueError("this strategy did not pass the evaluation: " + "; ".join(row["fails"]))
        else:
            if confirmation != TESTNET_CONFIRMATION:
                raise ValueError("confirmation text does not match")
            rep = s.query(EvaluationReport).order_by(EvaluationReport.id.desc()).first()
        if rep is None:
            # Testnet has no real money and needs no report, but the column keeps the link.
            run = EvaluationRun(duration_days=0, criteria={}, status="finished")
            s.add(run)
            s.flush()
            rep = EvaluationReport(run_id=run.id, is_final=False)
            s.add(rep)
            s.flush()
        for old in s.query(LiveAuthorization).filter(LiveAuthorization.environment == environment, LiveAuthorization.revoked_at.is_(None)):
            old.revoked_at = utcnow()
        a = LiveAuthorization(report_id=rep.id, strategy_version_id=strategy_version_id, environment=environment, pairs=pairs, max_capital=max_capital, max_position=max_position, daily_loss_limit=daily_loss_limit, max_drawdown_pct=max_drawdown_pct, fee_assumption=fee_assumption, stop_conditions=stop_conditions, confirmation_text=confirmation)
        s.add(a)
        s.flush()
        syslog(s, "WARNING", "approval", f"owner authorized {environment}: version {strategy_version_id} {pairs} cap {max_capital}")
        notify(s, "live", f"Tasdiq saqlandi ({environment})", "Savdo hali boshlanmadi: alohida ishga tushirish kerak", "warn", "live")
        return a.id


def revoke(db, environment: str) -> None:
    with db.session() as s:
        for a in s.query(LiveAuthorization).filter(LiveAuthorization.environment == environment, LiveAuthorization.revoked_at.is_(None)):
            a.revoked_at = utcnow()
        syslog(s, "WARNING", "approval", f"owner revoked {environment} authorization")
