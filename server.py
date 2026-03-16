"""
DASHBOARD API SERVER — multi-bot
---------------------------------
FastAPI server che espone i dati del bot alla dashboard React.
Supporta N bot in parallelo, ognuno con il proprio simbolo e strategia.

Avvio:
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload

Endpoints principali:
    GET  /api/bots                       → lista bot configurati + stato
    POST /api/bots                       → crea nuovo bot
    GET  /api/bots/{bot_id}/status       → stato corrente bot
    GET  /api/bots/{bot_id}/journal      → ultime N decisioni
    GET  /api/bots/{bot_id}/stats        → statistiche aggregate
    GET  /api/bots/{bot_id}/costs        → costi API aggregati
    GET  /api/bots/{bot_id}/logs         → ultime N righe di log
    GET  /api/bots/{bot_id}/settings     → impostazioni runtime
    POST /api/bots/{bot_id}/settings     → salva impostazioni runtime
    POST /api/bots/{bot_id}/start        → avvia bot come subprocess
    POST /api/bots/{bot_id}/stop         → ferma bot via stop flag
    DELETE /api/bots/{bot_id}            → rimuove bot dal registry

Backward-compat (dashboard vecchia, bot_id="default"):
    GET  /api/status   GET  /api/journal   GET  /api/stats
    GET  /api/costs    GET  /api/logs      GET  /api/config
    GET  /api/settings POST /api/settings  POST /api/config
    POST /api/bot/start POST /api/bot/stop
"""

import json
import os
import re
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from journal import compute_stats
from config import (
    MIN_CONFIDENCE, MAX_DAILY_LOSS_PCT, MAX_TRADE_DURATION_H,
    SESSION_FILTER_ENABLED, SESSION_START_UTC, SESSION_END_UTC,
    WEB_SEARCH_MIN_SCORE, ADX_THRESHOLD, REQUIRE_ADX,
    REQUIRE_EMA_CROSS, REQUIRE_RSI_ALIGNED, REQUIRE_H4_CONFIRM,
)


# ── Costanti ───────────────────────────────────────────────────────
BOTS_CONFIG_FILE = "bots_config.json"
STALE_THRESHOLD  = timedelta(minutes=3)

SETTINGS_DEFAULTS = {
    "min_confidence":         MIN_CONFIDENCE,
    "max_daily_loss_pct":     MAX_DAILY_LOSS_PCT,
    "max_trade_duration_h":   MAX_TRADE_DURATION_H,
    "session_filter_enabled": SESSION_FILTER_ENABLED,
    "session_start_utc":      SESSION_START_UTC,
    "session_end_utc":        SESSION_END_UTC,
    "web_search_min_score":   WEB_SEARCH_MIN_SCORE,
    "adx_threshold":          ADX_THRESHOLD,
    "require_adx":            REQUIRE_ADX,
    "require_ema_cross":      REQUIRE_EMA_CROSS,
    "require_rsi_aligned":    REQUIRE_RSI_ALIGNED,
    "require_h4_confirm":     REQUIRE_H4_CONFIRM,
}

SETTINGS_BOUNDS: dict[str, tuple] = {
    "min_confidence":       (10,  99),
    "max_daily_loss_pct":   (0.1, 20.0),
    "max_trade_duration_h": (1,   168),
    "session_start_utc":    (0,   23),
    "session_end_utc":      (1,   24),
    "web_search_min_score": (10,  99),
    "adx_threshold":        (10,  60),
}

# Processo(i) avviati da questo server: {bot_id: Popen}
_bot_processes: dict[str, subprocess.Popen] = {}


# ── Lifespan ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown: ferma tutti i bot avviati da questo server
    running = [bid for bid in list(_bot_processes) if _bot_is_running(bid)]
    for bid in running:
        _bot_dir(bid).joinpath("bot_stop.flag").write_text("stop", encoding="utf-8")

    if running:
        for _ in range(15):
            time.sleep(1)
            if not any(_bot_is_running(b) for b in running):
                break
        else:
            for bid in running:
                proc = _bot_processes.get(bid)
                if proc and proc.poll() is None:
                    proc.terminate()

    # Pulizia flag residui
    for bid in running:
        flag = _bot_dir(bid) / "bot_stop.flag"
        try:
            if flag.exists():
                flag.unlink()
        except Exception:
            pass


