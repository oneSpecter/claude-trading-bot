"""
INDICATORI TECNICI
------------------
Calcola tutto ciò che serve: EMA, RSI, ATR, supporti/resistenze,
candlestick pattern, momentum, e un pre-filtro che decide
se vale la pena chiamare Claude API.
"""

import pandas as pd
import numpy as np
from config import (
    EMA_FAST, EMA_SLOW, RSI_PERIOD, ATR_PERIOD,
    REQUIRE_EMA_CROSS, REQUIRE_RSI_ALIGNED,
    RSI_BULL_THRESHOLD, RSI_BEAR_THRESHOLD,
    ADX_PERIOD, ADX_THRESHOLD, REQUIRE_ADX,
    REQUIRE_H4_CONFIRM,
)


def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """Aggiunge tutti gli indicatori al DataFrame OHLC."""
    df = df.copy()

    # ── EMA ──────────────────────────────────────────────────────
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    df["ema_diff"] = df["ema_fast"] - df["ema_slow"]

    # ── RSI ──────────────────────────────────────────────────────
    delta    = df["close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()
    avg_loss = loss.ewm(com=RSI_PERIOD - 1, min_periods=RSI_PERIOD).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ── ATR ──────────────────────────────────────────────────────
    hl  = df["high"] - df["low"]
    hc  = (df["high"] - df["close"].shift()).abs()
    lc  = (df["low"]  - df["close"].shift()).abs()
    tr  = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr"] = tr.ewm(span=ATR_PERIOD, adjust=False).mean()

    # ── Crossover ────────────────────────────────────────────────
    prev_diff = df["ema_diff"].shift(1)
    curr_diff = df["ema_diff"]
    df["cross"] = 0
    df.loc[(prev_diff <= 0) & (curr_diff > 0), "cross"] = 1    # golden
    df.loc[(prev_diff >= 0) & (curr_diff < 0), "cross"] = -1   # death

    # ── MACD (extra contesto per Claude) ─────────────────────────
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"]        = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"]   = df["macd"] - df["macd_signal"]

    # ── Bollinger Bands ──────────────────────────────────────────
    sma20 = df["close"].rolling(20).mean()
    std20 = df["close"].rolling(20).std()
    df["bb_upper"] = sma20 + 2 * std20
    df["bb_lower"] = sma20 - 2 * std20
    df["bb_width"]  = (df["bb_upper"] - df["bb_lower"]) / sma20

    # ── Momentum & volume proxy ──────────────────────────────────
    df["momentum"]  = df["close"] - df["close"].shift(10)
    df["candle_body"] = (df["close"] - df["open"]).abs()
    df["candle_dir"]  = np.sign(df["close"] - df["open"])

    # ── ADX (Average Directional Index) ──────────────────────────
    # Misura la forza del trend (non la direzione).
    # ADX >= 25 → mercato trending  |  ADX < 25 → ranging / laterale
    up   = df["high"].diff()
    down = -df["low"].diff()
    plus_dm  = np.where((up > down) & (up > 0),   up,   0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)

    atr_s    = df["atr"]  # già calcolato sopra
    plus_di  = 100 * (pd.Series(plus_dm,  index=df.index)
                        .ewm(com=ADX_PERIOD - 1, min_periods=ADX_PERIOD).mean()
                      / atr_s.replace(0, np.nan))
    minus_di = 100 * (pd.Series(minus_dm, index=df.index)
                        .ewm(com=ADX_PERIOD - 1, min_periods=ADX_PERIOD).mean()
                      / atr_s.replace(0, np.nan))

    dx = (100 * (plus_di - minus_di).abs()
               / (plus_di + minus_di).replace(0, np.nan))
    df["adx"]       = dx.ewm(com=ADX_PERIOD - 1, min_periods=ADX_PERIOD).mean()
    df["adx_plus"]  = plus_di
    df["adx_minus"] = minus_di

    return df


def get_h4_bias(df_h4: pd.DataFrame) -> str:
    """
    Calcola il bias direzionale su H4 tramite EMA 9/21.
    Ritorna 'BULLISH', 'BEARISH' o 'NEUTRAL'.
    Usato come filtro: non tradare segnali H1 contro il trend H4.
    Threshold dinamico basato sulla volatilità recente (avg high-low H4).
    """
    df = df_h4.copy()
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    df = df.dropna()
    if len(df) == 0:
        return "NEUTRAL"
    last = df.iloc[-1]
    diff = last["ema_fast"] - last["ema_slow"]
    # Threshold = 20% della volatilità media H4 (adattivo a qualsiasi strumento)
    avg_range = (df["high"].tail(20) - df["low"].tail(20)).mean()
    threshold = avg_range * 0.20 if avg_range > 0 else 0.0005
    if diff > threshold:
        return "BULLISH"
    elif diff < -threshold:
        return "BEARISH"
    return "NEUTRAL"


