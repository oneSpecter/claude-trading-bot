# 🤖 Forex AI Bot — Claude + MetaTrader 5

Bot di trading automatico che combina **analisi tecnica locale** con **intelligenza artificiale Claude** (notizie, geopolitica, macro) e una **dashboard React** in tempo reale.

---

## 🏗️ Architettura

```
MetaTrader 5
    ↓  candele H1 + H4 live
indicators.py  ←── Pre-filtro GRATIS (EMA cross · RSI · ADX · filtro H4)
    ↓  solo se setup valido e allineato col trend H4
claude_analyst.py
    ├── Stadio 1: Analisi tecnica → technical_score (0-100)
    ├── Stadio 2: Web Search → notizie, Fed/BCE, macro  ← skippato se score < 55
    └── Stadio 3: Decisione finale + Devil's Advocate
    ↓
bot.py  ←── Valida confidenza minima (65%)
    ↓
mt5_broker.py  ←── Esegue ordine su MetaTrader 5
    ↓
journal.py  ←── Salva decisione + ragionamento in JSON + CSV
    ↓
server.py  ←── API REST per la dashboard (FastAPI)
    ↓
dashboard/  ←── React + Tailwind su localhost:5173
```

---

## 📁 File

| File | Cosa fa |
|---|---|
| `.env` | 🔑 Credenziali e parametri — **non committare mai su Git** |
| `config.py` | ⚙️ Tutte le impostazioni (legge da `.env`) |
| `indicators.py` | 📊 EMA, RSI, ATR, ADX, Bollinger, MACD, S/R, pattern, bias H4 |
| `claude_analyst.py` | 🧠 Analisi AI a 3 stadi con web search server-side |
| `mt5_broker.py` | 🔌 Connessione MT5 reale (solo Windows) |
| `mt5_mock.py` | 🧪 Simulatore MT5 per Mac/Linux |
| `bot.py` | 🚀 Loop principale e orchestrazione |
| `journal.py` | 📓 Log decisioni in JSON + CSV |
| `server.py` | 🌐 API REST per la dashboard (FastAPI) |
| `dashboard/` | 📊 Dashboard React in tempo reale |

---

## 🚀 Setup

### 1. Prerequisiti

```powershell
# Python 3.11+
python --version

# Node.js 18+ (per la dashboard)
node --version
```

### 2. Installa dipendenze Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Installa dipendenze dashboard

```powershell
cd dashboard
npm install
cd ..
```

### 4. Broker demo MT5

Scegli un broker gratuito con conto demo:
- **IC Markets EU** → icmarketseu.com (consigliato)
- **Pepperstone** → pepperstone.com
- **XM** → xm.com

Dopo la registrazione ricevi: Account ID, Password, Server name.

### 5. API Claude

