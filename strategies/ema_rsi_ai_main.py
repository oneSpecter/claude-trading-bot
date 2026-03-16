"""
STRATEGIA MAIN AI — EMA × RSI × Claude (full 3-stage, massima qualità)
=======================================================================
Progettata per trade di alta qualità su trend forti e ben confermati.

Caratteristiche principali rispetto alla strategia standard:

ENTRATA (più selettiva, alta probabilità):
  ┌───────────────────────────────────────────────────────────────┐
  │ SL:  ATR × 1.5   (stop adeguato ~9-14 pip su EUR/USD)      │
  │ TP:  ATR × 3.5   (target ampio ~21-32 pip, R/R > 2.3)      │
  │ ADX: ≥ 30        (solo trend forti, non medi)               │
  │ H4:  RICHIESTO   (trade solo nella direzione del trend H4)  │
  │ Web search: SEMPRE (min_score=0, analisi macro completa)    │
  │ Confidenza min: 78% (alta selettività — meno trade, meglio) │
  └───────────────────────────────────────────────────────────────┘

POST-PROCESSING:
  - Se convergence != "aligned" → forza HOLD (tech+fondamentale devono concordare)
  - Se R/R < 1.8 → forza HOLD (R/R insufficiente anche se confidenza alta)

USCITA (conservativa, massimizza i profitti):
  - RSI > 78 su BUY  → chiudi (esaurimento estremo)
  - RSI < 22 su SELL → chiudi
  - 80% del TP raggiunto + segnale di inversione → lock-in profitto
  - EMA+MACD inversione confermata → chiudi
  - Time limit: chiede a Claude (non chiude automaticamente come in scalping)

QUANDO USARE:
  - Sessioni principali con trend forti (Londra, NY overlap)
  - EUR/USD, GBP/USD, USD/JPY (coppie liquide)
  - In combinazione con strategia scalp su un altro bot per timeframe diversi
  - MAX 1 trade aperto alla volta

COSTO STIMATO:
  ~$0.015-0.025/analisi (Stage1+Stage2+Stage3 con web search sempre attivo)
"""

import logging
from strategies.base import BaseStrategy
from indicators import apply_prefilter
from claude_analyst import (
    stage1_technical,
    stage2_news,
    stage3_decision,
    check_exit,
)

log = logging.getLogger("MainStrategy")

# ── Moltiplicatori SL/TP main ───────────────────────────────────────────────
SL_MULT = 1.5    # Stop adeguato: ATR × 1.5
TP_MULT = 3.5    # Take profit ampio: ATR × 3.5  → R/R > 2.3

# ── Soglie main ────────────────────────────────────────────────────────
ADX_MIN        = 30     # Solo trend forti
MIN_CONFIDENCE = 78     # Alta selettività
MIN_RR         = 1.8    # R/R minimo per aprire un trade