def get_support_resistance(df: pd.DataFrame, lookback: int = 50) -> dict:
    """
    Identifica i livelli di supporto/resistenza chiave
    guardando i pivot point degli ultimi N periodi.
    """
    recent = df.tail(lookback)
    highs  = recent["high"].nlargest(5).round(5).tolist()
    lows   = recent["low"].nsmallest(5).round(5).tolist()
    pivot  = (recent["high"].iloc[-1] + recent["low"].iloc[-1] + recent["close"].iloc[-1]) / 3
    r1 = 2 * pivot - recent["low"].iloc[-1]
    s1 = 2 * pivot - recent["high"].iloc[-1]
    r2 = pivot + (recent["high"].iloc[-1] - recent["low"].iloc[-1])
    s2 = pivot - (recent["high"].iloc[-1] - recent["low"].iloc[-1])
    return {
        "pivot": round(pivot, 5),
        "r1": round(r1, 5), "r2": round(r2, 5),
        "s1": round(s1, 5), "s2": round(s2, 5),
        "recent_highs": highs[:3],
        "recent_lows": lows[:3],
    }


def get_candlestick_patterns(df: pd.DataFrame) -> list[str]:
    """Rileva pattern candlestick sull'ultima candela."""
    if len(df) < 3:
        return ["Nessun pattern rilevante"]
    patterns = []
    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    prev2 = df.iloc[-3]

    body      = abs(last["close"] - last["open"])
    wick_up   = last["high"] - max(last["close"], last["open"])
    wick_down = min(last["close"], last["open"]) - last["low"]
    total     = last["high"] - last["low"]
    if total == 0:
        return patterns

    # Doji
    if body / total < 0.1:
        patterns.append("Doji (indecisione)")

    # Hammer / Hanging man
    if wick_down > 2 * body and wick_up < body * 0.5:
        if last["close"] > prev["close"]:
            patterns.append("Hammer (segnale rialzista)")
        else:
            patterns.append("Hanging Man (segnale ribassista)")

    # Shooting star
    if wick_up > 2 * body and wick_down < body * 0.5:
        patterns.append("Shooting Star (segnale ribassista)")

    # Engulfing
    if (last["close"] > last["open"] and
        prev["close"] < prev["open"] and
        last["open"] < prev["close"] and
        last["close"] > prev["open"]):
        patterns.append("Bullish Engulfing (forte segnale rialzista)")

    if (last["close"] < last["open"] and
        prev["close"] > prev["open"] and
        last["open"] > prev["close"] and
        last["close"] < prev["open"]):
        patterns.append("Bearish Engulfing (forte segnale ribassista)")

    # Three consecutive candles
    if (last["close"] > last["open"] and
        prev["close"] > prev["open"] and
        prev2["close"] > prev2["open"]):
        patterns.append("Tre candele rialziste consecutive")

    if (last["close"] < last["open"] and
        prev["close"] < prev["open"] and
        prev2["close"] < prev2["open"]):
        patterns.append("Tre candele ribassiste consecutive")

    return patterns if patterns else ["Nessun pattern rilevante"]


def apply_prefilter(
    df_c: pd.DataFrame,
    df_h4: pd.DataFrame = None,
    *,
    require_ema_cross: bool = None,
    require_rsi_aligned: bool = None,
    adx_threshold: float = None,
    require_adx: bool = None,
    require_h4_confirm: bool = None,
) -> tuple[bool, str]:
    """
    Pre-filtro tecnico su df già elaborato da compute_all().
    Evita di ricalcolare gli indicatori se sono già disponibili.
    I parametri keyword-only permettono di sovrascrivere i default da config.py
    a runtime (usati dalla pagina Impostazioni della dashboard).
    Ritorna (bool, motivo).
    """
    _req_ema = REQUIRE_EMA_CROSS   if require_ema_cross   is None else require_ema_cross
    _req_rsi = REQUIRE_RSI_ALIGNED if require_rsi_aligned is None else require_rsi_aligned
    _adx_thr = ADX_THRESHOLD       if adx_threshold       is None else adx_threshold
    _req_adx = REQUIRE_ADX         if require_adx         is None else require_adx
    _req_h4  = REQUIRE_H4_CONFIRM  if require_h4_confirm  is None else require_h4_confirm

    if len(df_c) < 3:
        return False, "Dati insufficienti"

    last = df_c.iloc[-1]
    rsi  = last["rsi"]

    recent_crosses = df_c["cross"].tail(3)
    has_cross      = (recent_crosses != 0).any()
    cross_dir      = recent_crosses[recent_crosses != 0].iloc[-1] if has_cross else 0

    if _req_ema and not has_cross:
        return False, f"Nessun crossover EMA recente (EMA_diff={last['ema_diff']:.5f})"

    if _req_rsi:
        if cross_dir == 1 and rsi < RSI_BULL_THRESHOLD:
            return False, f"Cross rialzista ma RSI troppo basso ({rsi:.1f} < {RSI_BULL_THRESHOLD})"
        if cross_dir == -1 and rsi > RSI_BEAR_THRESHOLD:
            return False, f"Cross ribassista ma RSI troppo alto ({rsi:.1f} > {RSI_BEAR_THRESHOLD})"

    adx = last.get("adx", 0)
    if _req_adx and adx < _adx_thr:
        return False, f"Mercato ranging — ADX={adx:.1f} < {_adx_thr} (nessun trend)"

    if _req_h4:
        if df_h4 is None:
            return False, "H4 non disponibile — conferma multi-timeframe richiesta dalla strategia"
        h4_bias = get_h4_bias(df_h4)
        if cross_dir == 1 and h4_bias == "BEARISH":
            return False, f"Cross H1 rialzista ma H4 ribassista — contro-trend, skip"
        if cross_dir == -1 and h4_bias == "BULLISH":
            return False, f"Cross H1 ribassista ma H4 rialzista — contro-trend, skip"

    if cross_dir == 1:
        direction = "LONG"
    elif cross_dir == -1:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"
    return True, f"Setup {direction} rilevato — RSI={rsi:.1f}, ADX={adx:.1f}, ATR={last['atr']:.5f}"


