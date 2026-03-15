"""
DASHBOARD API SERVER
--------------------
FastAPI server che espone i dati del bot alla dashboard React.
Gira in parallelo al bot (processo separato).

Avvio:
    uvicorn server:app --host 0.0.0.0 --port 8000 --reload

Endpoints:
    GET /api/status   → stato corrente bot (da bot_status.json)
    GET /api/journal  → ultime N decisioni (da journal.json)
    GET /api/stats    → statistiche aggregate
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from journal import compute_stats

app = FastAPI(title="Forex AI Bot Dashboard", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

BOT_STATUS_FILE = "bot_status.json"
JOURNAL_FILE    = "journal.json"
COSTS_FILE      = "api_costs.json"
STOP_FLAG       = "bot_stop.flag"
STALE_THRESHOLD = timedelta(minutes=15)

_bot_process: subprocess.Popen | None = None


def _load_json(path: str) -> list | dict | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ── Endpoints ────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    """Stato corrente del bot."""
    data = _load_json(BOT_STATUS_FILE)
    if data is None:
        return {"running": False, "phase": "offline", "timestamp": None}

    # Se il bot ha scritto phase=stopped → non è running, sempre
    if data.get("phase") == "stopped":
        data["running"] = False
        return data

    # Controlla se il bot è ancora attivo (timestamp recente)
    ts_str = data.get("timestamp")
    if ts_str:
        try:
            ts = datetime.fromisoformat(ts_str)
            data["running"] = (datetime.now(timezone.utc) - ts) < STALE_THRESHOLD
        except ValueError:
            data["running"] = False
    else:
        data["running"] = False

    return data


@app.get("/api/journal")
def get_journal(limit: int = 100):
    """Ultime N decisioni in ordine cronologico inverso (più recente prima)."""
    entries = _load_json(JOURNAL_FILE)
    if not entries:
        return []
    # Inverti e limita
    return list(reversed(entries))[:limit]


@app.get("/api/stats")
def get_stats():
    """Statistiche aggregate dal journal."""
    entries = _load_json(JOURNAL_FILE)
    return compute_stats(entries or [])


@app.get("/api/costs")
def get_costs():
    """Costi API aggregati."""
    data = _load_json(COSTS_FILE)
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
        "today_cost":  round(sum(c["cost_usd"] for c in calls if c.get("timestamp","").startswith(today)), 4),
        "month_cost":  round(sum(c["cost_usd"] for c in calls if c.get("timestamp","").startswith(month)), 4),
        "by_stage":    by_stage,
        "last_calls":  list(reversed(calls[-10:])),
    }


@app.get("/api/logs")
def get_logs(lines: int = 150):
    """Ultime N righe di bot.log."""
    log_file = Path("bot.log")
    if not log_file.exists():
        return {"lines": [], "total": 0}
    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        all_lines = [l for l in content.splitlines() if l.strip()]
        return {"lines": all_lines[-lines:], "total": len(all_lines)}
    except Exception as e:
        return {"lines": [f"Errore lettura log: {e}"], "total": 0}


@app.post("/api/bot/stop")
def bot_stop():
    """Ferma il bot scrivendo il flag di stop (il bot lo rileva al prossimo tick)."""
    Path(STOP_FLAG).write_text("stop", encoding="utf-8")
    return {"status": "stop_requested"}


@app.post("/api/bot/start")
def bot_start(dry_run: bool = True):
    """Avvia il bot come sottoprocesso."""
    global _bot_process

    # Se il processo è ancora vivo non riavviare
    if _bot_process and _bot_process.poll() is None:
        return {"status": "already_running", "pid": _bot_process.pid, "dry_run": dry_run}

    # Rimuovi eventuale flag di stop rimasto
    stop_path = Path(STOP_FLAG)
    if stop_path.exists():
        stop_path.unlink()

    args = [sys.executable, "bot.py"]
    if dry_run:
        args.append("--dry")

    _bot_process = subprocess.Popen(args, cwd=Path(__file__).parent)
    return {"status": "started", "pid": _bot_process.pid, "dry_run": dry_run}


# ── Serve la dashboard React in produzione ───────────────────────
# (dopo `npm run build` nella cartella dashboard/)
_dist = Path("dashboard/dist")
if _dist.exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="static")
