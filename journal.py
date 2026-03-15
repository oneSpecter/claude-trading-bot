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
from datetime import datetime, timezone
from config import SYMBOL

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
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "symbol":             SYMBOL,
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


def log_trade_result(ticket: int, close_price: float, profit: float,
                     close_reason: str, close_time: str) -> bool:
    """
    Aggiorna l'entry del journal con il risultato reale del trade.
    Cerca l'entry per ticket, aggiunge close_price, profit, pips, win.
    Ritorna True se trovata e aggiornata.
    """
    if ticket is None:
        return False

    entries = _load_json()
    for entry in entries:
        if entry.get("ticket") != ticket:
            continue
        if not entry.get("executed"):
            continue
        if "close_price" in entry:          # già registrato
            continue

        entry["close_price"]  = close_price
        entry["close_time"]   = close_time
        entry["profit"]       = profit
        entry["close_reason"] = close_reason
        entry["win"]          = profit > 0

        # Pips (approssimato per forex a 4/5 decimali)
        open_price = entry.get("price")
        if open_price and entry.get("decision") in ("BUY", "SELL"):
            if entry["decision"] == "BUY":
                entry["pips"] = round((close_price - open_price) * 10_000, 1)
            else:
                entry["pips"] = round((open_price - close_price) * 10_000, 1)

        _save_json(entries)
        emoji = "✅" if profit > 0 else "❌"
        log.info(f"📊 Trade result — Ticket:{ticket} {emoji} ${profit:.2f} "
                 f"({entry.get('pips', '?')} pips) | Motivo: {close_reason}")
        return True

    return False


def compute_stats(entries: list) -> dict:
    """
    Calcola statistiche aggregate in un singolo passaggio.
    Usato da print_stats() e da server.py (nessuna duplicazione).
    """
    if not entries:
        return {
            "total": 0, "executed": 0, "holds": 0, "buys": 0, "sells": 0,
            "changed": 0, "avg_confidence": 0.0, "hold_rate": 0.0,
            "web_search_rate": 0.0, "win_rate": 0.0, "total_pnl": 0.0,
            "trades_with_result": 0, "winners": 0,
        }

    total = executed = holds = buys = sells = changed = web_done = winners = with_result = 0
    conf_sum = pnl_sum = 0.0

    for e in entries:
        total    += 1
        dec       = e.get("decision")
        conf_sum += e.get("confidence") or 0
        if e.get("executed"):          executed    += 1
        if dec == "HOLD":              holds       += 1
        if dec == "BUY":               buys        += 1
        if dec == "SELL":              sells       += 1
        if e.get("decision_changed"):  changed     += 1
        if e.get("web_search_done"):   web_done    += 1
        profit = e.get("profit")
        if profit is not None:
            with_result += 1
            pnl_sum     += profit
            if e.get("win"):
                winners += 1

    return {
        "total":              total,
        "executed":           executed,
        "holds":              holds,
        "buys":               buys,
        "sells":              sells,
        "changed":            changed,
        "winners":            winners,
        "avg_confidence":     round(conf_sum / total, 1),
        "hold_rate":          round(holds    / total * 100, 1),
        "web_search_rate":    round(web_done / total * 100, 1),
        "win_rate":           round(winners  / with_result * 100, 1) if with_result else 0.0,
        "total_pnl":          round(pnl_sum, 2),
        "trades_with_result": with_result,
    }


def print_stats():
    """Stampa statistiche dal journal."""
    entries = _load_json()
    if not entries:
        print("Journal vuoto.")
        return

    s = compute_stats(entries)
    print("\n" + "=" * 50)
    print("  📓  JOURNAL STATISTICHE")
    print("=" * 50)
    print(f"  Analisi totali:      {s['total']}")
    print(f"  Trade eseguiti:      {s['executed']}")
    print(f"  Trade con risultato: {s['trades_with_result']}")
    print(f"  Win rate:            {s['win_rate']:.0f}% ({s['winners']}/{s['trades_with_result']})")
    print(f"  PnL totale:          ${s['total_pnl']:.2f}")
    print(f"  HOLD:                {s['holds']}")
    print(f"  Decisioni cambiate:  {s['changed']} ({s['changed']/s['total']*100:.0f}%)")
    print(f"  Confidenza media:    {s['avg_confidence']:.1f}%")
    print("=" * 50)
