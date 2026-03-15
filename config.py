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
MT5_PATH     = os.getenv("MT5_PATH", "")   # percorso a terminal64.exe (opzionale)

# USE_MOCK=true  → broker simulato sempre (nessuna connessione MT5)
# USE_MOCK=false → MT5 reale se disponibile, mock come fallback
# Nota: --dry forza automaticamente il mock senza bisogno di questa flag
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"

# Percorso a un CSV con dati storici reali da usare nel mock.
# Se vuoto → genera dati random sintetici (default).
# Formato supportato: export MT5 (Date,Time,Open,High,Low,Close,Volume)
#   o colonne rinominate (datetime,open,high,low,close,volume)
MOCK_DATA_FILE = os.getenv("MOCK_DATA_FILE", "")
# Trovi queste info nell'email di registrazione del broker demo

# ── Strategia ───────────────────────────────────────────────────
SYMBOL    = os.getenv("SYMBOL",    "EURUSD")
TIMEFRAME = os.getenv("TIMEFRAME", "H1")     # H1, M30, H4

EMA_FAST     = 9
EMA_SLOW     = 21
RSI_PERIOD   = 14
ATR_PERIOD   = 14
ATR_SL_MULT  = 1.5        # Stop Loss = ATR × 1.5
ATR_TP_MULT  = 3.0        # Take Profit = ATR × 3.0  → R/R = 2.0 (era 2.5 → R/R 1.67)

CANDLES_LOAD    = 200     # Candele H1 (era 150 — più dati = indicatori più stabili)
H4_CANDLES_LOAD = 150     # Candele H4 per il filtro trend principale (era 100)

# ── Rischio ─────────────────────────────────────────────────────
RISK_PCT         = 0.01   # 1% del capitale per ogni trade
MAX_OPEN_TRADES  = 1      # Max posizioni aperte contemporaneamente
MIN_CONFIDENCE   = 70     # Minima confidenza Claude (era 65 — soglia più alta = meno trade, qualità migliore)

# ── Loop ────────────────────────────────────────────────────────
CHECK_INTERVAL = 1800     # Secondi tra un controllo e l'altro (30 min)
                          # Era 100s: con H1 candles e cross attivo 3h → Claude chiamato 108x per segnale!
                          # 1800s (30 min) è il bilanciamento ottimale per H1: reattivo ma non dispendioso.

# ── Autoprompt: soglie pre-filtro tecnico ────────────────────────
# Claude viene chiamato SOLO se questi filtri sono soddisfatti (risparmio costi)
REQUIRE_EMA_CROSS    = True   # Deve esserci un crossover recente (ultime 3 candele)
REQUIRE_RSI_ALIGNED  = True   # RSI deve essere dalla parte giusta del trend
RSI_BULL_THRESHOLD   = 50     # RSI > 50 per considerare long (era 45 — più simmetrico e selettivo)
RSI_BEAR_THRESHOLD   = 50     # RSI < 50 per considerare short (era 55)

# ── ADX ─────────────────────────────────────────────────────────
# Filtra falsi crossover EMA in mercati ranging
ADX_PERIOD     = 14
ADX_THRESHOLD  = 28           # < 28 = ranging (skip) — era 25, alzato per filtrare trend deboli
REQUIRE_ADX    = True         # False = disabilita il filtro ADX

# ── Filtro H4 multi-timeframe ─────────────────────────────────────
# Non tradare segnali H1 contro il trend principale su H4.
# Riduce i falsi segnali del ~30-40% su EUR/USD.
REQUIRE_H4_CONFIRM = os.getenv("REQUIRE_H4_CONFIRM", "true").lower() == "true"

# ── Web search gate ──────────────────────────────────────────────
# Stage 2 (notizie + macro) viene chiamato SOLO se il setup tecnico è solido
# Risparmia la chiamata API più costosa per setup marginali
WEB_SEARCH_MIN_SCORE = 60     # technical_score minimo (0-100) per triggerare stage2
                               # Era 65 → abbassato a 60: attiva la ricerca notizie su più setup
                               # Migliora la qualità delle decisioni AI con contesto fondamentale

# ── Multi-symbol ─────────────────────────────────────────────────
# Cambia SYMBOL + queste variabili per tradare altri asset senza toccare il codice
SYMBOL_BASE          = os.getenv("SYMBOL_BASE",         "EUR")
SYMBOL_QUOTE         = os.getenv("SYMBOL_QUOTE",        "USD")
CENTRAL_BANK_BASE    = os.getenv("CENTRAL_BANK_BASE",   "BCE (Banca Centrale Europea)")
CENTRAL_BANK_QUOTE   = os.getenv("CENTRAL_BANK_QUOTE",  "Federal Reserve (Fed)")
# Esempi:
#   GBPUSD → BASE=GBP, QUOTE=USD, CB_BASE="Bank of England", CB_QUOTE="Federal Reserve"
#   USDJPY → BASE=USD, QUOTE=JPY, CB_BASE="Federal Reserve", CB_QUOTE="Bank of Japan"
#   XAUUSD → BASE=Gold, QUOTE=USD, CB_BASE="", CB_QUOTE="Federal Reserve"

# ── Protezione perdita giornaliera ───────────────────────────────
# Se il P&L di oggi supera questa % del capitale → stop nuovi trade per oggi.
# 0 = disabilitato
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", 2.0))

# ── Durata massima trade ─────────────────────────────────────────
# Dopo N ore chiude il trade SOLO se in profitto o perdita contenuta (vedi TIME_EXIT_MAX_LOSS_PIPS).
# Se la perdita supera la soglia, lascia lavorare lo SL naturalmente.
# 0 = disabilitato
MAX_TRADE_DURATION_H = int(os.getenv("MAX_TRADE_DURATION_H", 48))
# Era 24h — i trade H1 su EUR/USD necessitano spesso 24-72h per maturare. 48h è più realistico.

# ── Session filter ───────────────────────────────────────────────
# Evita trading nelle ore morte (bassa liquidità = falsi segnali)
# Orari UTC: Londra apre 07:00, New York chiude 21:00
# Default: disabilitato — abilitare per EUR/USD in produzione
SESSION_FILTER_ENABLED = os.getenv("SESSION_FILTER_ENABLED", "false").lower() == "true"
SESSION_START_UTC      = int(os.getenv("SESSION_START_UTC", 7))   # 07:00 UTC = apertura Londra
SESSION_END_UTC        = int(os.getenv("SESSION_END_UTC",  21))   # 21:00 UTC = chiusura NY

