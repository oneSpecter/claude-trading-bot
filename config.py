# ================================================================
#  FOREX AI BOT — CONFIGURAZIONE CENTRALE
#  Le credenziali vengono caricate da .env (non committare .env su Git)
#  Copia .env.example → .env e compila i valori
# ================================================================

import os
from dotenv import load_dotenv
load_dotenv()  # carica .env se presente

# ── Claude API ──────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "sk-ant-XXXX")

# Modello consigliato: haiku per risparmio, sonnet per analisi più profonde
# "claude-haiku-4-5-20251001"    → ~$4-7/mese
# "claude-sonnet-4-6"            → ~$15-18/mese
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

# ── MetaTrader 5 ────────────────────────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", 0))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")
# Trovi queste info nell'email di registrazione del broker demo

# ── Strategia ───────────────────────────────────────────────────
SYMBOL       = "EURUSD"
TIMEFRAME    = "H1"       # H1, M30, H4

EMA_FAST     = 9
EMA_SLOW     = 21
RSI_PERIOD   = 14
ATR_PERIOD   = 14
ATR_SL_MULT  = 1.5        # Stop Loss = ATR × 1.5
ATR_TP_MULT  = 2.5        # Take Profit = ATR × 2.5

CANDLES_LOAD = 150        # Candele da caricare per i calcoli

# ── Rischio ─────────────────────────────────────────────────────
RISK_PCT         = 0.01   # 1% del capitale per ogni trade
MAX_OPEN_TRADES  = 1      # Max posizioni aperte contemporaneamente
MIN_CONFIDENCE   = 65     # Minima confidenza Claude (0-100) per tradare

# ── Loop ────────────────────────────────────────────────────────
CHECK_INTERVAL = 300      # Secondi tra un controllo e l'altro (5 min)

# ── Autoprompt: soglie pre-filtro tecnico ────────────────────────
# Claude viene chiamato SOLO se questi filtri sono soddisfatti (risparmio costi)
REQUIRE_EMA_CROSS    = True   # Deve esserci un crossover recente (ultime 3 candele)
REQUIRE_RSI_ALIGNED  = True   # RSI deve essere dalla parte giusta del trend
RSI_BULL_THRESHOLD   = 45     # RSI > 45 per considerare long
RSI_BEAR_THRESHOLD   = 55     # RSI < 55 per considerare short
