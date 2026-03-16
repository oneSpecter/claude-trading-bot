"""
BOT FOREX AI — LOOP PRINCIPALE
================================
Orchestrazione completa:

  1. Connessione MT5
  2. Download candele
  3. Pre-filtro tecnico (gratis, locale)
  4. Se setup rilevato → Claude AI (3 stadi)
  5. Decisione + validazione confidenza
  6. Esecuzione ordine su MT5
  7. Journal completo

Avvio:
  python bot.py          → live demo
  python bot.py --dry    → segnali senza ordini (usa MT5 reale)
  python bot.py --mock   → dati sintetici, nessun ordine, nessun MT5
  python bot.py --dry --mock → analisi completa su dati mock
  python bot.py --once   → un solo ciclo (debug)
  python bot.py --stats  → mostra statistiche journal
"""

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
    ADX_THRESHOLD, REQUIRE_ADX, REQUIRE_EMA_CROSS, REQUIRE_RSI_ALIGNED, REQUIRE_H4_CONFIRM,
    WEB_SEARCH_MIN_SCORE,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("ForexAIBot")

# Forza UTF-8 su stdout/stderr per evitare UnicodeEncodeError su Windows (cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import broker:
#   --dry o USE_MOCK=true → mock sempre (nessuna connessione MT5)
#   altrimenti            → MT5 reale se disponibile, mock come fallback
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

from indicators import compute_all, apply_prefilter, build_technical_summary
from claude_analyst import analyze, check_exit
from journal import log_decision, log_trade_result, print_stats, _load_json as _load_journal


STATUS_FILE   = "bot_status.json"
CONFIG_FILE   = Path("bot_config.json")
SETTINGS_FILE = Path("bot_settings.json")
STOP_FLAG     = Path("bot_stop.flag")
PID_FILE      = Path("bot.pid")

_last_status: dict = {}   # heartbeat: ultima scrittura status, riusata ogni 60s


def _acquire_pid_lock() -> bool:
    """
    Scrive il PID corrente in bot.pid.
    Se un altro processo con lo stesso PID è già attivo → ritorna False (bot duplicato).
    Gestisce PID file stale (processo morto ma file rimasto).
    """
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            # Controlla se il processo è ancora vivo (os.kill con signal 0 = no-op, solo check)
            os.kill(old_pid, 0)
            # Processo vivo → bot già in esecuzione
            return False
        except (ProcessLookupError, PermissionError):
            # Processo morto → PID file stale, lo sovrascriviamo
            pass
        except (ValueError, OSError):
            pass  # file corrotto, sovrascriviamo
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_pid_lock():
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


def _read_dry_run(default: bool) -> bool:
    """
    Legge la modalità dry_run da bot_config.json.
    Permette di cambiare modalità dalla dashboard senza riavviare.
    Fallback al valore di avvio se il file non esiste.
    """
    try:
        return bool(json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("dry_run", default))
    except Exception:
        return default


