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
from datetime import datetime
from config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER,
    SYMBOL, TIMEFRAME, CANDLES_LOAD, H4_CANDLES_LOAD, RISK_PCT
)

log = logging.getLogger("MT5Broker")

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
    """Apre la connessione a MT5."""
    if not MT5_AVAILABLE:
        log.error("MT5 non installato. Installa su Windows con: pip install MetaTrader5")
        return False

    if not mt5.initialize():
        log.error(f"Inizializzazione MT5 fallita: {mt5.last_error()}")
        return False

    authorized = mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if not authorized:
        log.error(f"Login MT5 fallito: {mt5.last_error()}")
        mt5.shutdown()
        return False

    info = mt5.account_info()
    log.info(f"✅ MT5 connesso — Account: {info.login} | Saldo: {info.balance:.2f} {info.currency}")
    return True


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
    """Restituisce le posizioni aperte sul simbolo."""
    if not MT5_AVAILABLE:
        return []
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    return list(positions)


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

    # Per EURUSD: pip_value ≈ 10$ per 1 lotto standard
    contract_size = sym_info.trade_contract_size  # tipicamente 100000
    pip_value = contract_size * pip_risk

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
        "magic":     20250314,
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


def close_all_positions():
    """Chiude tutte le posizioni aperte sul simbolo."""
    if not MT5_AVAILABLE:
        return
    positions = get_open_positions()
    for pos in positions:
        tick = mt5.symbol_info_tick(SYMBOL)
        price = tick.bid if pos.type == 0 else tick.ask
        order_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        request = {
            "action":   mt5.TRADE_ACTION_DEAL,
            "symbol":   SYMBOL,
            "volume":   pos.volume,
            "type":     order_type,
            "position": pos.ticket,
            "price":    price,
            "deviation": 10,
            "magic":    20250314,
            "comment":  "ForexAIBot_close",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        mt5.order_send(request)
        log.info(f"Posizione {pos.ticket} chiusa.")
