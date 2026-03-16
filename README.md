# Forex AI Bot — Claude + MetaTrader 5

Bot di trading automatico multi-simbolo che unisce **analisi tecnica locale**, **intelligenza artificiale Claude** con web search in tempo reale e una **dashboard React** con gestione di più bot in parallelo.

---

## Architettura — Multi-Bot

Il sistema supporta N bot in parallelo, ognuno su simbolo/strategia diversa, gestiti da un unico server FastAPI.

```
Dashboard React (localhost:8000)
    │
    ├── BotGrid        — vista griglia di tutti i bot configurati
    └── BotDashboard   — vista dettaglio singolo bot (journal, log, costi, controlli)
               │
         FastAPI server.py
               │
    ┌──────────┴──────────────────────────────────────┐
    │  bot.py --bot-id X --symbol Y --strategy Z      │
    │  bot.py --bot-id A --symbol B --strategy W      │  ← processi separati
    └─────────────────────────────────────────────────┘
               │
    bots/{bot_id}/
        ├── bot_status.json   ← stato live (prezzo, fase, indicatori)
        ├── bot_config.json   ← config runtime (dry_run, use_mock)
        ├── journal.json / journal.csv
        ├── api_costs.json
        └── bot.log
```

---

## Strategie disponibili

| Strategia | Tipo | Costo API | Quando usarla |
|-----------|------|-----------|---------------|
| `ema_rsi_ai_main` | AI 3-stage completa | ~$0.02/analisi | Trend forti, qualità massima (ADX ≥ 30, H4 richiesto, conf ≥ 78%) |
| `ema_rsi_ai` | AI standard | ~$0.008/analisi | Uso generale (ADX ≥ 25, H4 consigliato, conf ≥ 65%) |
| `ema_rsi_ai_scalp` | AI scalping | ~$0.005/analisi | Sessioni veloci, SL/TP stretti, posizioni brevi |
| `ema_rsi_manual` | Rule-based (no AI) | $0 | Costo zero, logic pura EMA × RSI × ADX |

### Confronto parametri SL/TP

| Strategia | SL | TP | R/R atteso | Conf. min |
|-----------|----|----|------------|-----------|
| `ema_rsi_ai_main` | ATR × 1.5 | ATR × 3.5 | > 2.3 | 78% |
| `ema_rsi_ai` | ATR × 1.5 | ATR × 2.5 | ~1.67 | 65% |
| `ema_rsi_ai_scalp` | ATR × 1.0 | ATR × 1.8 | 1.8 | 60% |
| `ema_rsi_manual` | ATR × 1.5 | ATR × 2.5 | ~1.67 | — |

---

## Flusso di analisi per tick

```
MetaTrader 5 (o mock sintetico / CSV storico)
    │
    ├── Candele H1 (150 barre)
    └── Candele H4 (100 barre, bias principale)
               │
        compute_all()  ← calcola tutti gli indicatori UNA SOLA VOLTA per tick
               │
   ┌───────────┴──────────────────────────────────────────────────┐
   │  EXIT CHECK  (gira sempre, anche fuori sessione)             │
   │  Per ogni posizione aperta (skip prima ora):                 │
   │  1. Scadenza tempo → chiude se > MAX_TRADE_DURATION_H        │
   │  2. Strategy.should_exit() → RSI estremo / EMA inversion     │
   └──────────────────────────────────────────────────────────────┘
               │
   ┌── Limite perdita giornaliera ──┐
   │   P&L oggi < -MAX_DAILY_LOSS% │ → stop nuovi trade per oggi
   └────────────────────────────────┘
               │
   ┌─ Session filter ─┐
   │  (07:00-21:00 UTC)│  ← blocca solo NUOVI trade fuori orario
   └──────────────────┘
               │
   Pre-filtro tecnico (strategy.should_trade() — GRATUITO per Manual)
        EMA cross recente?  +  RSI allineato?  +  ADX ≥ soglia?  +  H4 bias ok?
               │  solo se PASS e strategia AI:
   Claude — Stage 1: Analisi tecnica → technical_score (0-100)
               │
               ├── score < 65 → SKIP Stage 2 (risparmio web search)
               │
   Claude — Stage 2: Web Search → notizie BCE/Fed, NFP, CPI, geopolitica
               │
   Claude — Stage 3: Decisione finale + Devil's Advocate
               │       post-processing: convergence guard + R/R guard + ADX guard
               │
        confidence ≥ soglia?
               │
   Validazione trade (SL/TP coerenti con direzione)
               │
   MetaTrader 5 → open_trade(BUY/SELL, sl, tp)
               │
         bots/{bot_id}/journal.json + journal.csv
```

