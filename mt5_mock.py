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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from config import MOCK_DATA_FILE, TIMEFRAME as _TF

log = logging.getLogger("MT5Mock")

# Stato simulato
_mock_balance        = 10000.0
_mock_positions      = []
_mock_closed_trades  = []   # trade chiusi in attesa di essere letti
_mock_trade_counter  = 1000
_last_close          = 1.0850  # aggiornato a ogni get_candles()


def _load_csv(filepath: str, count: int) -> "pd.DataFrame | None":
    """
    Carica candele da file CSV con dati storici reali.

    Formati supportati:
      MT5 export standard:  Date,Time,Open,High,Low,Close,Volume
      MT5 con brackets:     <DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>
      Colonna singola:      datetime,open,high,low,close,volume
    """
    try:
        df = pd.read_csv(filepath)
        # Normalizza nomi colonne (minuscolo, rimuovi < >)
        df.columns = [c.strip().strip('<>').lower() for c in df.columns]

        # Costruisci indice datetime
        if 'date' in df.columns and 'time' in df.columns:
            df['_dt'] = pd.to_datetime(df['date'].astype(str) + ' ' + df['time'].astype(str))
            df = df.drop(columns=['date', 'time'])
        elif 'datetime' in df.columns:
            df['_dt'] = pd.to_datetime(df['datetime'])
            df = df.drop(columns=['datetime'])
        else:
            # Prima colonna come datetime
            df['_dt'] = pd.to_datetime(df.iloc[:, 0])
            df = df.iloc[:, 1:]

        df = df.set_index('_dt').sort_index()

        # Rinomina alias comuni
        aliases = {
            'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close',
            'tickvol': 'volume', 'vol': 'volume', 'tick_volume': 'volume',
        }
        df = df.rename(columns={k: v for k, v in aliases.items() if k in df.columns})

        required = ['open', 'high', 'low', 'close']
        missing = [c for c in required if c not in df.columns]
        if missing:
            log.warning(f"[MOCK CSV] Colonne mancanti {missing} — colonne trovate: {list(df.columns)}")
            return None

        if 'volume' not in df.columns:
            df['volume'] = 1000

        df = df[['open', 'high', 'low', 'close', 'volume']].dropna()
        result = df.tail(count)
        log.info(f"[MOCK CSV] {len(result)} candele caricate da {filepath} | "
                 f"Close={result['close'].iloc[-1]:.5f}")
        return result

    except Exception as e:
        log.warning(f"[MOCK CSV] Errore caricamento {filepath}: {e}")
        return None


def _check_sl_tp(df: "pd.DataFrame"):
    """
    Simula la chiusura automatica delle posizioni mock quando SL o TP viene toccato.
    Controlla high/low dell'ultima candela contro SL/TP di ogni posizione aperta.
    """
    global _mock_positions, _mock_closed_trades, _mock_balance
    if not _mock_positions:
        return

    last = df.iloc[-1]
    high, low = float(last["high"]), float(last["low"])
    remaining = []

    for pos in _mock_positions:
        direction = pos["direction"]
        entry     = pos["price"]
        sl, tp    = pos["sl"], pos["tp"]
        lot       = pos["lot"]

        hit_sl = (direction == "BUY"  and low  <= sl) or (direction == "SELL" and high >= sl)
        hit_tp = (direction == "BUY"  and high >= tp) or (direction == "SELL" and low  <= tp)

        if hit_tp:
            close_price = tp
            reason      = "tp"
        elif hit_sl:
            close_price = sl
            reason      = "sl"
        else:
            remaining.append(pos)
            continue

        profit = round(
            (close_price - entry if direction == "BUY" else entry - close_price)
            * lot * 100_000, 2
        )
        _mock_balance += profit

        closed = {
            "ticket":      pos["ticket"],
            "close_price": round(close_price, 5),
            "profit":      profit,
            "swap":        0.0,
            "commission":  0.0,
            "volume":      lot,
            "close_time":  datetime.now(timezone.utc).isoformat(),
            "reason":      reason,
        }
        _mock_closed_trades.append(closed)
        emoji = "✅" if profit > 0 else "❌"
        log.info(f"[MOCK] {emoji} Trade {pos['ticket']} chiuso per {reason} | "
                 f"Profit: ${profit:.2f} | Saldo: ${_mock_balance:.2f}")

    _mock_positions = remaining


