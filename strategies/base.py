"""
STRATEGY BASE CLASS
-------------------
Interfaccia comune per tutte le strategie (AI e manuali).
Ogni strategia deve implementare should_trade() e should_exit().
"""

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """
    Classe base per tutte le strategie di trading.

    params: dizionario con i parametri configurabili della strategia
            (es. ema_fast, ema_slow, rsi_min, rsi_max)
    """

    def __init__(self, params: dict):
        self.params = params

    @abstractmethod
    def should_trade(self, df: pd.DataFrame, df_h4, indicators: dict,
                     context: dict) -> dict:
        """
        Analizza le condizioni di mercato e restituisce una decisione di trade.

        Args:
            df:         DataFrame OHLC con indicatori calcolati (compute_all + dropna)
            df_h4:      DataFrame H4 (può essere None se non disponibile)
            indicators: tech summary da build_technical_summary()
            context:    dict con impostazioni runtime (settings, dry_run, symbol, ecc.)

        Returns:
            {
              "decision":    "BUY" | "SELL" | "HOLD",
              "confidence":  int (0-100),
              "sl":          float | None,
              "tp":          float | None,
              "reason":      str,
              ...campi extra per il journal (opzionali)
            }
        """

    @abstractmethod
    def should_exit(self, pos: dict, current_price: float, indicators: dict,
                    time_limit_hit: bool = False) -> dict:
        """
        Decide se una posizione aperta deve essere chiusa anticipatamente.

        Args:
            pos:            posizione normalizzata (dict con ticket, direction, price, sl, tp, ...)
            current_price:  prezzo corrente di mercato
            indicators:     tech summary corrente
            time_limit_hit: True se il trade ha superato MAX_TRADE_DURATION_H

        Returns:
            {
              "action":    "CLOSE" | "HOLD",
              "confidence": int (0-100),
              "reasoning":  str
            }
        """
