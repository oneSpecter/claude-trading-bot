"""
STRATEGIA AI — EMA × RSI × Claude (3 stadi)
--------------------------------------------
Pre-filtro tecnico locale + analisi Claude AI a 3 stadi (tecnico → macro → decisione).
Identica alla logica originale del bot, estratta come plugin riusabile.

Parametri configurabili (sovrascrivono i default di config.py):
    min_confidence:       soglia minima confidenza Claude (default: MIN_CONFIDENCE)
    web_search_min_score: soglia tecnica per attivare web search (default: WEB_SEARCH_MIN_SCORE)
    require_ema_cross:    richiede crossover EMA recente (default: REQUIRE_EMA_CROSS)
    require_rsi_aligned:  richiede RSI dalla parte giusta (default: REQUIRE_RSI_ALIGNED)
    adx_threshold:        soglia ADX per trend valido (default: ADX_THRESHOLD)
    require_adx:          abilita filtro ADX (default: REQUIRE_ADX)
    require_h4_confirm:   richiede conferma trend H4 (default: REQUIRE_H4_CONFIRM)
"""

from strategies.base import BaseStrategy
from indicators import apply_prefilter
from claude_analyst import analyze, check_exit


class Strategy(BaseStrategy):

    def should_trade(self, df, df_h4, indicators: dict, context: dict) -> dict:
        """
        Esegue pre-filtro tecnico poi chiama Claude AI (3 stadi).
        Se il pre-filtro fallisce restituisce HOLD senza consumare API.
        """
        settings = context.get("settings", {})
        p = self.params

        # ── Pre-filtro tecnico (gratuito, nessuna API call) ────────────
        ok, reason = apply_prefilter(
            df, df_h4,
            require_ema_cross=p.get("require_ema_cross",   settings.get("require_ema_cross")),
            require_rsi_aligned=p.get("require_rsi_aligned", settings.get("require_rsi_aligned")),
            adx_threshold=p.get("adx_threshold",       settings.get("adx_threshold")),
            require_adx=p.get("require_adx",          settings.get("require_adx")),
            require_h4_confirm=p.get("require_h4_confirm",   settings.get("require_h4_confirm")),
        )

        if not ok:
            return {
                "decision":   "HOLD",
                "confidence": 0,
                "sl":         None,
                "tp":         None,
                "reasoning":  f"Pre-filtro: {reason}",
                "_prefilter_skip": True,
            }

        # ── Claude AI — 3 stadi ────────────────────────────────────────
        decision = analyze(
            indicators,
            min_confidence=p.get("min_confidence",       settings.get("min_confidence")),
            web_search_min_score=p.get("web_search_min_score", settings.get("web_search_min_score")),
        )
        return decision

    def should_exit(self, pos: dict, current_price: float, indicators: dict,
                    time_limit_hit: bool = False) -> dict:
        """Delega a Claude check_exit (single-stage economico)."""
        return check_exit(pos, current_price, indicators, time_limit_hit=time_limit_hit)