def build_technical_summary(df: pd.DataFrame, df_h4: pd.DataFrame = None) -> dict:
    """
    Costruisce un dizionario con TUTTO il contesto tecnico
    da passare a Claude come prompt.
    Nota: riceve un df già elaborato da compute_all().
    """
    df = df.dropna()

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    sr    = get_support_resistance(df)
    patt  = get_candlestick_patterns(df)

    # Ultime 10 candele come mini-tabella
    last10 = df.tail(10)[["open", "high", "low", "close", "rsi", "adx", "atr"]].round(5)
    candles_str = last10.to_string()

    # Trend a breve e medio termine
    short_trend = "RIALZISTA" if last["ema_fast"] > last["ema_slow"] else "RIBASSISTA"
    macd_bias   = "RIALZISTA" if last["macd_hist"] > 0 else "RIBASSISTA"
    bb_range    = last["bb_upper"] - last["bb_lower"]
    bb_pos      = (last["close"] - last["bb_lower"]) / bb_range if bb_range > 0 else 0.5
    bb_desc     = "vicino alla banda superiore" if bb_pos > 0.8 else \
                  "vicino alla banda inferiore" if bb_pos < 0.2 else "al centro delle bande"

    recent_cross = df["cross"].tail(3)
    cross_signal = None
    for idx, val in recent_cross.items():
        if val == 1:  cross_signal = ("GOLDEN CROSS (rialzista)", idx)
        if val == -1: cross_signal = ("DEATH CROSS (ribassista)", idx)

    return {
        "price":          round(float(last["close"]), 5),
        "ema_fast":       round(float(last["ema_fast"]), 5),
        "ema_slow":       round(float(last["ema_slow"]), 5),
        "ema_trend":      short_trend,
        "rsi":            round(float(last["rsi"]), 1),
        "atr":            round(float(last["atr"]), 5),
        "macd":           round(float(last["macd"]), 5),
        "macd_signal":    round(float(last["macd_signal"]), 5),
        "macd_hist":      round(float(last["macd_hist"]), 5),
        "macd_bias":      macd_bias,
        "bb_upper":       round(float(last["bb_upper"]), 5),
        "bb_lower":       round(float(last["bb_lower"]), 5),
        "bb_position":    bb_desc,
        "momentum_10":    round(float(last["momentum"]), 5),
        "support_resistance": sr,
        "candlestick_patterns": patt,
        "cross_signal":   cross_signal,
        "last_10_candles": candles_str,
        "adx":            round(float(last["adx"]),       1),
        "adx_plus":       round(float(last["adx_plus"]),  1),
        "adx_minus":      round(float(last["adx_minus"]), 1),
        "adx_trend":      "TRENDING" if last["adx"] >= ADX_THRESHOLD else "RANGING",
        "h4_bias": get_h4_bias(df_h4) if df_h4 is not None else "N/A",
        "atr_sl":  round(float(last["close"] - last["atr"] * 1.5), 5),
        "atr_tp":  round(float(last["close"] + last["atr"] * 2.5), 5),
        "atr_sl_short": round(float(last["close"] + last["atr"] * 1.5), 5),
        "atr_tp_short": round(float(last["close"] - last["atr"] * 2.5), 5),
    }
