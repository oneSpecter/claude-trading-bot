"""
BOT FOREX — LOOP PRINCIPALE (multi-bot)
========================================

Orchestrazione completa:
  1. Connessione MT5
  2. Download candele
  3. Strategia plugin (AI o manuale)
  4. Decisione + validazione
  5. Esecuzione ordine su MT5
  6. Journal completo

Avvio singolo bot (default, compatibile con versione precedente):
  python bot.py                          → live demo
  python bot.py --dry                    → watch mode, nessun ordine
  python bot.py --mock                   → dati sintetici, nessun MT5
  python bot.py --once                   → un solo ciclo (debug)
  python bot.py --stats                  → mostra statistiche journal

Avvio multi-bot:
  python bot.py --bot-id eurusd_ai  --strategy ema_rsi_ai   --dry
  python bot.py --bot-id gbpusd_man --strategy ema_rsi_manual --params '{"rsi_bull_min":45}'
"""

import argparse
import hashlib
import os
import sys
import time
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import (
    CHECK_INTERVAL, MAX_OPEN_TRADES, SYMBOL, TIMEFRAME,
    ANTHROPIC_API_KEY, H4_CANDLES_LOAD, USE_MOCK,
    SESSION_FILTER_ENABLED, SESSION_START_UTC, SESSION_END_UTC,
    MIN_CONFIDENCE, MAX_TRADE_DURATION_H, MAX_DAILY_LOSS_PCT,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Logging iniziale minimal (file handler aggiunto in main()) ────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("ForexAIBot")

# Forza UTF-8 su stdout/stderr (Windows cp1252 fix)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── Broker: determina mock mode prima dell'import ─────────────────
_force_mock = USE_MOCK or "--mock" in sys.argv
if _force_mock:
    import mt5_mock as broker
    log.info("Mock broker attivo — nessuna connessione MT5 richiesta")
else:
    try:
        import MetaTrader5
        import mt5_broker as broker
        log.info("MetaTrader5 rilevato — uso broker reale")
    except ImportError:
        import mt5_mock as broker
        log.warning("MetaTrader5 non disponibile — uso mock automatico")

from indicators import compute_all, build_technical_summary
import journal as _journal_mod
import claude_analyst as _analyst_mod

# ── Path globali (ridefiniti in main() per il bot specifico) ──────
BOT_DIR       = Path("bots") / "default"
STATUS_FILE   = BOT_DIR / "bot_status.json"
CONFIG_FILE   = BOT_DIR / "bot_config.json"
SETTINGS_FILE = BOT_DIR / "bot_settings.json"
STOP_FLAG     = BOT_DIR / "bot_stop.flag"
PID_FILE      = BOT_DIR / "bot.pid"

_last_status: dict = {}
_strategy = None        # istanza BaseStrategy, impostata in main()


# ══════════════════════════════════════════════════════════════════
#  HELPERS — PID lock
# ══════════════════════════════════════════════════════════════════

def _acquire_pid_lock() -> bool:
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            os.kill(old_pid, 0)
            return False      # processo vivo → duplicato
        except (ProcessLookupError, PermissionError):
            pass              # morto → stale
        except (ValueError, OSError):
            pass
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_pid_lock():
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  HELPERS — Config / Settings
# ══════════════════════════════════════════════════════════════════

def _read_dry_run(default: bool) -> bool:
    try:
        return bool(json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("dry_run", default))
    except Exception:
        return default


def _read_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════
#  HELPERS — Status
# ══════════════════════════════════════════════════════════════════

def _write_status(data: dict):
    global _last_status
    _last_status = data
    try:
        STATUS_FILE.write_text(
            json.dumps({**data, "timestamp": _utcnow().isoformat()},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════
#  HELPERS — Trade management
# ══════════════════════════════════════════════════════════════════

def _normalize_pos(pos) -> dict:
    if isinstance(pos, dict):
        open_time_dt = None
        ts = pos.get("time", "")
        if ts:
            try:
                open_time_dt = datetime.fromisoformat(ts)
                if open_time_dt.tzinfo is None:
                    open_time_dt = open_time_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return {**pos, "open_time_dt": open_time_dt}
    posix = getattr(pos, "time", 0)
    open_time_dt = datetime.fromtimestamp(posix, tz=timezone.utc) if posix else None
    return {
        "ticket":       getattr(pos, "ticket",     None),
        "direction":    "BUY" if getattr(pos, "type", 0) == 0 else "SELL",
        "price":        getattr(pos, "price_open", 0.0),
        "sl":           getattr(pos, "sl",         0.0),
        "tp":           getattr(pos, "tp",         0.0),
        "lot":          getattr(pos, "volume",     0.0),
        "open_time_dt": open_time_dt,
    }


def _close_and_log(ticket, current_price: float, reason: str, dry_run: bool) -> bool:
    if dry_run:
        log.info(f"[DRY-RUN] Chiusura ticket {ticket} ({reason}) NON eseguita")
        return False
    result = broker.close_position(ticket)
    if result.get("success"):
        profit = result.get("profit", 0.0)
        emoji  = "✅" if profit > 0 else "❌"
        log.info(f"Trade {ticket} chiuso [{reason}] {emoji} ${profit:.2f}")
        _journal_mod.log_trade_result(
            ticket=ticket,
            close_price=result.get("close_price", current_price),
            profit=profit,
            close_reason=reason,
            close_time=_utcnow().isoformat(),
        )
        return True
    return False


def _validate_trade(action: str, sl: float, tp: float, price: float) -> bool:
    if not sl or not tp or not price:
        log.warning("Validazione trade: SL/TP/prezzo mancanti")
        return False
    if action == "BUY":
        if sl >= price:
            log.error(f"Trade invalido: BUY ma SL {sl:.5f} >= prezzo {price:.5f}")
            return False
        if tp <= price:
            log.error(f"Trade invalido: BUY ma TP {tp:.5f} <= prezzo {price:.5f}")
            return False
    elif action == "SELL":
        if sl <= price:
            log.error(f"Trade invalido: SELL ma SL {sl:.5f} <= prezzo {price:.5f}")
            return False
        if tp >= price:
            log.error(f"Trade invalido: SELL ma TP {tp:.5f} >= prezzo {price:.5f}")
            return False
    rr = abs(tp - price) / abs(price - sl) if abs(price - sl) > 0 else 0
    if rr < 1.0:
        log.warning(f"R/R basso: {rr:.2f} — considera se il trade vale il rischio")
    return True


def _get_daily_pnl() -> float:
    try:
        today   = _utcnow().date().isoformat()
        entries = _journal_mod._load_json()
        return sum(
            float(e.get("profit") or 0)
            for e in entries
            if e.get("close_time", "").startswith(today)
        )
    except Exception:
        return 0.0


# ══════════════════════════════════════════════════════════════════
#  EXIT CHECKS — usa strategy.should_exit()
# ══════════════════════════════════════════════════════════════════

def _run_exit_checks(tech: dict, dry_run: bool, *,
                     max_trade_duration_h: int = None,
                     min_confidence: int = None):
    _max_dur  = MAX_TRADE_DURATION_H if max_trade_duration_h is None else max_trade_duration_h
    _min_conf = MIN_CONFIDENCE       if min_confidence       is None else min_confidence

    try:
        open_positions = broker.get_open_positions()
    except Exception as e:
        log.warning(f"Exit check: impossibile leggere posizioni — {e}")
        return

    if not open_positions:
        return

    now           = _utcnow()
    current_price = float(tech["price"])

    for raw_pos in open_positions:
        pos    = _normalize_pos(raw_pos)
        ticket = pos.get("ticket")

        # ── Time-based exit ────────────────────────────────────────
        hours_open = 0.0
        if _max_dur > 0:
            open_time_dt = pos.get("open_time_dt")
            if open_time_dt:
                hours_open = (now - open_time_dt).total_seconds() / 3600
                if hours_open >= _max_dur:
                    entry     = float(pos.get("price", 0))
                    direction = pos.get("direction", "BUY")
                    pips      = round(
                        (current_price - entry if direction == "BUY"
                         else entry - current_price) * 10_000, 1
                    )
                    log.info(
                        f"Ticket {ticket}: {hours_open:.1f}h aperto | "
                        f"P&L {pips:+.1f} pips → chiedo alla strategia se chiudere"
                    )
                    try:
                        exit_dec   = _strategy.should_exit(pos, current_price, tech,
                                                           time_limit_hit=True)
                        action     = exit_dec.get("action", "HOLD")
                        confidence = exit_dec.get("confidence", 0)
                        reasoning  = exit_dec.get("reasoning", "")
                        log.info(
                            f"Time-exit ticket {ticket}: {action} "
                            f"| conf={confidence}% | {reasoning[:80]}"
                        )
                        if action == "CLOSE" and confidence >= _min_conf:
                            _close_and_log(ticket, current_price, "time_exit", dry_run)
                        else:
                            log.info("Strategia suggerisce HOLD nonostante scadenza — trade continua")
                    except Exception as e:
                        log.warning(f"Time exit check fallito ticket {ticket}: {e}")
                    continue

        # ── AI exit check (throttle: salta prima ora) ──────────────
        if hours_open < 1.0:
            log.debug(f"Exit check skipped ticket {ticket}: solo {hours_open:.1f}h aperto")
            continue
        try:
            exit_dec   = _strategy.should_exit(pos, current_price, tech)
            action     = exit_dec.get("action", "HOLD")
            confidence = exit_dec.get("confidence", 0)
            reasoning  = exit_dec.get("reasoning", "")

            log.info(f"Exit check ticket {ticket}: {action} "
                     f"| conf={confidence}% | {reasoning[:80]}")

            if action == "CLOSE" and confidence >= _min_conf:
                _close_and_log(ticket, current_price, "early_exit", dry_run)
        except Exception as e:
            log.warning(f"Exit check fallito per ticket {ticket}: {e}")


# ══════════════════════════════════════════════════════════════════
#  TICK — ciclo principale
# ══════════════════════════════════════════════════════════════════

def tick(dry_run: bool = False) -> bool:
    """Singolo ciclo del bot. Ritorna True se ha eseguito un trade."""
    dry_run  = _read_dry_run(dry_run)
    settings = _read_settings()
    now      = _utcnow()
    log.info(f"--- Tick {now.strftime('%Y-%m-%d %H:%M:%S')} UTC ---")
    _write_status({"phase": "scanning", "symbol": SYMBOL, "timeframe": TIMEFRAME,
                   "dry_run": dry_run, "use_mock": _force_mock,
                   "check_interval": CHECK_INTERVAL})

    # ── 1. Trade chiusi (SL/TP raggiunto) ────────────────────────
    try:
        for trade in broker.get_closed_trades():
            profit  = trade.get("profit", 0.0)
            updated = _journal_mod.log_trade_result(
                ticket=trade.get("ticket"),
                close_price=trade.get("close_price", 0.0),
                profit=profit,
                close_reason=trade.get("reason", ""),
                close_time=trade.get("close_time", ""),
            )
            if updated:
                emoji = "✅" if profit > 0 else "❌"
                log.info(f"Trade chiuso — {emoji} ${profit:.2f} "
                         f"| Motivo: {trade.get('reason','?')} "
                         f"| Ticket: {trade.get('ticket')}")
    except Exception as e:
        log.warning(f"Errore check trade chiusi: {e}")

    # ── 2. Candele H1 ─────────────────────────────────────────────
    try:
        df = broker.get_candles()
    except Exception as e:
        log.error(f"Errore download candele: {e}")
        raise

    log.info(f"Candele caricate: {len(df)} | Close={df['close'].iloc[-1]:.5f}")

    # ── 3. Candele H4 (filtro trend) ──────────────────────────────
    try:
        df_h4 = broker.get_candles(count=H4_CANDLES_LOAD, timeframe="H4")
    except Exception as e:
        log.warning(f"Candele H4 non disponibili: {e} — filtro H4 disabilitato")
        df_h4 = None

    # ── 4. Indicatori + tech summary ──────────────────────────────
    df_c = compute_all(df).dropna()
    tech = build_technical_summary(df_c, df_h4=df_h4)

    # ── 5. Exit checks posizioni aperte ───────────────────────────
    _run_exit_checks(tech, dry_run,
                     max_trade_duration_h=settings.get("max_trade_duration_h"),
                     min_confidence=settings.get("min_confidence"))

    # ── 6. Session filter ─────────────────────────────────────────
    _sf_enabled = settings.get("session_filter_enabled", SESSION_FILTER_ENABLED)
    _sf_start   = settings.get("session_start_utc",      SESSION_START_UTC)
    _sf_end     = settings.get("session_end_utc",        SESSION_END_UTC)
    weekday     = now.weekday()
    is_weekend  = (weekday == 5) or (weekday == 6 and now.hour < 22)
    if is_weekend:
        log.info("Mercati chiusi (weekend) — skip")
        return False
    if _sf_enabled:
        h = now.hour
        if not (_sf_start <= h < _sf_end):
            log.info(f"Fuori sessione ({h:02d}:00 UTC) — finestra attiva {_sf_start:02d}:00-{_sf_end:02d}:00 UTC")
            return False

    # ── 7. Limite perdita giornaliera ─────────────────────────────
    _max_daily = settings.get("max_daily_loss_pct", MAX_DAILY_LOSS_PCT)
    if _max_daily > 0:
        daily_pnl = _get_daily_pnl()
        try:
            balance    = broker.get_account_info().get("balance", 0)
            loss_limit = balance * _max_daily / 100
            if daily_pnl < -loss_limit:
                log.warning(
                    f"Limite perdita giornaliera raggiunto: "
                    f"P&L oggi=${daily_pnl:.2f} < -{loss_limit:.2f} "
                    f"({_max_daily}% di ${balance:.0f}). Nessun nuovo trade."
                )
                return False
        except Exception:
            pass

    # ── 8. Posizioni aperte ───────────────────────────────────────
    open_pos = broker.get_open_positions()
    log.info(f"Posizioni aperte: {len(open_pos)}/{MAX_OPEN_TRADES}")
    if len(open_pos) >= MAX_OPEN_TRADES:
        log.info("Limite posizioni raggiunto. Skip.")
        return False

    # ── 9. Log setup tecnico ──────────────────────────────────────
    log.info(f"Setup tecnico: EMA_trend={tech['ema_trend']} RSI={tech['rsi']} "
             f"ADX={tech['adx']} ({tech['adx_trend']}) ATR={tech['atr']}")
    _write_status({
        "phase":      "analyzing",
        "symbol":     SYMBOL,
        "timeframe":  TIMEFRAME,
        "dry_run":    dry_run,
        "price":      tech.get("price"),
        "ema_trend":  tech.get("ema_trend"),
        "rsi":        tech.get("rsi"),
        "adx":        tech.get("adx"),
        "adx_trend":  tech.get("adx_trend"),
        "h4_bias":    tech.get("h4_bias"),
    })

    # ── 10. Strategia (AI o manuale) ─────────────────────────────
    context = {"settings": settings, "dry_run": dry_run, "symbol": SYMBOL}
    try:
        decision = _strategy.should_trade(df_c, df_h4, tech, context)
    except Exception as e:
        log.error(f"Errore strategia: {e}")
        return False

    # Salta il logging dettagliato se la strategia ha già filtrato internamente
    if not decision.get("_prefilter_skip"):
        log.info(
            f"Decisione: {decision.get('decision', 'HOLD')} | "
            f"Confidenza: {decision.get('confidence', 0)}% | "
            f"Regime: {decision.get('market_regime', '?')}"
        )
    log.info(f"   Reasoning: {decision.get('reasoning', decision.get('reason', ''))}")
    if decision.get("decision_changed_after_review"):
        log.info(f"   Decisione cambiata da {decision.get('initial_decision')} "
                 f"a {decision['decision']} dopo review!")

    # ── 11. Esecuzione ────────────────────────────────────────────
    action    = decision.get("decision", "HOLD")
    executed  = False
    trade_res = None

    if action in ("BUY", "SELL"):
        current_price = float(df_c["close"].iloc[-1])
        if not _validate_trade(action, decision.get("sl"), decision.get("tp"), current_price):
            log.error("Trade bloccato dalla validazione — HOLD forzato")
            action = "HOLD"
        elif dry_run:
            log.info(f"[DRY-RUN] Ordine {action} NON inviato (SL={decision.get('sl')} TP={decision.get('tp')})")
        else:
            try:
                trade_res = broker.open_trade(action, decision["sl"], decision["tp"])
                executed  = trade_res.get("success", False)
                if executed:
                    log.info(f"Trade aperto — Ticket:{trade_res.get('ticket')} "
                             f"Price:{trade_res.get('price')}")
                else:
                    log.error(f"Trade fallito: {trade_res}")
            except Exception as e:
                log.error(f"Errore apertura trade: {e}")
    else:
        log.info("HOLD — Nessun ordine.")

    # ── 12. Journal ───────────────────────────────────────────────
    _journal_mod.log_decision(decision, tech, executed, trade_res)

    _write_status({
        "phase":           "idle",
        "symbol":          SYMBOL,
        "timeframe":       TIMEFRAME,
        "dry_run":         dry_run,
        "price":           tech.get("price"),
        "ema_trend":       tech.get("ema_trend"),
        "rsi":             tech.get("rsi"),
        "adx":             tech.get("adx"),
        "adx_trend":       tech.get("adx_trend"),
        "h4_bias":         tech.get("h4_bias"),
        "last_decision":   decision.get("decision"),
        "last_confidence": decision.get("confidence"),
        "last_regime":     decision.get("market_regime"),
        "web_search_done": decision.get("web_search_done", False),
        "tech_score_s1":   decision.get("tech_score_s1"),
    })
    return executed


# ══════════════════════════════════════════════════════════════════
#  BANNER / CONFIG CHECK
# ══════════════════════════════════════════════════════════════════

def banner(bot_id: str, strategy_name: str):
    print()
    print("=" * 56)
    print("  FOREX AI BOT -- Claude + MetaTrader 5")
    print(f"  Bot ID:    {bot_id}")
    print(f"  Strategia: {strategy_name}")
    print(f"  Simbolo:   {SYMBOL:<10} Timeframe: {TIMEFRAME}")
    print("=" * 56)
    print()


_AI_STRATEGIES = {"ema_rsi_ai", "ema_rsi_ai_main", "ema_rsi_ai_scalp"}

def check_config(strategy_name: str) -> bool:
    errors = []
    if strategy_name in _AI_STRATEGIES and ANTHROPIC_API_KEY.startswith("sk-ant-XXXX"):
        errors.append(f"ANTHROPIC_API_KEY non configurata (richiesta dalla strategia AI '{strategy_name}')")
    for e in errors:
        log.error(f"Configurazione mancante: {e}")
    return len(errors) == 0


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    global BOT_DIR, STATUS_FILE, CONFIG_FILE, SETTINGS_FILE, STOP_FLAG, PID_FILE
    global _strategy, _force_mock

    # ── 1. Parse args ─────────────────────────────────────────────
    parser = argparse.ArgumentParser(description="Forex AI Bot")
    parser.add_argument("--bot-id",   default="default",      help="ID univoco del bot")
    parser.add_argument("--strategy", default="ema_rsi_ai",   help="Nome strategia (strategies/<name>.py)")
    parser.add_argument("--params",   default="{}",           help="Parametri strategia in JSON")
    parser.add_argument("--dry",      action="store_true",    help="Watch mode — nessun ordine reale")
    parser.add_argument("--mock",     action="store_true",    help="Usa broker simulato")
    parser.add_argument("--once",     action="store_true",    help="Un solo ciclo (debug)")
    parser.add_argument("--stats",    action="store_true",    help="Mostra statistiche journal")
    args = parser.parse_args()

    bot_id        = args.bot_id
    strategy_name = args.strategy

    # ── 1b. Imposta magic number unico per bot ────────────────────
    # Derivato dal bot_id con MD5 → stabile tra riavvii, univoco per nome
    _magic = int(hashlib.md5(bot_id.encode()).hexdigest()[:6], 16) % 900000 + 100000
    broker.MAGIC = _magic

    # ── 2. Crea directory bot ─────────────────────────────────────
    BOT_DIR       = Path("bots") / bot_id
    BOT_DIR.mkdir(parents=True, exist_ok=True)

    STATUS_FILE   = BOT_DIR / "bot_status.json"
    CONFIG_FILE   = BOT_DIR / "bot_config.json"
    SETTINGS_FILE = BOT_DIR / "bot_settings.json"
    STOP_FLAG     = BOT_DIR / "bot_stop.flag"
    PID_FILE      = BOT_DIR / "bot.pid"

    # ── 3. Aggiungi file handler al logger ────────────────────────
    log_file     = BOT_DIR / "bot.log"
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logging.getLogger().addHandler(file_handler)

    # ── 4. Inizializza journal e costi per questo bot ─────────────
    _journal_mod.init(BOT_DIR)
    _analyst_mod.init(BOT_DIR, bot_id)

    # ── 5. Stats mode ─────────────────────────────────────────────
    if args.stats:
        _journal_mod.print_stats()
        return

    banner(bot_id, strategy_name)

    # ── 6. PID lock ───────────────────────────────────────────────
    if not _acquire_pid_lock():
        log.error(
            f"Un'altra istanza del bot '{bot_id}' e' gia' in esecuzione. "
            f"Fermala prima di avviarne una nuova."
        )
        sys.exit(1)

    # ── 7. Controlla config ───────────────────────────────────────
    if not check_config(strategy_name):
        _release_pid_lock()
        sys.exit(1)

    dry_run  = args.dry
    run_once = args.once

    # ── 8. Aggiorna _force_mock se --mock passato via args ────────
    if args.mock and not _force_mock:
        log.info("Mock forzato via --mock")

    if dry_run:
        log.info("Modalita' DRY-RUN: nessun ordine reale sara' inviato")

    # Scrivi config iniziale
    CONFIG_FILE.write_text(
        json.dumps({"dry_run": dry_run, "use_mock": _force_mock}, indent=2),
        encoding="utf-8",
    )
    if run_once:
        log.info("Modalita' ONE-SHOT: eseguo un solo ciclo")

    # ── 9. Carica strategia ───────────────────────────────────────
    from strategies import load_strategy
    try:
        strategy_params = json.loads(args.params)
        _strategy = load_strategy(strategy_name, strategy_params)
        log.info(f"Strategia caricata: {strategy_name} | params={strategy_params} | magic={_magic}")
    except Exception as e:
        log.error(f"Impossibile caricare la strategia '{strategy_name}': {e}")
        _release_pid_lock()
        sys.exit(1)

    # ── 10. Connessione MT5 ───────────────────────────────────────
    if not _force_mock:
        if not broker.connect():
            log.error("Impossibile connettersi a MT5 — bot fermato.")
            _write_status({"phase": "error", "symbol": SYMBOL, "timeframe": TIMEFRAME,
                           "error": "MT5 non raggiungibile"})
            _release_pid_lock()
            sys.exit(1)
    else:
        broker.connect()

    try:
        account = broker.get_account_info()
        log.info(f"Account: Saldo={account['balance']:.2f} {account['currency']} | "
                 f"Leva={account.get('leverage','?')}x")

        if run_once:
            tick(dry_run)
            return

        _write_status({"phase": "idle", "symbol": SYMBOL, "timeframe": TIMEFRAME,
                       "bot_id": bot_id, "strategy": strategy_name})
        log.info(f"Bot avviato. Controllo ogni {CHECK_INTERVAL}s. CTRL+C per fermare.")
        consecutive_errors = 0

        while True:
            if STOP_FLAG.exists():
                STOP_FLAG.unlink()
                log.info("Stop remoto ricevuto dalla dashboard.")
                break
            try:
                tick(dry_run)
                consecutive_errors = 0
            except KeyboardInterrupt:
                raise
            except Exception as e:
                consecutive_errors += 1
                log.error(f"Errore nel tick ({consecutive_errors}/3): {e}", exc_info=True)
                if consecutive_errors >= 3:
                    if _force_mock:
                        log.error("3 errori consecutivi in mock mode — bot fermato.")
                        _write_status({"phase": "error", "symbol": SYMBOL,
                                       "timeframe": TIMEFRAME, "error": str(e)})
                        break

                    if SESSION_FILTER_ENABLED:
                        now_h = _utcnow().hour
                        if not (SESSION_START_UTC <= now_h < SESSION_END_UTC):
                            log.info(
                                f"Errori rilevati fuori sessione ({now_h:02d}:xx UTC) "
                                f"— attendo apertura {SESSION_START_UTC:02d}:00 UTC"
                            )
                            _write_status({"phase": "waiting_session", "symbol": SYMBOL,
                                           "timeframe": TIMEFRAME})
                            stop_during_wait = False
                            while True:
                                time.sleep(60)
                                if STOP_FLAG.exists():
                                    STOP_FLAG.unlink()
                                    log.info("Stop remoto durante attesa sessione.")
                                    stop_during_wait = True
                                    break
                                if SESSION_START_UTC <= _utcnow().hour < SESSION_END_UTC:
                                    log.info("Sessione aperta — avvio riconnessione MT5")
                                    break
                            if stop_during_wait:
                                break

                    log.info("Tentativo di riconnessione MT5...")
                    try:
                        broker.disconnect()
                    except Exception:
                        pass
                    if broker.connect():
                        log.info("MT5 riconnesso — riprendo il loop")
                        consecutive_errors = 0
                    else:
                        log.error("Riconnessione MT5 fallita — bot fermato.")
                        _write_status({"phase": "error", "symbol": SYMBOL,
                                       "timeframe": TIMEFRAME,
                                       "error": "Riconnessione MT5 fallita"})
                        break

            log.info(f"Prossimo controllo tra {CHECK_INTERVAL}s...")
            deadline     = time.time() + CHECK_INTERVAL
            heartbeat_at = time.time() + 60
            while time.time() < deadline:
                if STOP_FLAG.exists():
                    break
                time.sleep(5)
                if _last_status and time.time() >= heartbeat_at:
                    _write_status(_last_status)
                    heartbeat_at = time.time() + 60

    except KeyboardInterrupt:
        log.info("Bot fermato. Ciao!")
    finally:
        broker.disconnect()
        _write_status({"phase": "stopped", "symbol": SYMBOL, "timeframe": TIMEFRAME})
        _release_pid_lock()
        _journal_mod.print_stats()


if __name__ == "__main__":
    main()