---

## Installazione

### Requisiti
- Python 3.11+
- Windows (per MT5 reale) — Mac/Linux usa il mock automatico
- Node.js 18+ (per la dashboard)
- Conto demo IC Markets o MetaQuotes-Demo
- API key Anthropic (necessaria solo per strategie AI)

### 1. Clona e installa dipendenze

```bash
git clone https://github.com/tuonome/claude-trading-bot
cd claude-trading-bot
pip install -r requirements.txt
```

### 2. Configura `.env`

```bash
cp .env.example .env
```

Apri `.env` e compila:

```env
ANTHROPIC_API_KEY=sk-ant-...          # da console.anthropic.com (non serve per ema_rsi_manual)
MT5_LOGIN=52791842                     # numero account demo MT5
MT5_PASSWORD=la_tua_password
MT5_SERVER=ICMarketsEU-Demo            # o MetaQuotes-Demo
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
SESSION_FILTER_ENABLED=true            # consigliato per produzione
USE_MOCK=false                         # true = dati sintetici senza MT5
MAX_DAILY_LOSS_PCT=2.0                 # stop se perdi >2% del capitale oggi
```

### 3. Installa la dashboard

```bash
cd dashboard
npm install
npm run build       # build di produzione (servita da FastAPI)
```

---

## Avvio

### Metodo consigliato — Dashboard

Apri **un solo terminale**:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

Apri il browser su `http://localhost:8000` e crea i bot dalla dashboard (pulsante **+ Nuovo Bot**).

### Avvio manuale da CLI (opzionale)

```bash
# Bot AI su EURUSD
python bot.py --bot-id eurusd_main --symbol EURUSD --strategy ema_rsi_ai_main --dry

# Bot manual su GBPUSD senza costi API
python bot.py --bot-id gbpusd_manual --symbol GBPUSD --strategy ema_rsi_manual --dry --mock

# Parametri utili
python bot.py --once     # singolo ciclo (debug)
python bot.py --stats    # mostra statistiche journal
```

| Flag | Significato |
|------|-------------|
| `--dry` | DRY-RUN: analisi completa, nessun ordine reale |
| `--mock` | Dati sintetici, non richiede MT5 |
| `--bot-id ID` | Identificativo bot (default: `default`) |
| `--symbol SYM` | Simbolo forex (default: da config.py) |
| `--strategy NAME` | Strategia da usare (default: `ema_rsi_ai`) |
| `--params '{"k":v}'` | Parametri JSON per la strategia |

> **Nota MT5:** Deve essere aperto e con **Algo Trading abilitato** (bottone verde nella toolbar) prima di avviare in modalità WATCH o TRADE.

---

## Dashboard

Accessibile su `http://localhost:8000` (o `http://<ip-tailscale>:8000` da iPhone).

### Vista griglia (home)

Mostra tutti i bot configurati in card compatte con:
- Stato (running / stopped / error) e fase corrente
- Prezzo corrente e ultima decisione del journal
- Badge strategia colorato per tipo (AI Main / AI Standard / AI Scalp / Manuale)
- Pulsanti Start / Stop / Apri (→ vista dettaglio)
- Barra statistiche globali aggregate (P&L totale, win rate, trade aperti)

