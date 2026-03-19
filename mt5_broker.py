"""
METATRADER 5 BROKER WRAPPER
----------------------------
Gestisce: connessione MT5, scaricamento candele, apertura/chiusura ordini,
stato account, posizioni aperte.

⚠️  MetaTrader5 funziona SOLO su Windows.
    Su Mac/Linux usa il modulo 'mt5_mock.py' per sviluppo.
"""

import logging
import pandas as pd
from datetime import datetime, timedelta, timezone
from config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER, MT5_PATH,
    SYMBOL, TIMEFRAME, CANDLES_LOAD, RISK_PCT
)

log = logging.getLogger("MT5Broker")

# Magic number per isolare le posizioni di questo bot dalle altre
# (sovrascrivibile da bot.py: broker.MAGIC = <valore>)
MAGIC: int = 20250314

# Mappa timeframe stringa → costante MT5
TF_MAP = {
    "M1":  1,   "M5":  5,   "M15": 15,  "M30": 30,
    "H1":  16385, "H4": 16388, "D1": 16408,
}

# Import MT5 (solo Windows)
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    log.warning("MetaTrader5 non disponibile su questo OS. Usa mt5_mock per sviluppo.")


def connect() -> bool:
    """Apre la connessione a MT5.

    Tenta 3 strategie in ordine crescente di aggressività:
    1. initialize() senza argomenti          → trova MT5 già aperto automaticamente
    2. initialize() con credenziali, no path → forza login senza lanciare nuovo processo
    3. initialize() con path + credenziali   → avvia MT5 dal percorso specificato
    """
    if not MT5_AVAILABLE:
        log.error("MT5 non installato. Installa su Windows con: pip install MetaTrader5")
        return False

    attempts = [
        # (descrizione, kwargs)
        ("senza argomenti",
         {}),
        ("con credenziali, senza path",
         {"login": int(MT5_LOGIN), "password": MT5_PASSWORD, "server": MT5_SERVER} if MT5_LOGIN else {}),
        ("con credenziali e path",
         {"path": MT5_PATH, "login": int(MT5_LOGIN), "password": MT5_PASSWORD, "server": MT5_SERVER} if MT5_PATH and MT5_LOGIN else {}),
    ]

    for desc, kwargs in attempts:
        if not kwargs and desc != "senza argomenti":
            continue   # salta se credenziali/path non configurati

        log.info(f"MT5 initialize() — tentativo: {desc}")
        mt5.shutdown()   # reset prima di ogni tentativo

        if not mt5.initialize(**kwargs):
            log.warning(f"  Fallito ({mt5.last_error()}) — prossimo tentativo")
            continue

        # initialize() ok → verifica account o esegui login esplicito
        info = mt5.account_info()
        if info:
            log.info(f"✅ MT5 connesso — Account: {info.login} | Saldo: {info.balance:.2f} {info.currency}")
            return True

        # initialize() ok ma non loggato → login esplicito
        if MT5_LOGIN:
            if mt5.login(int(MT5_LOGIN), password=MT5_PASSWORD, server=MT5_SERVER):
                info = mt5.account_info()
                log.info(f"✅ MT5 connesso — Account: {info.login} | Saldo: {info.balance:.2f} {info.currency}")
                return True
            log.warning(f"  Login fallito: {mt5.last_error()} — prossimo tentativo")

    log.error("❌ Tutti i tentativi MT5 falliti. Verifica:")
    log.error("   1. MT5 è aperto e visibile nel Task Manager?")
    log.error("   2. MT5 e Python girano con gli stessi privilegi (entrambi admin o entrambi utente)?")
    log.error("   3. Tools → Opzioni → Expert Advisors → 'Consenti trading algoritmico' spuntato?")
    log.error("   4. Il pulsante Algo Trading nella toolbar è verde?")
    log.error(f"   5. MT5_PATH nel .env è corretto? ({MT5_PATH})")
    return False


def disconnect():
    if MT5_AVAILABLE:
        mt5.shutdown()
        log.info("MT5 disconnesso.")


def get_candles(count: int = CANDLES_LOAD, timeframe: str = TIMEFRAME) -> pd.DataFrame:
    """Scarica le ultime N candele chiuse per il timeframe specificato."""
    if not MT5_AVAILABLE:
        raise RuntimeError("MT5 non disponibile")

    tf = TF_MAP.get(timeframe, mt5.TIMEFRAME_H1)
    rates = mt5.copy_rates_from_pos(SYMBOL, tf, 0, count + 1)

    if rates is None or len(rates) == 0:
        raise RuntimeError(f"Nessun dato ricevuto da MT5 per {SYMBOL}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df = df[["open", "high", "low", "close", "tick_volume"]]
    df.columns = ["open", "high", "low", "close", "volume"]

    # Escludi la candela corrente (ancora aperta)
    return df.iloc[:-1]


def get_account_info() -> dict:
    """Restituisce info account."""
    if not MT5_AVAILABLE:
        return {"balance": 10000, "equity": 10000, "currency": "USD"}
    info = mt5.account_info()
    return {
        "balance":  info.balance,
        "equity":   info.equity,
        "margin":   info.margin,
        "free_margin": info.margin_free,
        "currency": info.currency,
        "leverage": info.leverage,
    }


def get_open_positions() -> list:
    """Restituisce le posizioni aperte sul simbolo con il magic number di questo bot."""
    if not MT5_AVAILABLE:
        return []
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MAGIC]


