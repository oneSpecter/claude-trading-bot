# Forex AI Bot — Claude + MetaTrader 5

Bot di trading automatico che combina **analisi tecnica locale** con **intelligenza artificiale Claude** (notizie, geopolitica, macro) e una **dashboard React** in tempo reale.

---

## Architettura

```
MetaTrader 5  (o mock per dev/Linux/Mac)
    ↓  candele H1 + H4 live
indicators.py  ←── Pre-filtro GRATIS (EMA cross · RSI · ADX · bias H4)
    ↓  solo se setup valido e allineato col trend H4
claude_analyst.py
    ├── Stadio 1: Analisi tecnica → technical_score (0-100)
    ├── Stadio 2: Web Search → notizie, Fed/BCE, macro  ← skippato se score < 55
    └── Stadio 3: Decisione finale + Devil's Advocate
    ↓
    ├── check_exit()  ←── AI exit check su trade aperti (anche fuori sessione)
    └── analyze()     ←── Analisi per nuovi trade (solo in sessione)
bot.py  ←── Valida confidenza minima (65%)
    ↓
mt5_broker.py  ←── Esegue / chiude ordini su MetaTrader 5
    ↓
journal.py  ←── Salva decisione + risultati in JSON + CSV
    ↓
server.py  ←── API REST (FastAPI, porta 8000)
    ↓
dashboard/  ←── React + Tailwind su localhost:5173
```

---

## File

| File | Cosa fa |
|---|---|
| `.env` | Credenziali e parametri — **non committare mai su Git** |
| `config.py` | Tutte le impostazioni (legge da `.env`) |
| `indicators.py` | EMA, RSI, ATR, ADX, Bollinger, MACD, S/R, pattern, bias H4 |
| `claude_analyst.py` | Analisi AI a 3 stadi + exit check su posizioni aperte |
| `mt5_broker.py` | Connessione MT5 reale (solo Windows) |
| `mt5_mock.py` | Simulatore MT5 per dev/Mac/Linux |
| `bot.py` | Loop principale e orchestrazione |
| `journal.py` | Log decisioni e risultati trade in JSON + CSV |
| `server.py` | API REST per la dashboard (FastAPI) |
| `dashboard/` | Dashboard React in tempo reale |

---

## Setup

### 1. Prerequisiti

```powershell
python --version   # 3.11+
node --version     # 18+
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

Registra un conto demo gratuito:
- **IC Markets EU** → icmarketseu.com (consigliato, spread bassi)
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
SESSION_FILTER_ENABLED=true
DRY_RUN=true
```

> **Non modificare `config.py`** — tutte le impostazioni vanno in `.env`.

---

## Avvio

Apri **3 terminali**:

```powershell
# Terminale 1 — Bot
.\.venv\Scripts\Activate.ps1
python bot.py --dry

# Terminale 2 — API server
.\.venv\Scripts\Activate.ps1
uvicorn server:app --port 8000 --reload

# Terminale 3 — Dashboard React
cd dashboard
npm run dev
```

Apri **http://localhost:5173**

### Opzioni di avvio

| Comando | Descrizione |
|---|---|
| `python bot.py --dry` | Analizza, NON apre ordini (consigliato per iniziare) |
| `python bot.py --once --dry` | Un solo ciclo, nessun ordine (debug) |
| `python bot.py --once` | Un solo ciclo con ordini reali |
| `python bot.py` | Loop completo con ordini reali |
| `python bot.py --stats` | Mostra statistiche dal journal |

---

## Strategia

### Flusso per tick (ogni 5 minuti)

```
1. Controlla trade chiusi (SL/TP raggiunto) → aggiorna journal
2. Scarica candele H1 + H4
3. AI exit check  ← se ci sono trade aperti, Claude decide se chiudere
4. Session filter ← blocca SOLO nuovi trade fuori orario (07:00-21:00 UTC)
5. Pre-filtro tecnico gratuito
6. Claude 3-stadi per nuova entrata
7. Esegui trade
```

> Il bot NON si spegne mai — gestisce le posizioni aperte anche fuori sessione.

### Pre-filtro tecnico (nessuna API call)

Claude viene chiamato **solo** se:

1. **EMA crossover** — EMA 9 ha attraversato EMA 21 nelle ultime 3 candele H1
2. **RSI allineato** — RSI > 45 per long, RSI < 55 per short
3. **ADX > 25** — mercato trending (filtra ranging/laterale)
4. **H4 bias allineato** — segnale H1 non contro il trend principale H4

### Claude AI — 3 stadi

**Stadio 1 — Analisi tecnica** (sempre eseguito)
Claude analizza tutti gli indicatori e restituisce un brief + `technical_score` (0-100).

