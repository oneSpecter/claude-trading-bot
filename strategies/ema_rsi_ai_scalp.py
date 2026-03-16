"""
STRATEGIA SCALPING AI — EMA × RSI × Claude (fast)
===================================================
Progettata per trade veloci e frequenti su movimenti intra-H1.

Differenze chiave rispetto alla strategia main:

ENTRATA (più permissiva):
  ┌─────────────────────────────────────────────────────────────┐
  │ SL:  ATR × 0.8   (stop stretto  ~5-8 pip su EUR/USD)      │
  │ TP:  ATR × 1.8   (target vicino ~11-16 pip, R/R ≈ 2.25)   │
  │ ADX: ≥ 20        (accetta trend medi, non solo forti)       │
  │ H4:  NON richiesto (può tradare anche contro trend H4)       │
  │ Web search: DISABILITATO (solo Stage1+Stage3, ~70% più      │
  │             economico e più veloce)                          │
  │ Confidenza min: 58% (trade più frequenti)                   │
  └─────────────────────────────────────────────────────────────┘

USCITA (rapida, protegge i profitti):
  - RSI > 72 su BUY  → chiudi (momentum esaurito)
  - RSI < 28 su SELL → chiudi
  - Inversione EMA confermata → chiudi subito
  - Se > 60% del TP raggiunto + segnale contrario → chiudi (lock-in)

QUANDO USARE:
  - Sessioni ad alta volatilità (Londra 08:00-12:00, NY 14:00-18:00 UTC)
  - EUR/USD, GBP/USD (spread bassi essenziali per scalping)
  - In combinazione con la strategia main su un altro bot
  - MAX 1 trade aperto alla volta

COSTO STIMATO:
  ~$0.001-0.003/analisi (solo Stage1+Stage3, no web search)
"""

import logging
from strategies.base import BaseStrategy
from indicators import apply_prefilter
from claude_analyst import stage1_technical, stage3_decision, check_exit

log = logging.getLogger("ScalpStrategy")

# ── Moltiplicatori SL/TP scalping ─────────────────────────────────
SL_MULT = 0.8    # Stop stretto: ATR × 0.8
TP_MULT = 1.8    # Take profit vicino: ATR × 1.8  → R/R = 2.25


def _override_sltp(tech: dict) -> dict:
    """
    Ricalcola SL/TP con i moltiplicatori scalping.
    Claude vedrà targets più vicini → decisioni più aggressive.
    """
    t     = dict(tech)
    price = t["price"]
    atr   = t["atr"]
    t["atr_sl"]       = round(price - SL_MULT * atr, 5)
    t["atr_tp"]       = round(price + TP_MULT * atr, 5)
    t["atr_sl_short"] = round(price + SL_MULT * atr, 5)
    t["atr_tp_short"] = round(price - TP_MULT * atr, 5)
    return t