class Strategy(BaseStrategy):
    """
    Main AI con massima qualità: trend forti, conferma H4, web search sempre attivo,
    post-processing convergence check e R/R guard.

    Parametri (tutti opzionali — i default sono già calibrati per la strategia main):
        min_confidence:   soglia minima (default: 78)
        adx_min:          soglia ADX  (default: 30)
        require_ema:      richiede crossover EMA (default: True)
        require_rsi:      richiede RSI allineato (default: True)
        sl_mult:          moltiplicatore SL sull'ATR (default: 1.5)
        tp_mult:          moltiplicatore TP sull'ATR (default: 3.5)
        min_rr:           R/R minimo per aprire trade (default: 1.8)
        rsi_exit_high:    RSI chiusura BUY  (default: 78)
        rsi_exit_low:     RSI chiusura SELL (default: 22)
        profit_lock_pct:  % TP raggiunto per attivare lock-in (default: 0.80)
    """

    def _p(self, key, default):
        return self.params.get(key, default)

    def should_trade(self, df, df_h4, indicators: dict, context: dict) -> dict:
        settings = context.get("settings", {})

        # ── Pre-filtro MAIN (selettivo) ──────────────────────────────────────────
        adx_min     = self._p("adx_min",     ADX_MIN)
        require_ema = self._p("require_ema", True)
        require_rsi = self._p("require_rsi", True)

        ok, reason = apply_prefilter(
            df, df_h4,
            require_ema_cross=require_ema,
            require_rsi_aligned=require_rsi,
            adx_threshold=adx_min,
            require_adx=True,
            require_h4_confirm=True,   # main: richiede conferma trend H4
        )
        if not ok:
            return {"decision": "HOLD", "confidence": 0, "sl": None, "tp": None,
                    "reasoning": f"Pre-filtro main: {reason}", "_prefilter_skip": True}

        # ── Override SL/TP per strategia main ────────────────────────────────────
        sl_mult = self._p("sl_mult", SL_MULT)
        tp_mult = self._p("tp_mult", TP_MULT)
        tech  = dict(indicators)
        price = tech["price"]
        atr   = tech["atr"]
        tech["atr_sl"]       = round(price - sl_mult * atr, 5)
        tech["atr_tp"]       = round(price + tp_mult * atr, 5)
        tech["atr_sl_short"] = round(price + sl_mult * atr, 5)
        tech["atr_tp_short"] = round(price - tp_mult * atr, 5)
        # ADX trend aggiornato con soglia main
        tech["adx_trend"] = "TRENDING" if tech["adx"] >= adx_min else "RANGING"

        # ── Analisi Claude COMPLETA: Stage1 + Stage2 + Stage3 ─────────────────────
        # web_search_min_score=0 → stage2 eseguito sempre (nessun gate)
        min_conf = self._p("min_confidence", settings.get("min_confidence", MIN_CONFIDENCE))
        log.info("[Main] Avvio analisi completa Stage1 + Stage2 (web search) + Stage3")

        try:
            # Stage 1 — analisi tecnica
            tech_brief, tech_score, tech_bias = stage1_technical(tech)
            tech["technical_score_s1"] = tech_score

            # Stage 2 — notizie & macro (sempre, score non importa in main)
            news_brief, fundamental_score, convergence = stage2_news(tech_brief, tech_bias)

            # Stage 3 — decisione finale + devil's advocate
            decision = stage3_decision(
                tech_brief, news_brief, tech,
                fundamental_score=fundamental_score,
                convergence=convergence,
            )
        except Exception as e:
            log.error(f"[Main] Errore analisi Claude: {e}")
            return {"decision": "HOLD", "confidence": 0, "sl": None, "tp": None,
                    "reasoning": f"Errore Claude: {e}"}

        # Metadata per journal
        decision["tech_brief"]      = tech_brief
        decision["news_brief"]      = news_brief
        decision["tech_score_s1"]   = tech_score
        decision["technical_score"] = tech_score
        decision["tech_bias_s1"]    = tech_bias
        decision["web_search_done"] = True

        # ── Post-processing 1: convergence guard ──────────────────────────────────
        # Se tecnico e fondamentale non sono allineati → HOLD forzato
        conv = decision.get("convergence", convergence)
        if conv != "aligned" and decision.get("decision") != "HOLD":
            log.info(
                f"[Main] Convergenza={conv!r} != 'aligned' → HOLD forzato "
                f"(tech e fondamentale non concordano)"
            )
            decision["decision"]  = "HOLD"
            decision["reasoning"] = (
                f"[Convergenza {conv!r}] Tecnico e fondamentale non concordano — "
                "in strategia main è richiesto allineamento completo. "
                + decision.get("reasoning", "")
            )

        # ── Post-processing 2: R/R guard ────────────────────────────────────────────
        min_rr = self._p("min_rr", MIN_RR)
        rr     = float(decision.get("rr_ratio", 0))
        if rr < min_rr and decision.get("decision") != "HOLD":
            log.info(
                f"[Main] R/R={rr:.2f} < {min_rr} → HOLD forzato "
                f"(R/R insufficiente per strategia main)"
            )
            decision["decision"]  = "HOLD"
            decision["reasoning"] = (
                f"[R/R={rr:.2f} < {min_rr}] Risk/reward insufficiente — "
                "la strategia main richiede R/R ≥ 1.8 per ogni trade. "
                + decision.get("reasoning", "")
            )

        # ── Enforce ADX debole ──────────────────────────────────────────────────────────
        adx = float(tech.get("adx", 25))
        if adx < adx_min and decision.get("decision") != "HOLD":
            orig_conf = decision.get("confidence", 0)
            enforced  = max(0, orig_conf - 15)
            if enforced != orig_conf:
                decision["confidence"] = enforced
                decision["reasoning"]  = f"[ADX debole {adx:.0f} < {adx_min}] " + decision.get("reasoning", "")

        # ── Soglia confidenza main ────────────────────────────────────────────────────
        if decision.get("confidence", 0) < min_conf:
            log.info(f"[Main] Confidenza {decision.get('confidence', 0)}% < {min_conf}% → HOLD")
            decision["decision"]  = "HOLD"
            decision["reasoning"] = (
                f"Confidenza insufficiente ({decision.get('confidence', 0)}% < {min_conf}%). "
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

        rsi_exit_high   = self._p("rsi_exit_high",   78)
        rsi_exit_low    = self._p("rsi_exit_low",    22)
        profit_lock_pct = self._p("profit_lock_pct", 0.80)

        # ── Chiusura su RSI estremo (più conservativa che in scalping) ────────────────
        if direction == "BUY" and rsi >= rsi_exit_high:
            return {
                "action":    "CLOSE",
                "confidence": 85,
                "reasoning":  f"[Main] RSI={rsi:.1f} ≥ {rsi_exit_high} — esaurimento estremo, chiudi BUY",
            }
        if direction == "SELL" and rsi <= rsi_exit_low:
            return {
                "action":    "CLOSE",
                "confidence": 85,
                "reasoning":  f"[Main] RSI={rsi:.1f} ≤ {rsi_exit_low} — esaurimento estremo, chiudi SELL",
            }

        # ── Lock-in profitti: 80% del TP + segnale inversione ──────────────────────
        if tp and entry and abs(tp - entry) > 0:
            pct_tp = abs(current_price - entry) / abs(tp - entry)
            if pct_tp >= profit_lock_pct:
                if direction == "BUY" and (ema_trend == "RIBASSISTA" or macd_bias == "RIBASSISTA"):
                    return {
                        "action":    "CLOSE",
                        "confidence": 82,
                        "reasoning":  f"[Main] {pct_tp:.0%} del TP raggiunto + inversione → lock-in profitto",
                    }
                if direction == "SELL" and (ema_trend == "RIALZISTA" or macd_bias == "RIALZISTA"):
                    return {
                        "action":    "CLOSE",
                        "confidence": 82,
                        "reasoning":  f"[Main] {pct_tp:.0%} del TP raggiunto + inversione → lock-in profitto",
                    }

        # ── Inversione EMA+MACD confermata ──────────────────────────────────────────
        if direction == "BUY" and ema_trend == "RIBASSISTA" and macd_bias == "RIBASSISTA":
            return {
                "action":    "CLOSE",
                "confidence": 80,
                "reasoning":  "[Main] Inversione EMA+MACD ribassista confermata — esci dal BUY",
            }
        if direction == "SELL" and ema_trend == "RIALZISTA" and macd_bias == "RIALZISTA":
            return {
                "action":    "CLOSE",
                "confidence": 80,
                "reasoning":  "[Main] Inversione EMA+MACD rialzista confermata — esci dal SELL",
            }

        # ── Time limit: chiede a Claude (NON chiude automaticamente) ───────────────
        # In main la posizione potrebbe ancora avere molto potenziale —
        # lasciamo decidere a Claude in base al contesto corrente.
        if time_limit_hit:
            log.info("[Main] Time limit raggiunto — delega decisione di uscita a Claude")
            return check_exit(pos, current_price, indicators, time_limit_hit=True)

        return {"action": "HOLD", "confidence": 50, "reasoning": "Nessun segnale di uscita main"}
