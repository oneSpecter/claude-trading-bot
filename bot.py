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
  python bot.py --dry    → segnali senza ordini
  python bot.py --once   → un solo ciclo (debug)
  python bot.py --stats  → mostra statistiche journal
"""

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

# Import broker:
#   --dry o USE_MOCK=true → mock sempre (nessuna connessione MT5)
#   altrimenti            → MT5 reale se disponibile, mock come fallback
_force_mock = USE_MOCK or "--dry" in sys.argv
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

from indicators import compute_all, should_call_claude, build_technical_summary
from claude_analyst import analyze
from journal import log_decision, print_stats


STATUS_FILE = "bot_status.json"
STOP_FLAG   = Path("bot_stop.flag")


def _write_status(data: dict):
    """Scrive lo stato corrente del bot su file (letto dalla dashboard)."""
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
    print("╔══════════════════════════════════════════════════════╗")
    print("║   🤖  FOREX AI BOT — Claude + MetaTrader 5           ║")
    print("║   Strategia: EMA × RSI × ATR + Analisi AI 3-stadi   ║")
    print(f"║   Simbolo: {SYMBOL:<10} Timeframe: {TIMEFRAME:<8}              ║")
    print("╚══════════════════════════════════════════════════════╝")
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


def tick(dry_run: bool = False) -> bool:
    """
    Singolo ciclo del bot.
    Ritorna True se ha eseguito un trade, False altrimenti.
    """
    now = _utcnow()
    log.info(f"─── Tick {now.strftime('%Y-%m-%d %H:%M:%S')} UTC ───")
    _write_status({"phase": "scanning", "symbol": SYMBOL, "timeframe": TIMEFRAME,
                   "dry_run": dry_run})

    # ── 0. Session filter (opzionale) ────────────────────────────
    if SESSION_FILTER_ENABLED:
        h = now.hour
        if not (SESSION_START_UTC <= h < SESSION_END_UTC):
            log.info(f"⏰ Fuori sessione ({h:02d}:00 UTC) — finestra attiva {SESSION_START_UTC:02d}:00-{SESSION_END_UTC:02d}:00 UTC")
            return False

    # ── 1. Dati mercato ──────────────────────────────────────────
    try:
        df = broker.get_candles()
    except Exception as e:
        log.error(f"Errore download candele: {e}")
        return False

    log.info(f"Candele caricate: {len(df)} | Close={df['close'].iloc[-1]:.5f}")

    # ── 1b. Candele H4 per il filtro trend principale ─────────────
    try:
        df_h4 = broker.get_candles(count=H4_CANDLES_LOAD, timeframe="H4")
    except Exception as e:
        log.warning(f"Candele H4 non disponibili: {e} — filtro H4 disabilitato")
        df_h4 = None

    # ── 2. Pre-filtro tecnico (gratuito, nessuna API call) ────────
    ok, reason = should_call_claude(df, df_h4=df_h4)
    log.info(f"Pre-filtro: {'✅ PASS' if ok else '⏭  SKIP'} — {reason}")

    if not ok:
        return False

    # ── 3. Controlla posizioni aperte ────────────────────────────
    open_pos = broker.get_open_positions()
    log.info(f"Posizioni aperte: {len(open_pos)}/{MAX_OPEN_TRADES}")

    if len(open_pos) >= MAX_OPEN_TRADES:
        log.info("Limite posizioni raggiunto. Skip.")
        return False

    # ── 4. Build summary tecnico ─────────────────────────────────
    df_ind = compute_all(df)
    df_ind.dropna(inplace=True)
    tech = build_technical_summary(df_ind, df_h4=df_h4)

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

    # ── 5. Claude AI (3 stadi) ───────────────────────────────────
    try:
        decision = analyze(tech)
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

    # ── 6. Esecuzione ────────────────────────────────────────────
    action    = decision["decision"]
    executed  = False
    trade_res = None

    if action in ("BUY", "SELL"):
        if dry_run:
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

    # ── 7. Journal ───────────────────────────────────────────────
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

    if not check_config():
        sys.exit(1)

    dry_run  = "--dry"  in args
    run_once = "--once" in args

    if dry_run:
        log.info("Modalità DRY-RUN: nessun ordine reale sarà inviato")
    if run_once:
        log.info("Modalità ONE-SHOT: eseguo un solo ciclo")

    # Connessione MT5 (saltata in mock mode)
    if not _force_mock:
        if not broker.connect():
            log.error("Impossibile connettersi a MT5. Controlla le credenziali in config.py")
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

        log.info(f"Bot avviato. Controllo ogni {CHECK_INTERVAL}s. CTRL+C per fermare.")
        while True:
            if STOP_FLAG.exists():
                STOP_FLAG.unlink()
                log.info("🛑 Stop remoto ricevuto dalla dashboard.")
                break
            try:
                tick(dry_run)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log.error(f"Errore nel tick: {e}", exc_info=True)

            log.info(f"Prossimo controllo tra {CHECK_INTERVAL}s...")
            # Controlla lo stop flag ogni 5s invece di dormire CHECK_INTERVAL tutto in una volta
            deadline = time.time() + CHECK_INTERVAL
            while time.time() < deadline:
                if STOP_FLAG.exists():
                    break
                time.sleep(5)

    except KeyboardInterrupt:
        log.info("Bot fermato. Ciao! 👋")
    finally:
        broker.disconnect()
        _write_status({"phase": "stopped", "symbol": SYMBOL, "timeframe": TIMEFRAME})
        print_stats()


if __name__ == "__main__":
    main()