### Vista dettaglio bot

| Sezione | Contenuto |
|---------|-----------|
| **Top bar** | Stato, prezzo, fase, H4 bias, pulsanti Start/Stop |
| **Stats row** | Win rate, P&L totale, confidenza media, tasso HOLD |
| **Stato mercato** | EMA trend, RSI, ADX, H4 bias + ultima analisi Claude |
| **Confidence chart** | Ultime 40 decisioni con confidenza — BUY/SELL/HOLD |
| **Costi API** | Breakdown per stage, oggi, mese, totale |
| **Decision table** | Journal ultime 15 decisioni con R/R, score, P&L |
| **Modalità operativa** | Selettore MOCK / WATCH / TRADE con conferma per TRADE |
| **Log panel** | Log in tempo reale, color-coded, auto-scroll, clear |

### 3 modalità operative

| Modalità | Dati | Ordini | Quando usarla |
|----------|------|--------|---------------|
| 🧪 **MOCK** | Sintetici generati localmente | No | Test senza MT5, sviluppo |
| 👁 **WATCH** | MT5 reali in tempo reale | No | Osservare e imparare |
| 💹 **TRADE** | MT5 reali in tempo reale | Sì (conto demo) | Trading reale su demo |

Il cambio tra WATCH e TRADE è attivo al **prossimo tick** (senza riavvio).
Il cambio su MOCK richiede il **riavvio del bot**.

### Controllo remoto da iPhone (Tailscale)
1. Installa Tailscale su PC e iPhone
2. Collega entrambi alla stessa rete Tailscale
3. Accedi a `http://<ip-tailscale>:8000` da Safari
4. Pulsante **STOP** nella dashboard per fermare il bot in sicurezza

---

## Strategia Manual — `ema_rsi_manual`

Logica rule-based pura, nessuna chiamata API, costo $0.

**Entrata:**
- BUY → EMA fast > EMA slow (RIALZISTA) + RSI ≥ `rsi_bull_min` + ADX ≥ `adx_min` + H4 bullish/neutral
- SELL → EMA fast < EMA slow (RIBASSISTA) + RSI ≤ `rsi_bear_max` + ADX ≥ `adx_min` + H4 bearish/neutral
- HOLD → condizioni non soddisfatte

**Uscita anticipata:**
- RSI ≥ `rsi_exit_high` su BUY → chiudi (ipercomprato)
- RSI ≤ `rsi_exit_low` su SELL → chiudi (ipervenduto)
- Inversione EMA + MACD confermata → chiudi

**Parametri configurabili:**

| Parametro | Default | Descrizione |
|-----------|---------|-------------|
| `rsi_bull_min` | 50 | RSI minimo per BUY |
| `rsi_bear_max` | 50 | RSI massimo per SELL |
| `adx_min` | 25 | ADX minimo (mercato trending) |
| `confidence` | 70 | Confidenza fissa del segnale |
| `require_h4` | true | Richiedi conferma bias H4 |
| `rsi_exit_high` | 75 | RSI chiusura BUY |
| `rsi_exit_low` | 25 | RSI chiusura SELL |

---

## Indicatori — formule e fonti

| Indicatore | Formula | Fonte |
|------------|---------|-------|
| EMA(n) | `EMA_t = price × k + EMA_{t-1} × (1-k)`, k = 2/(n+1) | Appel 1979 |
| RSI(14) | `100 - 100/(1 + avg_gain/avg_loss)`, Wilder smoothing | Wilder 1978 |
| ATR(14) | `max(H-L, \|H-C_prev\|, \|L-C_prev\|)`, EWM 14 | Wilder 1978 |
| ADX(14) | `EWM(\|+DI - -DI\| / (+DI + -DI)) × 100` | Wilder 1978 |
| MACD | `EMA(12) - EMA(26)`, signal = `EMA(9)` del MACD | Appel 1979 |
| Bollinger Bands | `SMA(20) ± 2σ` | Bollinger 1983 |
| Pivot Point | `(H + L + C) / 3` | Murphy 1999 |
| H4 Bias threshold | `avg(H-L, ultime 20 candele H4) × 20%` | dinamico |
| Lot size | `lot = risk_$ / (pip_risk × contract_size)` | Van Tharp 1998 |