class Strategy(BaseStrategy):
    """
    Scalping AI con setup più frequenti, stop stretti e uscite rapide.

    Parametri (tutti opzionali — i default sono già calibrati per scalping):
        min_confidence:  soglia minima (default: 58)
        adx_min:         soglia ADX  (default: 20)
        require_ema:     richiede crossover EMA (default: True)
        require_rsi:     richiede RSI allineato (default: True)
        sl_mult:         moltiplicatore SL sull'ATR (default: 0.8)
        tp_mult:         moltiplicatore TP sull'ATR (default: 1.8)
        rsi_exit_high:   RSI chiusura BUY  (default: 72)
        rsi_exit_low:    RSI chiusura SELL (default: 28)
        profit_lock_pct: % TP raggiunto per attivare lock-in (default: 0.60)
    """

    def _p(self, key, default):
        return self.params.get(key, default)

    def should_trade(self, df, df_h4, indicators: dict, context: dict) -> dict:
        p        = self.params
        settings = context.get("settings", {})

        # ── Pre-filtro SCALPING (meno restrittivo) ─────────────────
        adx_min     = self._p("adx_min",     20)
        require_ema = self._p("require_ema", True)
        require_rsi = self._p("require_rsi", True)

        ok, reason = apply_prefilter(
            df, df_h4,
            require_ema_cross=require_ema,
            require_rsi_aligned=require_rsi,
            adx_threshold=adx_min,
            require_adx=True,
            require_h4_confirm=False,    # scalping: ignora trend H4
        )
        if not ok:
            return {"decision": "HOLD", "confidence": 0, "sl": None, "tp": None,
                    "reasoning": f"Pre-filtro scalp: {reason}", "_prefilter_skip": True}

        # ── Override SL/TP per scalping ────────────────────────────
        sl_mult = self._p("sl_mult", SL_MULT)
        tp_mult = self._p("tp_mult", TP_MULT)
        tech = dict(indicators)
        price = tech["price"]
        atr   = tech["atr"]
        tech["atr_sl"]       = round(price - sl_mult * atr, 5)
        tech["atr_tp"]       = round(price + tp_mult * atr, 5)
        tech["atr_sl_short"] = round(price + sl_mult * atr, 5)
        tech["atr_tp_short"] = round(price - tp_mult * atr, 5)
        # ADX trend aggiornato con soglia scalping
        tech["adx_trend"] = "TRENDING" if tech["adx"] >= adx_min else "RANGING"

        # ── Analisi Claude: SOLO Stage1 + Stage3 (no web search) ──
        # web_search_min_score=999 → stage2 sempre skippato (risparmio ~$0.01)
        min_conf = self._p("min_confidence", settings.get("min_confidence", 58))
        log.info("[Scalp] Avvio analisi Stage1 + Stage3 (web search disabilitato)")

        try:
            tech_brief, tech_score, tech_bias = stage1_technical(tech)
            tech["technical_score_s1"] = tech_score

            # Stage2 skippato: nota esplicita per Stage3
            news_brief = (
                "Analisi macro non eseguita — strategia scalping: "
                "decisione basata SOLO su analisi tecnica H1. "
                "Priorità: momentum intraday, pattern di prezzo, livelli S/R a breve termine."
            )
            fundamental_score = 50
            convergence       = "neutral"

            decision = stage3_decision(
                tech_brief, news_brief, tech,
                fundamental_score=fundamental_score,
                convergence=convergence,
            )
        except Exception as e:
            log.error(f"[Scalp] Errore analisi Claude: {e}")
            return {"decision": "HOLD", "confidence": 0, "sl": None, "tp": None,
                    "reasoning": f"Errore Claude: {e}"}

        # Metadata per journal
        decision["tech_brief"]      = tech_brief
        decision["news_brief"]      = news_brief
        decision["tech_score_s1"]   = tech_score
        decision["technical_score"] = tech_score
        decision["tech_bias_s1"]    = tech_bias
        decision["web_search_done"] = False

        # ── Enforce R3 (ADX < 20) ─────────────────────────────────
        adx = float(tech.get("adx", 25))
        if adx < 20 and decision.get("decision") != "HOLD":
            orig_conf = decision.get("confidence", 0)
            enforced  = max(0, orig_conf - 15)
            if enforced != orig_conf:
                decision["confidence"] = enforced
                decision["reasoning"]  = f"[ADX debole {adx:.0f}] " + decision.get("reasoning", "")

        # ── Soglia confidenza scalping ────────────────────────────
        if decision.get("confidence", 0) < min_conf:
            log.info(f"[Scalp] Confidenza {decision['confidence']}% < {min_conf}% → HOLD")
            decision["decision"]  = "HOLD"
            decision["reasoning"] = (
                f"Confidenza insufficiente ({decision['confidence']}% < {min_conf}%). "
                + decision.get("reasoning", "")
            )

        return decision

    def should_exit(self, pos: dict, current_price: float, indicators: dict,
                    time_limit_hit: bool = False) -> dict:
        direction = pos.get("direction", "BUY")
        rsi       = float(indicators.get("rsi",       50))
        ema_trend = indicators.get("ema_trend",    "flat")
        macd_bias = indicators.get("macd_bias",    "neutral")
        entry     = float(pos.get("price",  0))
        tp        = float(pos.get("tp",     0))
        sl        = float(pos.get("sl",     0))

        rsi_exit_high  = self._p("rsi_exit_high",  72)
        rsi_exit_low   = self._p("rsi_exit_low",   28)
        profit_lock_pct = self._p("profit_lock_pct", 0.60)

        # ── Chiusura rapida su RSI estremo (scalping) ──────────────
        if direction == "BUY" and rsi >= rsi_exit_high:
            return {
                "action":    "CLOSE",
                "confidence": 85,
                "reasoning":  f"[Scalp] RSI={rsi:.1f} ≥ {rsi_exit_high} — momentum esaurito, chiudi subito",
            }
        if direction == "SELL" and rsi <= rsi_exit_low:
            return {
                "action":    "CLOSE",
                "confidence": 85,
                "reasoning":  f"[Scalp] RSI={rsi:.1f} ≤ {rsi_exit_low} — momentum esaurito, chiudi subito",
            }

        # ── Lock-in profitti: se > X% del TP raggiunto + inversione ──
        if tp and entry and abs(tp - entry) > 0:
            pct_tp = abs(current_price - entry) / abs(tp - entry)
            if pct_tp >= profit_lock_pct:
                if direction == "BUY" and (ema_trend == "RIBASSISTA" or macd_bias == "RIBASSISTA"):
                    return {
                        "action":    "CLOSE",
                        "confidence": 80,
                        "reasoning":  f"[Scalp] {pct_tp:.0%} del TP raggiunto + segnale inversione → lock-in profitto",
                    }
                if direction == "SELL" and (ema_trend == "RIALZISTA" or macd_bias == "RIALZISTA"):
                    return {
                        "action":    "CLOSE",
                        "confidence": 80,
                        "reasoning":  f"[Scalp] {pct_tp:.0%} del TP raggiunto + segnale inversione → lock-in profitto",
                    }

        # ── Inversione EMA+MACD confermata → chiudi subito ─────────
        if direction == "BUY" and ema_trend == "RIBASSISTA" and macd_bias == "RIBASSISTA":
            return {
                "action":    "CLOSE",
                "confidence": 78,
                "reasoning":  "[Scalp] Inversione EMA+MACD ribassista confermata — esci dal BUY",
            }
        if direction == "SELL" and ema_trend == "RIALZISTA" and macd_bias == "RIALZISTA":
            return {
                "action":    "CLOSE",
                "confidence": 78,
                "reasoning":  "[Scalp] Inversione EMA+MACD rialzista confermata — esci dal SELL",
            }

        # ── Time limit: in scalping → chiudi comunque ─────────────
        if time_limit_hit:
            return {
                "action":    "CLOSE",
                "confidence": 70,
                "reasoning":  "[Scalp] Durata massima raggiunta — in scalping è sempre meglio chiudere e rientrare",
            }

        return {"action": "HOLD", "confidence": 50, "reasoning": "Nessun segnale di uscita scalping"}