def _read_settings() -> dict:
    """
    Legge le impostazioni runtime da bot_settings.json.
    Ritorna dict vuoto se il file non esiste (usa i default di config.py).
    Le chiavi presenti sovrascrivono i default senza riavvio.
    """
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_status(data: dict):
    """Scrive lo stato corrente del bot su file (letto dalla dashboard)."""
    global _last_status
    _last_status = data
    try:
        Path(STATUS_FILE).write_text(
            json.dumps({**data, "timestamp": _utcnow().isoformat()},
                       ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def banner():
    print()
    print("=" * 56)
    print("  FOREX AI BOT -- Claude + MetaTrader 5")
    print("  Strategia: EMA x RSI x ATR + Analisi AI 3-stadi")
    print(f"  Simbolo: {SYMBOL:<10} Timeframe: {TIMEFRAME}")
    print("=" * 56)
    print()


def check_config():
    """Verifica configurazione prima di avviare."""
    errors = []
    if ANTHROPIC_API_KEY.startswith("sk-ant-XXXX"):
        errors.append("ANTHROPIC_API_KEY non configurata in config.py")
    if errors:
        for e in errors:
            log.error(f"❌ Configurazione mancante: {e}")
        return False
    return True


def _normalize_pos(pos) -> dict:
    """Normalizza una posizione (MT5 object o dict mock) in formato uniforme."""
    if isinstance(pos, dict):
        # Mock: time è stringa ISO
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
    # MT5 object: time è POSIX int
    posix = getattr(pos, "time", 0)
    open_time_dt = datetime.fromtimestamp(posix, tz=timezone.utc) if posix else None
    return {
        "ticket":      getattr(pos, "ticket",     None),
        "direction":   "BUY" if getattr(pos, "type", 0) == 0 else "SELL",
        "price":       getattr(pos, "price_open", 0.0),
        "sl":          getattr(pos, "sl",         0.0),
        "tp":          getattr(pos, "tp",         0.0),
        "lot":         getattr(pos, "volume",     0.0),
        "open_time_dt": open_time_dt,
    }


def _close_and_log(ticket, current_price: float, reason: str, dry_run: bool) -> bool:
    """Chiude una posizione e aggiorna il journal. Ritorna True se successo."""
    if dry_run:
        log.info(f"[DRY-RUN] Chiusura ticket {ticket} ({reason}) NON eseguita")
        return False
    result = broker.close_position(ticket)
    if result.get("success"):
        profit = result.get("profit", 0.0)
        emoji  = "✅" if profit > 0 else "❌"
        log.info(f"🤖 Trade {ticket} chiuso [{reason}] {emoji} ${profit:.2f}")
        log_trade_result(
            ticket=ticket,
            close_price=result.get("close_price", current_price),
            profit=profit,
            close_reason=reason,
            close_time=_utcnow().isoformat(),
        )
        return True
    return False


def _validate_trade(action: str, sl: float, tp: float, price: float) -> bool:
    """Controlla che SL/TP siano coerenti con la direzione prima di inviare l'ordine."""
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
        log.warning(f"⚠️  R/R basso: {rr:.2f} — considera se il trade vale il rischio")
    return True


def _get_daily_pnl() -> float:
    """Calcola il P&L realizzato oggi dal journal."""
    try:
        today   = _utcnow().date().isoformat()
        entries = _load_journal()
        return sum(
            float(e.get("profit") or 0)
            for e in entries
            if e.get("close_time", "").startswith(today)
        )
    except Exception:
        return 0.0


def _run_exit_checks(tech: dict, dry_run: bool, *,
                     max_trade_duration_h: int = None,
                     min_confidence: int = None):
    """
    Per ogni posizione aperta:
      1. Controlla se ha superato MAX_TRADE_DURATION_H:
         - Se perdita > TIME_EXIT_MAX_LOSS_PIPS → lascia lavorare lo SL, salta al check normale
         - Altrimenti → chiede a Claude se è il momento giusto (time_limit_hit=True)
      2. Chiede a Claude se chiudere anticipatamente (AI exit normale)
    Eseguito prima del session filter: il bot gestisce trade aperti H24.
    Riceve tech già calcolato da tick() per evitare ricalcoli.
    I parametri keyword-only sovrascrivono i default da config.py a runtime.
    """
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

        # ── 1. Time-based exit — dopo N ore chiede sempre a Claude ────
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
                        f"⏰ Ticket {ticket}: {hours_open:.1f}h aperto | "
                        f"P&L {pips:+.1f} pips → chiedo a Claude se chiudere"
                    )
                    try:
                        exit_dec   = check_exit(pos, current_price, tech,
                                                time_limit_hit=True)
                        action     = exit_dec.get("action", "HOLD")
                        confidence = exit_dec.get("confidence", 0)
                        reasoning  = exit_dec.get("reasoning", "")
                        log.info(
                            f"⏰ Claude time-exit ticket {ticket}: {action} "
                            f"| conf={confidence}% | {reasoning[:80]}"
                        )
                        if action == "CLOSE" and confidence >= _min_conf:
                            _close_and_log(ticket, current_price, "time_exit_ai", dry_run)
                        else:
                            log.info(
                                f"⏰ Claude suggerisce HOLD nonostante scadenza "
                                f"→ trade continua normalmente"
                            )
                    except Exception as e:
                        log.warning(f"Time exit check fallito ticket {ticket}: {e}")
                    continue  # Claude già interpellato — salta il check normale in questo tick

        # ── 2. AI exit check (throttle: salta nella prima ora) ───────
        if hours_open < 1.0:
            log.debug(f"Exit check skipped ticket {ticket}: solo {hours_open:.1f}h aperto")
            continue
        try:
            exit_dec   = check_exit(pos, current_price, tech)
            action     = exit_dec.get("action", "HOLD")
            confidence = exit_dec.get("confidence", 0)
            reasoning  = exit_dec.get("reasoning", "")

            log.info(f"🔍 Exit check ticket {ticket}: {action} "
                     f"| conf={confidence}% | {reasoning[:80]}")

            if action == "CLOSE" and confidence >= _min_conf:
                _close_and_log(ticket, current_price, "ai_exit", dry_run)
        except Exception as e:
            log.warning(f"Exit check fallito per ticket {ticket}: {e}")


def tick(dry_run: bool = False) -> bool:
    """
    Singolo ciclo del bot.
    Ritorna True se ha eseguito un trade, False altrimenti.
    """
    dry_run  = _read_dry_run(dry_run)   # può essere cambiato live dalla dashboard
    settings = _read_settings()         # impostazioni runtime dalla dashboard
    now = _utcnow()
    log.info(f"─── Tick {now.strftime('%Y-%m-%d %H:%M:%S')} UTC ───")
    _write_status({"phase": "scanning", "symbol": SYMBOL, "timeframe": TIMEFRAME,
                   "dry_run": dry_run, "use_mock": _force_mock,
                   "check_interval": CHECK_INTERVAL})

    # ── 1. Controlla trade chiusi (SL/TP raggiunto) ──────────────
    try:
        for trade in broker.get_closed_trades():
            profit = trade.get("profit", 0.0)
            updated = log_trade_result(
                ticket=trade.get("ticket"),
                close_price=trade.get("close_price", 0.0),
                profit=profit,
                close_reason=trade.get("reason", ""),
                close_time=trade.get("close_time", ""),
            )
            if updated:
                emoji = "✅" if profit > 0 else "❌"
                log.info(f"📊 Trade chiuso — {emoji} ${profit:.2f} "
                         f"| Motivo: {trade.get('reason','?')} "
                         f"| Ticket: {trade.get('ticket')}")
    except Exception as e:
        log.warning(f"Errore check trade chiusi: {e}")

    # ── 2. Dati mercato ──────────────────────────────────────────
    try:
        df = broker.get_candles()
    except Exception as e:
        log.error(f"Errore download candele: {e}")
        raise   # propaga al main loop → conta errori consecutivi

    log.info(f"Candele caricate: {len(df)} | Close={df['close'].iloc[-1]:.5f}")

    # ── 3. Candele H4 per il filtro trend principale ─────────────
    try:
        df_h4 = broker.get_candles(count=H4_CANDLES_LOAD, timeframe="H4")
    except Exception as e:
        log.warning(f"Candele H4 non disponibili: {e} — filtro H4 disabilitato")
        df_h4 = None

    # ── 4. Calcola indicatori + tech summary una sola volta per tick ──
    df_c = compute_all(df).dropna()
    tech = build_technical_summary(df_c, df_h4=df_h4)

    # ── 5. AI exit check — gestisce trade aperti anche fuori sessione ──
    _run_exit_checks(tech, dry_run,
                     max_trade_duration_h=settings.get("max_trade_duration_h"),
                     min_confidence=settings.get("min_confidence"))

    # ── 6. Session filter — blocca solo nuovi trade fuori orario e nel weekend ─
    _sf_enabled = settings.get("session_filter_enabled", SESSION_FILTER_ENABLED)
    _sf_start   = settings.get("session_start_utc",    SESSION_START_UTC)
    _sf_end     = settings.get("session_end_utc",      SESSION_END_UTC)
    # Forex chiuso: sabato tutto il giorno + domenica prima delle 22:00 UTC
    weekday = now.weekday()   # 0=Lun … 5=Sab, 6=Dom
    is_weekend = (weekday == 5) or (weekday == 6 and now.hour < 22)
    if is_weekend:
        log.info(f"📅 Mercati chiusi (weekend) — skip")
        return False
    if _sf_enabled:
        h = now.hour
        if not (_sf_start <= h < _sf_end):
            log.info(f"⏰ Fuori sessione ({h:02d}:00 UTC) — finestra attiva {_sf_start:02d}:00-{_sf_end:02d}:00 UTC")
            return False

    # ── 7. Limite perdita giornaliera ────────────────────────────
    _max_daily = settings.get("max_daily_loss_pct", MAX_DAILY_LOSS_PCT)
    if _max_daily > 0:
        daily_pnl = _get_daily_pnl()
        try:
            balance    = broker.get_account_info().get("balance", 0)
            loss_limit = balance * _max_daily / 100
            if daily_pnl < -loss_limit:
                log.warning(
                    f"🛑 Limite perdita giornaliera raggiunto: "
                    f"P&L oggi=${daily_pnl:.2f} < -{loss_limit:.2f} "
                    f"({_max_daily}% di ${balance:.0f}). "
                    f"Nessun nuovo trade oggi."
                )
                return False
        except Exception:
            pass

    # ── 8. Pre-filtro tecnico (gratuito, nessuna API call) ────────
    ok, reason = apply_prefilter(df_c, df_h4,
                                 require_ema_cross=settings.get("require_ema_cross"),
                                 require_rsi_aligned=settings.get("require_rsi_aligned"),
                                 adx_threshold=settings.get("adx_threshold"),
                                 require_adx=settings.get("require_adx"),
                                 require_h4_confirm=settings.get("require_h4_confirm"))
    log.info(f"Pre-filtro: {'✅ PASS' if ok else '⏭  SKIP'} — {reason}")

    if not ok:
        return False

    # ── 9. Controlla posizioni aperte ────────────────────────────
    open_pos = broker.get_open_positions()
    log.info(f"Posizioni aperte: {len(open_pos)}/{MAX_OPEN_TRADES}")

    if len(open_pos) >= MAX_OPEN_TRADES:
        log.info("Limite posizioni raggiunto. Skip.")
        return False

    # ── 10. Tech summary già calcolato al passo 4 — riuso diretto ──
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

    # ── 11. Claude AI (3 stadi) ──────────────────────────────────
    try:
        decision = analyze(tech,
                           min_confidence=settings.get("min_confidence"),
                           web_search_min_score=settings.get("web_search_min_score"))
    except Exception as e:
        log.error(f"Errore Claude API: {e}")
        return False

    log.info(
        f"🧠 Decisione AI: {decision['decision']} | "
        f"Confidenza: {decision['confidence']}% | "
        f"Regime: {decision.get('market_regime', '?')} | "
        f"Tech: {decision.get('technical_score', '?')} | "
        f"Fund: {decision.get('fundamental_score', '?')}"
    )
    log.info(f"   Reasoning: {decision.get('reasoning', '')}")
    log.info(f"   Devil advocate: {decision.get('devil_advocate', '')}")
    if decision.get("decision_changed_after_review"):
        log.info(f"   ⚠️  Decisione cambiata da {decision.get('initial_decision')} a {decision['decision']} dopo review!")

    # ── 12. Esecuzione ───────────────────────────────────────────
    action    = decision["decision"]
    executed  = False
    trade_res = None

    if action in ("BUY", "SELL"):
        # Validazione pre-esecuzione
        current_price = float(df_c["close"].iloc[-1])
        if not _validate_trade(action, decision.get("sl"), decision.get("tp"), current_price):
            log.error("Trade bloccato dalla validazione — HOLD forzato")
            action = "HOLD"
        elif dry_run:
            log.info(f"[DRY-RUN] Ordine {action} NON inviato (SL={decision['sl']} TP={decision['tp']})")
        else:
            try:
                trade_res = broker.open_trade(action, decision["sl"], decision["tp"])
                executed  = trade_res.get("success", False)
                if executed:
                    log.info(f"✅ Trade aperto — Ticket:{trade_res.get('ticket')} "
                             f"Price:{trade_res.get('price')}")
                else:
                    log.error(f"❌ Trade fallito: {trade_res}")
            except Exception as e:
                log.error(f"Errore apertura trade: {e}")
    else:
        log.info("HOLD — Nessun ordine.")

    # ── 13. Journal ──────────────────────────────────────────────
    log_decision(decision, tech, executed, trade_res)

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


def main():
    args = set(sys.argv[1:])

    if "--stats" in args:
        print_stats()
        return

    banner()

    if not _acquire_pid_lock():
        log.error("❌ Un'altra istanza del bot è già in esecuzione (bot.pid). Fermala prima di avviarne una nuova.")
        sys.exit(1)

    if not check_config():
        _release_pid_lock()
        sys.exit(1)

    dry_run  = "--dry"  in args
    run_once = "--once" in args

    if dry_run:
        log.info("Modalità DRY-RUN: nessun ordine reale sarà inviato")

    # Scrivi config iniziale (la dashboard può sovrascriverla in seguito)
    CONFIG_FILE.write_text(
        json.dumps({"dry_run": dry_run, "use_mock": _force_mock}, indent=2),
        encoding="utf-8",
    )
    if run_once:
        log.info("Modalità ONE-SHOT: eseguo un solo ciclo")

    # Connessione MT5 (saltata in mock mode)
    if not _force_mock:
        if not broker.connect():
            log.error("❌ Impossibile connettersi a MT5 — bot fermato.")
            log.error("   Verifica: MT5 aperto? Algo Trading abilitato? MT5_PATH corretto?")
            log.error("   Oppure usa modalità MOCK dalla dashboard per continuare senza MT5.")
            _write_status({"phase": "error", "symbol": SYMBOL, "timeframe": TIMEFRAME,
                           "error": "MT5 non raggiungibile"})
            sys.exit(1)
    else:
        broker.connect()  # no-op nel mock, ma inizializza lo stato interno

    try:
        account = broker.get_account_info()
        log.info(f"Account: Saldo={account['balance']:.2f} {account['currency']} | "
                 f"Leva={account.get('leverage','?')}x")

        if run_once:
            tick(dry_run)
            return

        # Scrivi subito lo stato "idle" così la dashboard vede il bot come running
        # prima ancora che il primo tick inizi (può richiedere secondi)
        _write_status({"phase": "idle", "symbol": SYMBOL, "timeframe": TIMEFRAME})
        log.info(f"Bot avviato. Controllo ogni {CHECK_INTERVAL}s. CTRL+C per fermare.")
        consecutive_errors = 0
        while True:
            if STOP_FLAG.exists():
                STOP_FLAG.unlink()
                log.info("🛑 Stop remoto ricevuto dalla dashboard.")
                break
            try:
                tick(dry_run)
                consecutive_errors = 0   # reset dopo tick OK
            except KeyboardInterrupt:
                raise
            except Exception as e:
                consecutive_errors += 1
                log.error(f"Errore nel tick ({consecutive_errors}/3): {e}", exc_info=True)
                if consecutive_errors >= 3:
                    if _force_mock:
                        # Mock mode: nessuna riconnessione possibile, fermati
                        log.error("❌ 3 errori consecutivi in mock mode — bot fermato.")
                        _write_status({"phase": "error", "symbol": SYMBOL,
                                       "timeframe": TIMEFRAME, "error": str(e)})
                        break

                    # ── Fuori sessione? Aspetta apertura mercati prima di riconnettersi ──
                    if SESSION_FILTER_ENABLED:
                        now_h = _utcnow().hour
                        if not (SESSION_START_UTC <= now_h < SESSION_END_UTC):
                            log.info(
                                f"⏸ Errori rilevati fuori sessione ({now_h:02d}:xx UTC) "
                                f"— attendo apertura {SESSION_START_UTC:02d}:00 UTC "
                                f"prima di riconnettermi a MT5"
                            )
                            _write_status({"phase": "waiting_session", "symbol": SYMBOL,
                                           "timeframe": TIMEFRAME})
                            stop_during_wait = False
                            while True:
                                time.sleep(60)
                                if STOP_FLAG.exists():
                                    STOP_FLAG.unlink()
                                    log.info("🛑 Stop remoto durante attesa sessione.")
                                    stop_during_wait = True
                                    break
                                if SESSION_START_UTC <= _utcnow().hour < SESSION_END_UTC:
                                    log.info("🔔 Sessione aperta — avvio riconnessione MT5")
                                    break
                            if stop_during_wait:
                                break  # esce dal loop principale

                    # ── Tentativo di riconnessione MT5 ──────────────────────────
                    log.info("🔄 Tentativo di riconnessione MT5...")
                    try:
                        broker.disconnect()
                    except Exception:
                        pass
                    if broker.connect():
                        log.info("✅ MT5 riconnesso — riprendo il loop")
                        consecutive_errors = 0
                    else:
                        log.error("❌ Riconnessione MT5 fallita — bot fermato.")
                        log.error("   Riavvia il bot manualmente dalla dashboard.")
                        _write_status({"phase": "error", "symbol": SYMBOL,
                                       "timeframe": TIMEFRAME,
                                       "error": "Riconnessione MT5 fallita"})
                        break

            log.info(f"Prossimo controllo tra {CHECK_INTERVAL}s...")
            # Controlla lo stop flag ogni 5s; heartbeat ogni 60s per non apparire "morto" alla dashboard
            deadline      = time.time() + CHECK_INTERVAL
            heartbeat_at  = time.time() + 60
            while time.time() < deadline:
                if STOP_FLAG.exists():
                    break
                time.sleep(5)
                if _last_status and time.time() >= heartbeat_at:
                    _write_status(_last_status)
                    heartbeat_at = time.time() + 60

    except KeyboardInterrupt:
        log.info("Bot fermato. Ciao! 👋")
    finally:
        broker.disconnect()
        _write_status({"phase": "stopped", "symbol": SYMBOL, "timeframe": TIMEFRAME})
        _release_pid_lock()
        print_stats()


if __name__ == "__main__":
    main()