---

## Risk Management

| Parametro | Valore default | Formula |
|-----------|----------------|---------|
| Risk per trade | 1% del capitale | `lot = (balance × 0.01) / (pip_risk × contract_size)` |
| Max posizioni | 1 per bot | Una posizione aperta per bot alla volta |
| Limite perdita giornaliera | 2% | Stop nuovi trade se P&L oggi < -2% del saldo |
| Scadenza trade | 24h | Chiusura automatica dopo MAX_TRADE_DURATION_H |

---

## Costi API stimati

| Scenario | Costo/mese stimato |
|----------|--------------------|
| Haiku, stage2 skippato spesso (score < 65) | ~$3-5 |
| Haiku con web search regolare | ~$6-10 |
| Sonnet (analisi più profonde) | ~$12-18 |
| Manual strategy (ema_rsi_manual) | **$0** |

**Ottimizzazioni attive:**
- Prompt caching sul system prompt (−70% token fissi)
- Gate stage1→stage2: web search solo se score ≥ 65
- Fast path stage3: max_tokens ridotti per setup score ≥ 80
- Exit check skip: nessuna chiamata AI nella prima ora dal trade

---

## Sicurezza e protezioni

| Protezione | Descrizione |
|------------|-------------|
| Validazione trade | SL/TP controllati prima dell'esecuzione — blocca ordini con parametri invertiti |
| Limite perdita giornaliera | Stop automatico se P&L oggi < -MAX_DAILY_LOSS_PCT% |
| Max errori consecutivi | Il bot si ferma dopo 3 errori MT5 di fila |
| Fase "error" | Dashboard segnala in rosso e sblocca Start per riavvio |
| DRY-RUN | Nessun ordine reale — analisi completa ma esecuzione bloccata |
| Conferma TRADE | Passare a TRADE dalla dashboard richiede conferma esplicita |
| API key check | Il bot verifica la presenza dell'API key all'avvio (solo strategie AI) |

---

## Configurazione completa

Tutte le impostazioni sono in `config.py` e sovrascrivibili via `.env`:

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `SYMBOL` | EURUSD | Simbolo da tradare (default, override da CLI) |
| `TIMEFRAME` | H1 | Timeframe principale |
| `CLAUDE_MODEL` | claude-haiku-4-5-20251001 | Modello AI (haiku=economico, sonnet=profondo) |
| `MIN_CONFIDENCE` | 65 | Confidenza minima Claude per aprire trade (%) |
| `RISK_PCT` | 0.01 | Rischio per trade (1% del capitale) |
| `ATR_SL_MULT` | 1.5 | Moltiplicatore ATR per Stop Loss |
| `ATR_TP_MULT` | 2.5 | Moltiplicatore ATR per Take Profit |
| `ADX_THRESHOLD` | 25 | ADX minimo per mercato trending |
| `WEB_SEARCH_MIN_SCORE` | 65 | Score minimo stage1 per attivare web search |
| `MAX_DAILY_LOSS_PCT` | 2.0 | % perdita giornaliera max prima di stop |
| `MAX_TRADE_DURATION_H` | 24 | Ore massime per trade aperto |
| `SESSION_FILTER_ENABLED` | false | Abilita filtro orario sessione |
| `SESSION_START_UTC` | 7 | Inizio sessione (07:00 UTC = apertura Londra) |
| `SESSION_END_UTC` | 21 | Fine sessione (21:00 UTC = chiusura NY) |
| `CHECK_INTERVAL` | 300 | Secondi tra un tick e l'altro (5 min) |
| `USE_MOCK` | false | Forza broker simulato |
| `MOCK_DATA_FILE` | (vuoto) | CSV dati storici per mock (da histdata.com) |
| `MT5_PATH` | (vuoto) | Percorso a terminal64.exe (consigliato) |

