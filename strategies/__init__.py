"""
STRATEGY PLUGIN LOADER
-----------------------
Carica strategie dinamicamente dal folder strategies/.
Ogni file deve contenere una classe 'Strategy' che estende BaseStrategy.

Uso:
    from strategies import load_strategy
    strategy = load_strategy("ema_rsi_ai", {"min_confidence": 70})
    strategy = load_strategy("ema_rsi_manual", {"ema_fast": 9, "ema_slow": 21})

Per strategie custom: crea strategies/my_strategy.py con classe Strategy(BaseStrategy)
e usa load_strategy("my_strategy", {...}).
"""

import importlib
from strategies.base import BaseStrategy


def load_strategy(name: str, params: dict) -> BaseStrategy:
    """
    Carica e istanzia una strategia per nome.

    Args:
        name:   nome del modulo (es. "ema_rsi_ai", "ema_rsi_manual")
        params: parametri configurabili passati al costruttore

    Returns:
        istanza di BaseStrategy

    Raises:
        ModuleNotFoundError: se il file strategies/{name}.py non esiste
        AttributeError:      se la classe Strategy non è definita nel modulo
    """
    mod = importlib.import_module(f"strategies.{name}")
    cls = getattr(mod, "Strategy")
    if not issubclass(cls, BaseStrategy):
        raise TypeError(f"strategies.{name}.Strategy deve estendere BaseStrategy")
    return cls(params)