**Stadio 2 — Notizie & Macro** (solo se score ≥ 55)
Claude cerca: notizie recenti, decisioni Fed/BCE, dati macro (NFP, CPI, GDP, PMI), geopolitica, sentiment risk-on/off.
> Skippato se il setup è marginale — risparmio costi ~40%.

**Stadio 3 — Decisione + Devil's Advocate**
Claude decide BUY/SELL/HOLD, poi si sfida: *"3 motivi per cui potrei sbagliarsi"*.
Se i rischi reggono → trade. Altrimenti → HOLD.

### AI Exit Check (gestione attiva posizioni)

Ogni tick, se c'è un trade aperto, Claude valuta se chiuderlo anticipatamente:
- Trend invertito (EMA/MACD opposti alla direzione)
- RSI in esaurimento estremo (>78 per BUY, <22 per SELL)
- ADX < 20 — trend che si esaurisce
- P&L positivo (>30% del TP) + segnale di inversione

Richiede confidenza ≥ 65% per agire — in caso di dubbio resta aperto (HOLD default).

### Risk management

| Parametro | Valore | Logica |
|---|---|---|
| Stop Loss | 1.5 × ATR | Volatility-adaptive, evita stop troppo stretti |
| Take Profit | 2.5 × ATR | R:R = 1.67:1 — rentabile anche con win rate 40% |
| Rischio per trade | 1% del capitale | Position sizing Kelly-style conservativo |
| Max posizioni aperte | 1 | Evita over-exposure |
| Confidenza minima | 65% | Gate qualità per i segnali Claude |

---

## Indicatori — fonti e correttezza

Tutti gli indicatori usano le formule originali dei rispettivi autori:

| Indicatore | Formula | Fonte |
|---|---|---|
| EMA | α = 2/(span+1), Wilder smoothing | Appel, *Technical Analysis* (2005) |
| RSI | Wilder's smoothed RS, com = N-1 | Wilder, *New Concepts in Technical Trading* (1978) |
| ATR | TR = max(H-L, \|H-PrevC\|, \|L-PrevC\|) | Wilder (1978) |
| MACD | EMA(12) − EMA(26), signal EMA(9) | Appel (1979) |
| Bollinger Bands | SMA(20) ± 2σ | Bollinger, *Bollinger on Bollinger Bands* (2002) |
| ADX / DI+/DI− | Wilder's smoothing (com=N-1) | Wilder (1978) |
| Pivot Points | PP=(H+L+C)/3, R1=2PP-L, S1=2PP-H | Murphy, *Technical Analysis of Financial Markets* (1999) |
| ATR-based SL/TP | SL=1.5×ATR, TP=2.5×ATR | Van Tharp, *Trade Your Way to Financial Freedom* (1998) |
| Lot sizing | lot = risk_$ / (contract_size × SL_distance) | Position sizing standard per forex |

---

## Costi stimati mensili

| Voce | Costo |
|---|---|
| Claude Haiku (~300-500 call/mese, prompt caching) | ~$4-5 |
| Web Search API (~150-200 ricerche/mese con gate score) | ~$5-6 |
| AI exit check (~$0.002/call, solo con trade aperti) | ~$0.5-1 |
| Broker demo MT5 | €0 |
| **Totale stimato** | **~$10-12/mese** |

Con Claude Sonnet: ~$18-22/mese

> Il gate score (skip stage2 se score < 55) riduce le chiamate web search del ~40%.
> Il prompt caching riduce i costi stage1/stage3 del ~70%.

---

## Dashboard

Mostra in tempo reale:
- **Stato bot** (scanning / analyzing / idle / stopped)
- **Mercato attuale** — prezzo, EMA trend, RSI, ADX, H4 bias
- **Ultima decisione** — BUY/SELL/HOLD con barra confidenza
- **Stage1 score** e se il web search è stato eseguito
- **Storico decisioni** — brief tecnico, macro e devil's advocate
- **Grafico confidenza** — ultime 40 analisi con colori per decisione
- **Log in tempo reale** — output del bot aggiornato ogni 2s

---

## Multi-symbol

Cambia solo `.env` per tradare altri asset:

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

## Note

- `MetaTrader5` funziona **solo su Windows**. Su Mac/Linux usa automaticamente `mt5_mock.py`
- Testa sempre in modalità dry-run (`python bot.py --dry`) prima di passare al live
- Il trading Forex comporta **rischi reali** — usa solo fondi che puoi permetterti di perdere
- Ogni decisione è salvata in `journal.json` con ragionamento completo di Claude
