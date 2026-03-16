"""
STRATEGIA MANUALE — EMA × RSI × ADX (regole pure, nessuna AI)
--------------------------------------------------------------
Strategia rule-based classica: non chiama mai Claude API.
Costo operativo: $0.

Logica di entrata:
  BUY  → EMA fast > EMA slow + RSI in zona bullish + ADX sopra soglia + H4 rialzista
  SELL → EMA fast < EMA slow + RSI in zona bearish + ADX sopra soglia + H4 ribassista
  HOLD → condizioni non soddisfatte

Logica di uscita anticipata:
  RSI in zona di esaurimento estremo (configurabile)
  oppure inversione EMA confermata da MACD

Parametri configurabili:
    rsi_bull_min:    RSI minimo per segnale BUY     (default: 50)
    rsi_bear_max:    RSI massimo per segnale SELL   (default: 50)
    adx_min:         ADX minimo per trend valido    (default: 25)
    confidence:      confidenza fissa del segnale   (default: 70)
    require_h4:      richiede conferma bias H4      (default: True)
    rsi_exit_high:   RSI soglia uscita BUY          (default: 75)
    rsi_exit_low:    RSI soglia uscita SELL         (default: 25)
"""

import logging
from strategies.base import BaseStrategy

log = logging.getLogger("ManualStrategy")


class Strategy(BaseStrategy):

    # ── Default parametri ─────────────────────────────────────────
    _DEF = {
        "rsi_bull_min":  50,
        "rsi_bear_max":  50,
        "adx_min":       25,
        "confidence":    70,
        "require_h4":    True,
        "rsi_exit_high": 75,
        "rsi_exit_low":  25,
    }

    def _p(self, key):
        """Legge un parametro con fallback al default."""
        return self.params.get(key, self._DEF[key])

    def should_trade(self, df, df_h4, indicators: dict, context: dict) -> dict:
        rsi          = float(indicators.get("rsi",      50))
        adx          = float(indicators.get("adx",       0))
        ema_trend    = indicators.get("ema_trend",    "flat")
        macd_bias    = indicators.get("macd_bias",    "neutral")
        h4_bias      = indicators.get("h4_bias",      "neutral")
        atr_sl       = indicators.get("atr_sl")
        atr_tp       = indicators.get("atr_tp")
        atr_sl_short = indicators.get("atr_sl_short")
        atr_tp_short = indicators.get("atr_tp_short")

        adx_min    = self._p("adx_min")
        require_h4 = self._p("require_h4")
        confidence = int(self._p("confidence"))

        hold = {"decision": "HOLD", "confidence": 0, "sl": None, "tp": None}

        # ── Filtro ADX (trend abbastanza forte?) ──────────────────
        if adx < adx_min:
            log.info(f"[Manual] HOLD — ADX={adx:.1f} < {adx_min} (mercato ranging)")
            return {**hold, "reasoning": f"ADX={adx:.1f} sotto soglia {adx_min} — mercato ranging"}

        # ── BUY setup ─────────────────────────────────────────────
        if (
            ema_trend == "RIALZISTA"
            and rsi >= self._p("rsi_bull_min")
            and (not require_h4 or h4_bias in ("BULLISH", "NEUTRAL"))
        ):
            log.info(f"[Manual] BUY — EMA RIALZISTA | RSI={rsi:.1f} | ADX={adx:.1f} | H4={h4_bias}")
            return {
                "decision":   "BUY",
                "confidence": confidence,
                "sl":         atr_sl,
                "tp":         atr_tp,
                "reasoning":  (
                    f"EMA RIALZISTA | RSI={rsi:.1f} >= {self._p('rsi_bull_min')} | "
                    f"ADX={adx:.1f} | H4={h4_bias}"
                ),
                "market_regime": "trending",
                "technical_score": int(min(100, adx + rsi / 2)),
            }

        # ── SELL setup ────────────────────────────────────────────
        if (
            ema_trend == "RIBASSISTA"
            and rsi <= self._p("rsi_bear_max")
            and (not require_h4 or h4_bias in ("BEARISH", "NEUTRAL"))
        ):
            log.info(f"[Manual] SELL — EMA bearish | RSI={rsi:.1f} | ADX={adx:.1f} | H4={h4_bias}")
            return {
                "decision":   "SELL",
                "confidence": confidence,
                "sl":         atr_sl_short,
                "tp":         atr_tp_short,
                "reasoning":  (
                    f"EMA bearish cross | RSI={rsi:.1f} <= {self._p('rsi_bear_max')} | "
                    f"ADX={adx:.1f} | H4={h4_bias}"
                ),
                "market_regime": "trending",
                "technical_score": int(min(100, adx + (100 - rsi) / 2)),
            }

        log.info(f"[Manual] HOLD — nessun setup valido (EMA={ema_trend} RSI={rsi:.1f})")
        return {**hold, "reasoning": f"Nessun setup — EMA={ema_trend} RSI={rsi:.1f} H4={h4_bias}"}

    def should_exit(self, pos: dict, current_price: float, indicators: dict,
                    time_limit_hit: bool = False) -> dict:
        direction = pos.get("direction", "BUY")
        rsi       = float(indicators.get("rsi",       50))
        ema_trend = indicators.get("ema_trend",    "flat")
        macd_bias = indicators.get("macd_bias",    "neutral")

        # ── Uscita basata su RSI estremo ──────────────────────────
        if direction == "BUY" and rsi >= self._p("rsi_exit_high"):
            return {
                "action":    "CLOSE",
                "confidence": 80,
                "reasoning":  f"RSI={rsi:.1f} in zona ipercomprato (>= {self._p('rsi_exit_high')})",
            }
        if direction == "SELL" and rsi <= self._p("rsi_exit_low"):
            return {
                "action":    "CLOSE",
                "confidence": 80,
                "reasoning":  f"RSI={rsi:.1f} in zona ipervenduto (<= {self._p('rsi_exit_low')})",
            }

        # ── Uscita su inversione EMA+MACD confermata ──────────────
        if direction == "BUY" and ema_trend == "RIBASSISTA" and macd_bias == "RIBASSISTA":
            return {
                "action":    "CLOSE",
                "confidence": 75,
                "reasoning":  "Inversione EMA bearish confermata da MACD",
            }
        if direction == "SELL" and ema_trend == "RIALZISTA" and macd_bias == "RIALZISTA":
            return {
                "action":    "CLOSE",
                "confidence": 75,
                "reasoning":  "Inversione EMA bullish confermata da MACD",
            }

        # ── Scadenza durata massima senza segnale chiaro → tieni ──
        if time_limit_hit:
            return {
                "action":    "HOLD",
                "confidence": 60,
                "reasoning":  "Durata max raggiunta ma nessun segnale di inversione — mantieni",
            }

        return {
            "action":    "HOLD",
            "confidence": 50,
            "reasoning":  "Nessun segnale di uscita anticipata",
        }