1. Vai su [console.anthropic.com](https://console.anthropic.com/)
2. Crea un account e aggiungi credito ($5-10 per iniziare)
3. Genera una API Key (`sk-ant-...`)

### 6. Configura `.env`

```env
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-haiku-4-5-20251001

MT5_LOGIN=12345678
MT5_PASSWORD=tua_password
MT5_SERVER=ICMarketsSC-Demo

SYMBOL=EURUSD
DRY_RUN=true
```

> **Non modificare `config.py`** — tutte le credenziali vanno in `.env`.

---

## ▶️ Avvio

Apri **3 terminali**:

```powershell
# Terminale 1 — Bot
.\.venv\Scripts\Activate.ps1
python bot.py --dry

# Terminale 2 — API server dashboard
.\.venv\Scripts\Activate.ps1
uvicorn server:app --port 8000 --reload

# Terminale 3 — Dashboard React
cd dashboard
npm run dev
```

Poi apri **http://localhost:5173**

### Opzioni di avvio bot

| Comando | Descrizione |
|---|---|
| `python bot.py --dry` | Analizza, NON apre ordini (consigliato per iniziare) |
| `python bot.py --once --dry` | Un solo ciclo, nessun ordine (debug) |
| `python bot.py --once` | Un solo ciclo con ordini reali |
| `python bot.py` | Loop completo con ordini reali |
| `python bot.py --stats` | Mostra statistiche dal journal |

---

## 🧠 Strategia

### Pre-filtro tecnico (gratuito, nessuna API)

Ogni 5 minuti il bot controlla localmente — Claude viene chiamato **solo** se:

1. **EMA cross** — EMA 9 ha attraversato EMA 21 nelle ultime 3 candele H1
2. **RSI allineato** — RSI > 45 per long, RSI < 55 per short
3. **ADX > 25** — il mercato è trending (filtra ranging/laterale)
4. **H4 bias allineato** — il segnale H1 non è contro il trend principale su H4

### Claude AI — 3 stadi

**Stadio 1 — Analisi tecnica** (sempre eseguito)
Claude analizza tutti gli indicatori e restituisce un brief + `technical_score` (0-100).

**Stadio 2 — Notizie & Macro** (solo se score ≥ 55)
Claude cerca autonomamente: notizie recenti, decisioni Fed/BCE, dati macro (NFP, CPI, GDP, PMI), geopolitica, sentiment risk-on/off.
> Skippato se il setup tecnico è marginale → risparmio costi.

**Stadio 3 — Decisione + Devil's Advocate**
Claude decide BUY/SELL/HOLD, poi si sfida: *"I 3 motivi per cui potrei sbagliarsi"*.
Se i rischi reggono → trade. Altrimenti → HOLD.

### Filtro confidenza

Anche se Claude dice BUY, se `confidence < 65%` → HOLD forzato.

---

## 📊 Dashboard

La dashboard React mostra in tempo reale:
- **Stato bot** (scanning / analyzing / idle / stopped)
- **Mercato attuale** — prezzo, EMA trend, RSI, ADX, H4 bias
- **Ultima decisione** — BUY/SELL/HOLD con barra confidenza
- **Stage1 score** e se il web search è stato eseguito
- **Storico decisioni** — tabella cliccabile con brief tecnico, macro e devil's advocate
- **Grafico confidenza** — ultime 40 analisi con colori per decisione

---

## 💰 Costi stimati mensili

| Voce | Costo |
|---|---|
| Claude Haiku (~300-500 call/mese dopo ottimizzazioni) | ~$4-5 |
| Web Search API (~150-200 ricerche/mese con gate score) | ~$5-6 |
| Broker demo MT5 | €0 |
| **Totale stimato** | **~$9-11/mese** |

Con Claude Sonnet: ~$16-20/mese

> Il gate score (skip stage2 se score < 55) riduce le chiamate web search del ~40%.

---

## 🔧 Multi-symbol

Per tradare un altro asset cambia solo `.env`:

```env
# GBP/USD
SYMBOL=GBPUSD
SYMBOL_BASE=GBP
SYMBOL_QUOTE=USD
CENTRAL_BANK_BASE=Bank of England
CENTRAL_BANK_QUOTE=Federal Reserve

# USD/JPY
SYMBOL=USDJPY
SYMBOL_BASE=USD
SYMBOL_QUOTE=JPY
CENTRAL_BANK_BASE=Federal Reserve
CENTRAL_BANK_QUOTE=Bank of Japan

# Oro
SYMBOL=XAUUSD
SYMBOL_BASE=Gold
SYMBOL_QUOTE=USD
CENTRAL_BANK_BASE=
CENTRAL_BANK_QUOTE=Federal Reserve
```

---

## ⚠️ Note

- `MetaTrader5` funziona **solo su Windows**. Su Mac/Linux usa automaticamente `mt5_mock.py`
- Testa sempre in **DRY_RUN=true** prima di passare al live
- Il trading Forex comporta **rischi reali** — usa solo fondi che puoi permetterti di perdere
- Ogni decisione è salvata in `journal.json` con il ragionamento completo di Claude