app = FastAPI(title="Forex AI Bot Dashboard", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════

def _bot_dir(bot_id: str) -> Path:
    return Path("bots") / bot_id


def _bot_file(bot_id: str, name: str) -> Path:
    return _bot_dir(bot_id) / name


def _load_json(path) -> list | dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_bots_config() -> list:
    data = _load_json(BOTS_CONFIG_FILE)
    return data if isinstance(data, list) else []


def _save_bots_config(bots: list):
    tmp = BOTS_CONFIG_FILE + ".tmp"
    Path(tmp).write_text(json.dumps(bots, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, BOTS_CONFIG_FILE)


def _bot_is_running(bot_id: str) -> bool:
    proc = _bot_processes.get(bot_id)
    if proc and proc.poll() is None:
        return True
    pid_path = _bot_file(bot_id, "bot.pid")
    if pid_path.exists():
        try:
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError, ValueError, OSError):
            pass
    return False


def _get_bot_status(bot_id: str) -> dict:
    """Legge e arricchisce lo stato di un bot specifico."""
    data = _load_json(_bot_file(bot_id, "bot_status.json"))
    if data is None:
        return {"running": False, "phase": "offline", "timestamp": None, "bot_id": bot_id}

    if data.get("phase") in ("stopped", "error"):
        data["running"] = False
        data["bot_id"]  = bot_id
        return data

    ts_str = data.get("timestamp")
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            data["running"] = (datetime.now(timezone.utc) - ts) < STALE_THRESHOLD
        except ValueError:
            data["running"] = False
    else:
        data["running"] = False

    data["bot_id"] = bot_id
    return data


def _validate_settings(body: dict) -> dict:
    """Valida e clampla le impostazioni. Ritorna solo le chiavi riconosciute."""
    validated = {}
    for key, default in SETTINGS_DEFAULTS.items():
        if key not in body:
            continue
        val = body[key]
        try:
            if isinstance(default, bool):
                coerced = bool(val)
            elif isinstance(default, int):
                coerced = int(val)
            elif isinstance(default, float):
                coerced = float(val)
            else:
                coerced = val
            if key in SETTINGS_BOUNDS and not isinstance(coerced, bool):
                lo, hi  = SETTINGS_BOUNDS[key]
                coerced = max(lo, min(hi, coerced))
            validated[key] = coerced
        except (ValueError, TypeError):
            pass
    return validated


# ══════════════════════════════════════════════════════════════════
#  ENDPOINTS — multi-bot
# ══════════════════════════════════════════════════════════════════

@app.get("/api/bots")
def list_bots():
    """Lista tutti i bot configurati con stato corrente."""
    bots = _load_bots_config()
    result = []
    for b in bots:
        bid    = b.get("bot_id", "")
        _bot_dir(bid).mkdir(parents=True, exist_ok=True)
        status = _get_bot_status(bid)
        result.append({**b, "running": status.get("running", False),
                       "phase": status.get("phase", "offline")})
    return result


VALID_STRATEGIES = {
    "ema_rsi_ai",
    "ema_rsi_ai_main",
    "ema_rsi_ai_scalp",
    "ema_rsi_manual",
}


@app.post("/api/bots")
async def create_bot(request: Request):
    """Crea un nuovo bot e lo aggiunge al registry."""
    body     = await request.json()
    bot_id   = body.get("bot_id", "").strip()
    strategy = body.get("strategy", "ema_rsi_ai")

    if not bot_id:
        raise HTTPException(status_code=400, detail="bot_id richiesto")
    if not re.match(r"^[a-zA-Z0-9_-]+$", bot_id):
        raise HTTPException(status_code=400, detail="bot_id: solo lettere, numeri, _ e -")
    if strategy not in VALID_STRATEGIES:
        raise HTTPException(
            status_code=400,
            detail=f"Strategia '{strategy}' non valida. Valide: {sorted(VALID_STRATEGIES)}",
        )

    bots = _load_bots_config()
    if any(b["bot_id"] == bot_id for b in bots):
        raise HTTPException(status_code=409, detail=f"bot_id '{bot_id}' gia' esistente")

    new_bot = {
        "bot_id":             bot_id,
        "symbol":             body.get("symbol",             "EURUSD"),
        "symbol_base":        body.get("symbol_base",        "EUR"),
        "symbol_quote":       body.get("symbol_quote",       "USD"),
        "central_bank_base":  body.get("central_bank_base",  "BCE"),
        "central_bank_quote": body.get("central_bank_quote", "Federal Reserve"),
        "strategy":           strategy,
        "params":             body.get("params",             {}),
        "enabled":            True,
    }
    bots.append(new_bot)
    _save_bots_config(bots)

    # Crea directory del bot
    _bot_dir(bot_id).mkdir(parents=True, exist_ok=True)
    return new_bot


@app.delete("/api/bots/{bot_id}")
def delete_bot(bot_id: str):
    """Rimuove un bot dal registry (non cancella i file di log)."""
    if _bot_is_running(bot_id):
        raise HTTPException(status_code=409, detail="Ferma il bot prima di eliminarlo")
    bots    = _load_bots_config()
    updated = [b for b in bots if b["bot_id"] != bot_id]
    if len(updated) == len(bots):
        raise HTTPException(status_code=404, detail=f"bot_id '{bot_id}' non trovato")
    _save_bots_config(updated)
    return {"deleted": bot_id}


@app.get("/api/bots/{bot_id}/status")
def get_bot_status_endpoint(bot_id: str):
    return _get_bot_status(bot_id)


@app.get("/api/bots/{bot_id}/journal")
def get_bot_journal(bot_id: str, limit: int = 100):
    entries = _load_json(_bot_file(bot_id, "journal.json"))
    if not entries:
        return []
    return list(reversed(entries))[:limit]


@app.get("/api/bots/{bot_id}/stats")
def get_bot_stats(bot_id: str):
    entries = _load_json(_bot_file(bot_id, "journal.json"))
    return compute_stats(entries or [])


@app.get("/api/bots/{bot_id}/costs")
def get_bot_costs(bot_id: str):
    data = _load_json(_bot_file(bot_id, "api_costs.json"))
    if not data:
        return {"total_cost": 0.0, "total_calls": 0, "today_cost": 0.0,
                "month_cost": 0.0, "by_stage": {}, "last_calls": []}

    calls = data.get("calls", [])
    today = datetime.now(timezone.utc).date().isoformat()
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    by_stage: dict[str, float] = {}
    for c in calls:
        s = c.get("stage", "?")
        by_stage[s] = round(by_stage.get(s, 0) + c.get("cost_usd", 0), 6)

    return {
        "total_cost":  round(data.get("total_cost", 0), 4),
        "total_calls": data.get("total_calls", 0),
        "today_cost":  round(sum(c["cost_usd"] for c in calls if c.get("timestamp", "").startswith(today)), 4),
        "month_cost":  round(sum(c["cost_usd"] for c in calls if c.get("timestamp", "").startswith(month)), 4),
        "by_stage":    by_stage,
        "last_calls":  list(reversed(calls[-10:])),
    }


@app.get("/api/bots/{bot_id}/logs")
def get_bot_logs(bot_id: str, lines: int = 150):
    log_file = _bot_file(bot_id, "bot.log")
    if not log_file.exists():
        return {"lines": [], "total": 0}
    try:
        content   = log_file.read_text(encoding="utf-8", errors="replace")
        all_lines = [l for l in content.splitlines() if l.strip()]
        return {"lines": all_lines[-lines:], "total": len(all_lines)}
    except Exception as e:
        return {"lines": [f"Errore lettura log: {e}"], "total": 0}


@app.get("/api/bots/{bot_id}/settings")
def get_bot_settings(bot_id: str):
    saved = _load_json(_bot_file(bot_id, "bot_settings.json")) or {}
    return {**SETTINGS_DEFAULTS, **saved}


@app.post("/api/bots/{bot_id}/settings")
async def set_bot_settings(bot_id: str, request: Request):
    body      = await request.json()
    validated = _validate_settings(body)
    settings_path = _bot_file(bot_id, "bot_settings.json")
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(settings_path) + ".tmp"
    Path(tmp).write_text(json.dumps(validated, indent=2), encoding="utf-8")
    os.replace(tmp, settings_path)
    return {**SETTINGS_DEFAULTS, **validated}


@app.post("/api/bots/{bot_id}/start")
def start_bot(bot_id: str, dry_run: bool = True, use_mock: bool = True):
    """Avvia un bot come subprocess."""
    if _bot_is_running(bot_id):
        pid = _bot_processes[bot_id].pid if _bot_processes.get(bot_id) else None
        return {"status": "already_running", "pid": pid, "bot_id": bot_id}

    # Rimuovi stop flag residuo
    flag = _bot_file(bot_id, "bot_stop.flag")
    if flag.exists():
        flag.unlink()

    # Leggi config del bot dal registry
    bots   = _load_bots_config()
    bot_cfg = next((b for b in bots if b["bot_id"] == bot_id), None)

    args = [sys.executable, "-u", "bot.py", "--bot-id", bot_id]
    if dry_run:
        args.append("--dry")
    if use_mock:
        args.append("--mock")
    if bot_cfg:
        args += ["--strategy", bot_cfg.get("strategy", "ema_rsi_ai")]
        params = bot_cfg.get("params", {})
        if params:
            args += ["--params", json.dumps(params)]

    # Env vars per simbolo e banche centrali (letti da config.py via os.getenv)
    env = os.environ.copy()
    env["PYTHONUTF8"]        = "1"
    env["PYTHONIOENCODING"]  = "utf-8"
    if bot_cfg:
        env["SYMBOL"]             = bot_cfg.get("symbol",             "EURUSD")
        env["SYMBOL_BASE"]        = bot_cfg.get("symbol_base",        "EUR")
        env["SYMBOL_QUOTE"]       = bot_cfg.get("symbol_quote",       "USD")
        env["CENTRAL_BANK_BASE"]  = bot_cfg.get("central_bank_base",  "BCE")
        env["CENTRAL_BANK_QUOTE"] = bot_cfg.get("central_bank_quote", "Federal Reserve")

    proc = subprocess.Popen(
        args,
        cwd=Path(__file__).parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    _bot_processes[bot_id] = proc
    return {"status": "started", "pid": proc.pid, "bot_id": bot_id, "dry_run": dry_run}


@app.get("/api/bots/{bot_id}/config")
def get_bot_config(bot_id: str):
    data = _load_json(_bot_file(bot_id, "bot_config.json"))
    return data if data else {"dry_run": True, "use_mock": True}


@app.post("/api/bots/{bot_id}/config")
def set_bot_config(bot_id: str, dry_run: bool, use_mock: Optional[bool] = None):
    config_path = _bot_file(bot_id, "bot_config.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_json(config_path) or {}
    data["dry_run"] = dry_run
    if use_mock is not None:
        data["use_mock"] = use_mock
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


@app.post("/api/bots/{bot_id}/stop")
def stop_bot(bot_id: str):
    """Ferma il bot scrivendo il flag di stop."""
    _bot_dir(bot_id).mkdir(parents=True, exist_ok=True)
    _bot_file(bot_id, "bot_stop.flag").write_text("stop", encoding="utf-8")
    return {"status": "stop_requested", "bot_id": bot_id}


# ══════════════════════════════════════════════════════════════════
#  BACKWARD-COMPAT — endpoint legacy (bot_id="default")
# ══════════════════════════════════════════════════════════════════

# File legacy nella root (pre-multi-bot) → mappati a bots/default/
_LEGACY_ROOT_FILES = {
    "bot_status.json": True,
    "journal.json":    True,
    "api_costs.json":  True,
    "bot.log":         True,
    "bot_settings.json": True,
    "bot_config.json": True,
    "bot_stop.flag":   True,
    "bot.pid":         True,
}

DEFAULT_BOT_ID = "default"


@app.get("/api/status")
def get_status():
    return _get_bot_status(DEFAULT_BOT_ID)


@app.get("/api/journal")
def get_journal(limit: int = 100):
    return get_bot_journal(DEFAULT_BOT_ID, limit)


@app.get("/api/stats")
def get_stats():
    return get_bot_stats(DEFAULT_BOT_ID)


@app.get("/api/costs")
def get_costs():
    return get_bot_costs(DEFAULT_BOT_ID)


@app.get("/api/logs")
def get_logs(lines: int = 150):
    return get_bot_logs(DEFAULT_BOT_ID, lines)


@app.get("/api/settings")
def get_settings():
    return get_bot_settings(DEFAULT_BOT_ID)


@app.post("/api/settings")
async def set_settings(request: Request):
    return await set_bot_settings(DEFAULT_BOT_ID, request)


@app.get("/api/config")
def get_config():
    data = _load_json(_bot_file(DEFAULT_BOT_ID, "bot_config.json"))
    return data if data else {"dry_run": True}


@app.post("/api/config")
def set_config(dry_run: bool, use_mock: Optional[bool] = None):
    config_path = _bot_file(DEFAULT_BOT_ID, "bot_config.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_json(config_path) or {}
    data["dry_run"] = dry_run
    if use_mock is not None:
        data["use_mock"] = use_mock
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


@app.post("/api/bot/stop")
def bot_stop():
    return stop_bot(DEFAULT_BOT_ID)


@app.post("/api/bot/start")
def bot_start(dry_run: bool = True, use_mock: bool = True):
    return start_bot(DEFAULT_BOT_ID, dry_run=dry_run, use_mock=use_mock)


# ── Serve la dashboard React ──────────────────────────────────────
_dist = Path("dashboard/dist")
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
