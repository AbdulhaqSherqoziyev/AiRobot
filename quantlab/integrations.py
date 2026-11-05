"""What was taken from each external project, how, and whether it works right now.
Version facts here were checked against the upstream source on 2026-11-05; see
.ai/integrations/INTEGRATION_REPORT.md."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from quantlab.config import Settings
from quantlab.models import AiReport, Experiment, SystemLog, SystemSetting

SETTING_KEY = "integrations"
MANIFEST = {
    "vectorbt": {
        "name": "VectorBT", "upstream": "polakowo/vectorbt", "audited": "1.2.0 (c923f74)", "license": "Apache-2.0 + Commons Clause",
        "mode": "ixtiyoriy kutubxona", "package": "vectorbt", "provides": "Tez parametr sweep; yakuniy natija baribir asosiy dvigatelda", "component": "vectorbt", "default": True,
        "obligation": "Commons Clause: VectorBT qiymati asosiy bo'lgan mahsulotni pullik xizmat sifatida sotib bo'lmaydi. Shaxsiy foydalanish mumkin.",
    },
    "jesse": {
        "name": "Jesse", "upstream": "jesse-ai/jesse", "audited": "3.6.0 (8665b25)", "license": "MIT",
        "mode": "g'oya, kod va runtime olinmagan", "package": None, "provides": "Strategiya spec formati, moslik hisoboti, Monte Carlo g'oyasi", "component": "jesse", "default": True,
        "obligation": "Kod ko'chirilmagan. Qiyoslash faqat alohida venv'da bajarilgan.",
    },
    "hummingbot": {
        "name": "Hummingbot", "upstream": "hummingbot/hummingbot", "audited": "2.17.0 (9af100d)", "license": "Apache-2.0",
        "mode": "g'oya, kod olinmagan", "package": None, "provides": "Faqat o'qiydigan order book ko'rsatkichlari", "component": "micro", "default": True,
        "obligation": "Kod ko'chirilmagan. Hummingbot buyurtma yuborish yo'liga ega emas.",
    },
    "tradingagents": {
        "name": "TradingAgents", "upstream": "TauricResearch/TradingAgents", "audited": "0.7.1 (9fa1196)", "license": "Apache-2.0",
        "mode": "ixtiyoriy AI tahlil (alohida venv)", "package": None, "provides": "Tuzilgan AI hisobot; standart tahlilchi Claude, bazaviy qoida LLM'siz", "component": "ai", "default": False,
        "obligation": "Upstream alohida interpreterda ishlaydi va manzili sozlanadi. LLM xarajati chegaralangan.",
    },
}


def switches(s) -> dict[str, bool]:
    row = s.get(SystemSetting, SETTING_KEY)
    saved = row.value if row else {}
    return {k: bool(saved.get(k, m["default"])) for k, m in MANIFEST.items()}


def is_enabled(s, key: str) -> bool:
    return switches(s)[key]


def set_enabled(s, key: str, enabled: bool) -> None:
    if key not in MANIFEST:
        raise KeyError(key)
    row = s.get(SystemSetting, SETTING_KEY)
    s.merge(SystemSetting(key=SETTING_KEY, value={**(row.value if row else {}), key: enabled}))


def _installed(package: str | None) -> str | None:
    if not package:
        return None
    try:
        return version(package)
    except PackageNotFoundError:
        return None


def _last_runs(s) -> dict:
    out: dict = {k: {"last_success": None, "last_error": None} for k in MANIFEST}
    done = s.query(Experiment).filter(Experiment.status == "done").order_by(Experiment.id.desc())
    if (e := done.filter(Experiment.backend == "vectorbt").first()):
        out["vectorbt"]["last_success"] = e.created_at
    if (e := done.filter(Experiment.strategy_key.like("jesse_%")).first()):
        out["jesse"]["last_success"] = e.created_at
    if (e := s.query(Experiment).filter(Experiment.status == "error", Experiment.backend == "vectorbt").order_by(Experiment.id.desc()).first()):
        out["vectorbt"]["last_error"] = {"at": e.created_at, "text": e.error}
    if (r := s.query(AiReport).filter(AiReport.status == "ok").order_by(AiReport.id.desc()).first()):
        out["tradingagents"]["last_success"] = r.created_at
    if (r := s.query(AiReport).filter(AiReport.status == "error").order_by(AiReport.id.desc()).first()):
        out["tradingagents"]["last_error"] = {"at": r.created_at, "text": r.error}
    return out


def health(key: str, enabled: bool, settings: Settings) -> dict:
    if key == "vectorbt":
        v = _installed("vectorbt")
        return {"state": "ok" if v else "missing", "installed": v, "text": f"vectorbt {v} o'rnatilgan" if v else "O'rnatilmagan: sweep native dvigatelda ishlaydi"}
    if key == "tradingagents":
        engines = []
        if settings.ai_api_key and _installed("anthropic"):
            engines.append("claude")
        if settings.tradingagents_python:
            engines.append("tradingagents")
        text = "LLM tahlilchi sozlanmagan: faqat bazaviy qoida ishlaydi" if not settings.ai_api_key else "LLM kaliti sozlangan"
        return {"state": "ok" if settings.ai_api_key else "degraded", "installed": _installed("anthropic"), "text": text, "engines": ["rule_baseline", *engines]}
    return {"state": "ok", "installed": None, "text": "Tashqi kutubxona kerak emas"}


def status(s, settings: Settings, ts) -> list[dict]:
    sw = switches(s)
    runs = _last_runs(s)
    out = []
    for k, m in MANIFEST.items():
        logs = s.query(SystemLog).filter(SystemLog.component == m["component"]).order_by(SystemLog.id.desc()).limit(10).all()
        err = runs[k]["last_error"]
        out.append({
            "key": k, **{a: m[a] for a in ("name", "upstream", "audited", "license", "mode", "provides", "obligation")},
            "enabled": sw[k], "health": health(k, sw[k], settings),
            "last_success": ts(runs[k]["last_success"]), "last_error": {"at": ts(err["at"]), "text": err["text"]} if err else None,
            "logs": [{"at": ts(l.created_at), "level": l.level, "message": l.message[:300]} for l in logs],
        })
    return out
