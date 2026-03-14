# 🤖 Forex AI Bot — Claude + MetaTrader 5

Bot di trading automatico per EUR/USD che combina **analisi tecnica locale**
con **intelligenza artificiale Claude** (notizie, geopolitica, macro).

---

## 🏗️ Architettura

```
MetaTrader 5
    ↓  candele H1 live
indicators.py  ←── Pre-filtro GRATIS (EMA, RSI, ATR, S/R, patterns)
    ↓  solo se c'è un setup valido
claude_analyst.py
    ├── Stadio 1: Analisi tecnica (Claude legge gli indicatori)
    ├── Stadio 2: Web Search → notizie EUR/USD, Fed, BCE, geopolitica
    └── Stadio 3: Decisione finale + Devil's Advocate (si sfida da solo)
    ↓
bot.py  ←── Valida confidenza (min 65%)
    ↓
mt5_broker.py  ←── Esegue ordine su MetaTrader 5
    ↓
journal.py  ←── Salva decisione + ragionamento completo
```

---

## 📁 File

| File | Cosa fa |
|---|---|
| `config.py` | ⚙️ Tutte le impostazioni — **modifica prima di tutto** |
| `indicators.py` | 📊 EMA, RSI, ATR, Bollinger, MACD, S/R, pattern candlestick |
| `claude_analyst.py` | 🧠 Analisi AI a 3 stadi con web search |
| `mt5_broker.py` | 🔌 Connessione MT5 reale (Windows) |
| `mt5_mock.py` | 🧪 Simulatore MT5 per Mac/Linux |
| `bot.py` | 🚀 Loop principale |
| `journal.py` | 📓 Log decisioni in JSON + CSV |

---

## 🚀 Setup

### 1. Installa dipendenze
```bash
pip install -r requirements.txt

# Solo Windows (per MT5 reale):
pip install MetaTrader5
```

### 2. Broker demo MT5
Scegli uno di questi broker gratuiti con conto demo:
- **IC Markets** → icmarkets.com (consigliato, spread bassi)
- **Pepperstone** → pepperstone.com
- **XM** → xm.com

Dopo la registrazione ricevi: Account ID, Password, Server

### 3. API Claude
1. Vai su https://console.anthropic.com/
2. Crea un account e aggiungi credito (anche solo $5-10 per iniziare)
3. Genera una API Key

### 4. Configura `config.py`
```python
ANTHROPIC_API_KEY = "sk-ant-..."    # la tua key
CLAUDE_MODEL = "claude-haiku-4-5-20251001"  # economico
MT5_LOGIN    = 12345678
MT5_PASSWORD = "tua_password"
MT5_SERVER   = "ICMarkets-Demo"
```

---

## ▶️ Uso

```bash
# Test senza ordini (consigliato per iniziare)
python bot.py --dry

# Un solo ciclo (debug)
python bot.py --once --dry

# Live demo
python bot.py

# Statistiche journal
python bot.py --stats
```

---

## 🧠 Logica Claude AI (3 stadi)

### Stadio 1 — Analisi Tecnica
Claude riceve tutti gli indicatori e scrive un brief professionale sul setup.

### Stadio 2 — Notizie & Macro (web search)
Claude cerca autonomamente:
- Notizie recenti EUR/USD
- Comunicazioni Fed e BCE
- Dati macro (NFP, inflazione, GDP, PMI)
- Tensioni geopolitiche
- Sentiment risk-on/risk-off

### Stadio 3 — Decisione + Devil's Advocate
Claude decide BUY/SELL/HOLD, poi si sfida da solo:
*"Quali sono i 3 motivi per cui potrei sbagliarmi?"*
Se i rischi sono troppo alti → cambia in HOLD.

---

## 💰 Costi stimati mensili

| Voce | Costo |
|---|---|
| Claude API (Haiku, ~720 call/mese) | ~$4 |
| Web Search nel API (~720 ricerche) | ~$7 |
| Broker demo MT5 | €0 |
| **Totale** | **~$11/mese** |

Con Claude Sonnet: ~$18/mese

---

## ⚠️ Note importanti

- `MetaTrader5` funziona **solo su Windows**. Su Mac/Linux usa `mt5_mock.py`
- Il bot è **pre-configurato per conto demo**. Per live: cambia `OANDA_ENV`
- Il trading Forex comporta **rischi reali**. Testa sempre in demo prima
- Ogni decisione è salvata nel `journal.json` con il ragionamento completo
