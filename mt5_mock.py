"""
MT5 MOCK — Simulatore per sviluppo su Mac/Linux
------------------------------------------------
Sostituisce MetaTrader5 con dati sintetici realistici.
Usato automaticamente quando MT5 non è disponibile.

Per usarlo nel bot principale, importa così:
  from mt5_mock import get_candles, get_account_info, ...
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

log = logging.getLogger("MT5Mock")

# Stato simulato
_mock_balance = 10000.0
_mock_positions = []
_mock_trade_counter = 1000


def connect() -> bool:
    log.info("[MOCK] Connessione MT5 simulata. Saldo: $10,000 demo")
    return True


def disconnect():
    log.info("[MOCK] Disconnessione MT5 simulata.")


def get_candles(count: int = 150) -> pd.DataFrame:
    """Genera candele EURUSD realistiche con trend e rumore."""
    np.random.seed(int(datetime.utcnow().timestamp()) % 1000)
    n = count

    # Simula un mercato con trend alternati
    base_price = 1.0850
    trend_changes = np.zeros(n)
    segment = n // 5
    for i in range(5):
        direction = 1 if i % 2 == 0 else -1
        strength  = np.random.uniform(0.0001, 0.0003)
        trend_changes[i*segment:(i+1)*segment] = direction * strength

    noise  = np.random.randn(n) * 0.0002
    prices = base_price + np.cumsum(trend_changes + noise)

    highs  = prices + np.abs(np.random.randn(n) * 0.0003)
    lows   = prices - np.abs(np.random.randn(n) * 0.0003)
    opens  = prices + np.random.randn(n) * 0.0001

    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    times = [now - timedelta(hours=i) for i in range(n, 0, -1)]

    df = pd.DataFrame({
        "open":   opens,
        "high":   highs,
        "low":    lows,
        "close":  prices,
        "volume": np.random.randint(500, 2000, n),
    }, index=pd.DatetimeIndex(times))

    log.info(f"[MOCK] {len(df)} candele generate | Close={prices[-1]:.5f}")
    return df


def get_account_info() -> dict:
    return {
        "balance":      _mock_balance,
        "equity":       _mock_balance,
        "margin":       0.0,
        "free_margin":  _mock_balance,
        "currency":     "USD",
        "leverage":     100,
    }


def get_open_positions() -> list:
    return _mock_positions


def calculate_lot_size(price: float, sl: float) -> float:
    risk_amount = _mock_balance * 0.01
    pip_risk    = abs(price - sl)
    if pip_risk == 0:
        return 0.01
    lot = risk_amount / (pip_risk * 100000)
    return round(max(lot, 0.01), 2)


def open_trade(direction: str, sl: float, tp: float) -> dict:
    global _mock_trade_counter, _mock_positions
    price = 1.0850 + np.random.randn() * 0.0001
    lot   = calculate_lot_size(price, sl)

    trade = {
        "ticket":    _mock_trade_counter,
        "direction": direction,
        "price":     price,
        "lot":       lot,
        "sl":        sl,
        "tp":        tp,
        "time":      datetime.utcnow().isoformat(),
    }
    _mock_positions.append(trade)
    _mock_trade_counter += 1

    log.info(f"[MOCK] {direction} eseguito — Ticket:{trade['ticket']} "
             f"Price:{price:.5f} Lot:{lot} SL:{sl} TP:{tp}")
    return {"success": True, **trade}


def close_all_positions():
    global _mock_positions
    log.info(f"[MOCK] Chiuse {len(_mock_positions)} posizioni.")
    _mock_positions = []
