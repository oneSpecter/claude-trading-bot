"""
TRADE JOURNAL
-------------
Registra ogni decisione del bot con il ragionamento completo di Claude.
Salva in formato JSON (leggibile) e CSV (per analisi in Excel/pandas).
"""

import json
import csv
import os
import logging
from datetime import datetime

log = logging.getLogger("Journal")

JOURNAL_JSON = "journal.json"
JOURNAL_CSV  = "journal.csv"
CSV_FIELDS   = [
    "timestamp", "symbol", "decision", "confidence",
    "price", "sl", "tp", "lot",
    "technical_score", "fundamental_score", "market_regime",
    "initial_decision", "decision_changed",
    "reasoning", "devil_advocate",
    "executed", "ticket",
]


def _load_json() -> list:
    if not os.path.exists(JOURNAL_JSON):
        return []
    try:
        with open(JOURNAL_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_json(entries: list):
    with open(JOURNAL_JSON, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False, default=str)


def _append_csv(entry: dict):
    file_exists = os.path.exists(JOURNAL_CSV)
    with open(JOURNAL_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(entry)


def log_decision(decision: dict, tech_summary: dict, executed: bool, trade_result: dict = None):
    """Salva una decisione nel journal."""
    entry = {
        "timestamp":          datetime.utcnow().isoformat(),
        "symbol":             "EURUSD",
        "decision":           decision.get("decision"),
        "confidence":         decision.get("confidence"),
        "price":              tech_summary.get("price"),
        "sl":                 decision.get("sl"),
        "tp":                 decision.get("tp"),
        "lot":                trade_result.get("lot") if trade_result else None,
        "technical_score":    decision.get("technical_score"),
        "fundamental_score":  decision.get("fundamental_score"),
        "market_regime":      decision.get("market_regime"),
        "initial_decision":   decision.get("initial_decision"),
        "decision_changed":   decision.get("decision_changed_after_review"),
        "reasoning":          decision.get("reasoning"),
        "devil_advocate":     decision.get("devil_advocate"),
        "tech_brief":         decision.get("tech_brief"),
        "news_brief":         decision.get("news_brief"),
        "executed":           executed,
        "ticket":             trade_result.get("ticket") if trade_result else None,
    }

    # JSON (completo con brief)
    entries = _load_json()
    entries.append(entry)
    _save_json(entries)

    # CSV (sintetico, per analisi)
    _append_csv(entry)

    log.info(f"📓 Journal aggiornato — {entry['decision']} | {entry['confidence']}% confidence")


def print_stats():
    """Stampa statistiche dal journal."""
    entries = _load_json()
    if not entries:
        print("Journal vuoto.")
        return

    total       = len(entries)
    executed    = [e for e in entries if e.get("executed")]
    holds       = [e for e in entries if e.get("decision") == "HOLD"]
    changed     = [e for e in entries if e.get("decision_changed")]
    avg_conf    = sum(e.get("confidence", 0) for e in entries) / total

    print("\n" + "=" * 50)
    print("  📓  JOURNAL STATISTICHE")
    print("=" * 50)
    print(f"  Analisi totali:      {total}")
    print(f"  Trade eseguiti:      {len(executed)}")
    print(f"  HOLD:                {len(holds)}")
    print(f"  Decisioni cambiate   {len(changed)} ({len(changed)/total*100:.0f}%)")
    print(f"  Confidenza media:    {avg_conf:.1f}%")
    print("=" * 50)