def calculate_lot_size(price: float, sl: float) -> float:
    """
    Calcola il lot size basato sul rischio percentuale.
    rischio_$ = balance * RISK_PCT
    lot_size  = rischio_$ / (pip_risk * pip_value)
    """
    if not MT5_AVAILABLE:
        return 0.01

    info    = mt5.account_info()
    balance = info.balance
    risk_amount = balance * RISK_PCT
    pip_risk = abs(price - sl)

    sym_info = mt5.symbol_info(SYMBOL)
    if sym_info is None:
        return 0.01

    # Rischio in $ per lotto = contract_size × distanza_SL_in_prezzi
    # Equivalente a: pip_value_per_lot($10) × pip_risk_in_pips
    # Esempio: 100000 × 0.0015 = $150/lot → lot = $100/$150 = 0.67 lot
    contract_size = sym_info.trade_contract_size  # 100000 per forex standard
    pip_value = contract_size * pip_risk          # dollar risk per 1 lot

    lot = risk_amount / pip_value if pip_value > 0 else 0.01
    lot = round(max(lot, sym_info.volume_min), 2)
    lot = min(lot, sym_info.volume_max)

    return lot


def open_trade(direction: str, sl: float, tp: float) -> dict:
    """
    Apre un ordine a mercato.
    direction: "BUY" | "SELL"
    """
    if not MT5_AVAILABLE:
        log.warning("[MOCK] Ordine simulato — MT5 non disponibile")
        return {"success": True, "mock": True}

    tick = mt5.symbol_info_tick(SYMBOL)
    price = tick.ask if direction == "BUY" else tick.bid
    lot   = calculate_lot_size(price, sl)

    order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    SYMBOL,
        "volume":    lot,
        "type":      order_type,
        "price":     price,
        "sl":        sl,
        "tp":        tp,
        "deviation": 10,
        "magic":     MAGIC,
        "comment":   "ForexAIBot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log.error(f"Ordine fallito: retcode={result.retcode}, comment={result.comment}")
        return {"success": False, "retcode": result.retcode, "comment": result.comment}

    log.info(f"✅ {direction} eseguito — Ticket:{result.order} Price:{price:.5f} "
             f"Lot:{lot} SL:{sl} TP:{tp}")
    return {
        "success": True,
        "ticket":  result.order,
        "price":   price,
        "lot":     lot,
        "sl":      sl,
        "tp":      tp,
    }


def _deal_reason(code: int) -> str:
    return {0: "manual", 1: "expert", 2: "sl", 3: "tp", 4: "stop_out"}.get(code, f"code_{code}")


_last_deal_check: datetime | None = None


def get_closed_trades(lookback_hours: int = 24) -> list:
    """
    Restituisce i trade chiusi nelle ultime lookback_hours ore.
    Cerca deal di chiusura (DEAL_ENTRY_OUT) per il simbolo corrente.
    Usato per registrare profit/loss reali nel journal.
    """
    global _last_deal_check
    if not MT5_AVAILABLE:
        return []

    now     = datetime.now(timezone.utc)
    from_dt = _last_deal_check if _last_deal_check else (now - timedelta(hours=lookback_hours))
    _last_deal_check = now

    deals = mt5.history_deals_get(from_dt, now)
    if deals is None:
        return []

    closed = []
    for d in deals:
        if d.symbol != SYMBOL:
            continue
        if d.entry != mt5.DEAL_ENTRY_OUT:   # solo deal di chiusura
            continue
        if d.magic != MAGIC:                 # solo deal di questo bot
            continue
        closed.append({
            "ticket":      d.position_id,   # ticket della posizione originale
            "deal_id":     d.ticket,
            "close_price": d.price,
            "profit":      round(d.profit, 2),
            "swap":        round(d.swap, 2),
            "commission":  round(d.commission, 2),
            "volume":      d.volume,
            "close_time":  datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
            "reason":      _deal_reason(d.reason),
        })

    return closed


def close_position(ticket: int) -> dict:
    """Chiude una singola posizione per ticket (AI exit anticipato)."""
    if not MT5_AVAILABLE:
        return {"success": False}
    positions = mt5.positions_get(ticket=ticket)
    if not positions:
        log.warning(f"Ticket {ticket} non trovato tra le posizioni aperte")
        return {"success": False}
    pos        = positions[0]
    tick_info  = mt5.symbol_info_tick(SYMBOL)
    price      = tick_info.bid if pos.type == 0 else tick_info.ask
    order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       SYMBOL,
        "volume":       pos.volume,
        "type":         order_type,
        "position":     pos.ticket,
        "price":        price,
        "deviation":    10,
        "magic":        MAGIC,
        "comment":      "ForexAIBot_exit",
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log.error(f"Chiusura ticket {ticket} fallita: retcode={result.retcode}")
        return {"success": False, "retcode": result.retcode}
    log.info(f"✅ Posizione {ticket} chiusa (AI exit) @ {price:.5f}")
    return {"success": True, "ticket": ticket, "close_price": price}