---

## File di dati generati

Per ogni bot, tutti i file sono in `bots/{bot_id}/`:

| File | Contenuto |
|------|-----------|
| `bot_status.json` | Stato live del bot (letto dalla dashboard ogni 5s) |
| `bot_config.json` | Configurazione runtime (dry_run, use_mock) — modificabile dalla dashboard |
| `journal.json` | Storico completo decisioni con brief Claude, R/R, P&L |
| `journal.csv` | Versione tabellare per Excel/pandas |
| `api_costs.json` | Costi API dettagliati per ogni chiamata |
| `bot.log` | Log completo del bot |
| `bot.pid` | PID del processo (per gestione start/stop) |

Il registro di tutti i bot configurati è in `bots_config.json` nella root.

---

## Struttura del progetto

```
claude-trading-bot/
├── bot.py                  # Loop principale — orchestrazione tick, CLI args
├── config.py               # Configurazione centrale + variabili .env
├── indicators.py           # Indicatori tecnici (EMA, RSI, ATR, ADX, MACD, BB) + pre-filtro
├── claude_analyst.py       # AI 3 stadi + exit check + cost tracking
├── mt5_broker.py           # Wrapper MetaTrader 5 (Windows)
├── mt5_mock.py             # Broker simulato con SL/TP automatici
├── journal.py              # Trade journal JSON + CSV + statistiche
├── server.py               # FastAPI: API multi-bot + avvio subprocess
├── strategies/
│   ├── __init__.py         # Plugin loader: load_strategy(name, params)
│   ├── base.py             # BaseStrategy ABC (should_trade / should_exit)
│   ├── ema_rsi_ai_main.py  # AI 3-stage completa (massima qualità)
│   ├── ema_rsi_ai.py       # AI standard (uso generale)
│   ├── ema_rsi_ai_scalp.py # AI scalping (trade veloci)
│   └── ema_rsi_manual.py   # Rule-based senza AI (costo $0)
├── bots/
│   └── {bot_id}/           # Directory per-bot (status, journal, log, config)
├── bots_config.json        # Registro di tutti i bot configurati
├── dashboard/
│   ├── src/
│   │   ├── App.jsx                      # Root: BotGrid + BotDashboard con routing
│   │   └── components/
│   │       ├── BotCard.jsx              # Card bot nella griglia
│   │       ├── BotDashboard.jsx         # Vista dettaglio singolo bot
│   │       ├── GlobalStats.jsx          # Statistiche aggregate multi-bot
│   │       ├── NewBotModal.jsx          # Modal creazione nuovo bot
│   │       ├── LogPanel.jsx             # Log real-time
│   │       ├── ModeControl.jsx          # Selettore MOCK/WATCH/TRADE
│   │       └── ui.jsx                   # Componenti UI (GlowCard, AnimatedNumber…)
│   └── dist/                            # Build produzione (servita da FastAPI)
├── .env.example
└── requirements.txt
```

---

## Sviluppo senza MT5 (Mac/Linux/offline)

```bash
# .env
USE_MOCK=true
MOCK_DATA_FILE=dati_eurusd.csv    # opzionale: CSV con dati reali da histdata.com
```

```bash
python bot.py --bot-id test --symbol EURUSD --strategy ema_rsi_manual --dry --mock
```

Il mock simula:
- Generazione candele OHLC con trend alternati e noise realistico
- Chiusura automatica SL/TP su ogni candela (high/low check)
- Prezzo di esecuzione = ultimo close ± spread (1.3 pip EUR/USD)
- Reset mock non persistente tra sessioni