def get_closed_trades() -> list:
    """Ritorna i trade chiusi recentemente (simulati). Svuota la lista dopo la lettura."""
    global _mock_closed_trades
    result = list(_mock_closed_trades)
    _mock_closed_trades = []
    return result


def connect() -> bool:
    log.info("[MOCK] Connessione MT5 simulata. Saldo: $10,000 demo")
    return True


def disconnect():
    log.info("[MOCK] Disconnessione MT5 simulata.")


def get_candles(count: int = 150, timeframe: str = "H1") -> pd.DataFrame:
    """
    Restituisce candele per il mock.
    Se MOCK_DATA_FILE è configurato e il file esiste → carica dati storici reali.
    Altrimenti → genera dati sintetici random.
    """
    global _last_close   # dichiarazione in cima alla funzione — obbligatorio in Python

    try:
        if MOCK_DATA_FILE and Path(MOCK_DATA_FILE).exists():
            df = _load_csv(MOCK_DATA_FILE, count)
            if df is not None:
                _last_close = float(df["close"].iloc[-1])
                return df
            log.warning("[MOCK CSV] Fallback a dati sintetici")
    except Exception:
        pass

    # ── Generazione sintetica ────────────────────────────────────
    np.random.seed(int(datetime.now(timezone.utc).timestamp()) % 1000)
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

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    times = [now - timedelta(hours=i) for i in range(n, 0, -1)]

    df = pd.DataFrame({
        "open":   opens,
        "high":   highs,
        "low":    lows,
        "close":  prices,
        "volume": np.random.randint(500, 2000, n),
    }, index=pd.DatetimeIndex(times))

    log.info(f"[MOCK] {len(df)} candele generate | Close={prices[-1]:.5f}")
    if timeframe == _TF:    # SL/TP solo sul timeframe di trading
        _check_sl_tp(df)
        _last_close = float(df["close"].iloc[-1])
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
    # Usa il prezzo reale dell'ultimo tick, non un valore fisso
    spread = 0.00013  # ~1.3 pip spread EUR/USD tipico
    price  = (_last_close + spread) if direction == "BUY" else (_last_close - spread)
    price  = round(price + np.random.randn() * 0.00003, 5)  # slippage minimo
    lot   = calculate_lot_size(price, sl)

    trade = {
        "ticket":    _mock_trade_counter,
        "direction": direction,
        "price":     price,
        "lot":       lot,
        "sl":        sl,
        "tp":        tp,
        "time":      datetime.now(timezone.utc).isoformat(),
    }
    _mock_positions.append(trade)
    _mock_trade_counter += 1

    log.info(f"[MOCK] {direction} eseguito — Ticket:{trade['ticket']} "
             f"Price:{price:.5f} Lot:{lot} SL:{sl} TP:{tp}")
    return {"success": True, **trade}


def close_position(ticket: int) -> dict:
    """Chiude una singola posizione mock per ticket (AI exit)."""
    global _mock_positions, _mock_closed_trades, _mock_balance
    for i, pos in enumerate(_mock_positions):
        if pos["ticket"] != ticket:
            continue
        # Usa il prezzo di mercato corrente (non il prezzo di apertura)
        close_price = round(_last_close + np.random.randn() * 0.00005, 5)
        profit = round(
            (close_price - pos["price"] if pos["direction"] == "BUY"
             else pos["price"] - close_price)
            * pos["lot"] * 100_000, 2
        )
        _mock_balance += profit
        _mock_positions.pop(i)
        closed = {
            "ticket":      ticket,
            "close_price": round(close_price, 5),
            "profit":      profit,
            "swap":        0.0,
            "commission":  0.0,
            "volume":      pos["lot"],
            "close_time":  datetime.now(timezone.utc).isoformat(),
            "reason":      "ai_exit",
        }
        _mock_closed_trades.append(closed)
        emoji = "✅" if profit > 0 else "❌"
        log.info(f"[MOCK] {emoji} Trade {ticket} chiuso da AI exit | "
                 f"Profit: ${profit:.2f} | Saldo: ${_mock_balance:.2f}")
        return {"success": True, **closed}
    log.warning(f"[MOCK] Ticket {ticket} non trovato tra le posizioni aperte")
    return {"success": False}


