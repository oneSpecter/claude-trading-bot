# Forex AI Bot — Claude + MetaTrader 5

Bot di trading automatico per EUR/USD (e altri simboli forex) che unisce **analisi tecnica locale**, **intelligenza artificiale Claude** con web search in tempo reale e una **dashboard React** accessibile anche da remoto via Tailscale.

---

## Come funziona — flusso completo

```
MetaTrader 5  (o mock sintetico / CSV storico)
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
   │  2. Claude AI → valuta se chiudere prima dello SL            │
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
   Pre-filtro tecnico (GRATUITO — nessuna API call)
        EMA cross recente?  +  RSI allineato?  +  ADX ≥ 25?  +  H4 bias ok?
               │  solo se PASS
   Claude — Stadio 1: Analisi tecnica → technical_score (0-100)
               │
               ├── score < 65 → SKIP Stage2 (risparmio web search)
               │
   Claude — Stadio 2: Web Search → notizie BCE/Fed, NFP, CPI, geopolitica
               │
   Claude — Stadio 3: Decisione finale + Devil's Advocate
               │       applica regole R1-R3 (convergenza, R/R, ADX)
               │       [R3 anche enforced in post-processing]
               │
        confidence ≥ 65%?
               │
   Validazione trade (SL/TP coerenti con direzione)
               │
   MetaTrader 5 → open_trade(BUY/SELL, sl, tp)
               │
         journal.json / journal.csv
```

---

## Installazione

### Requisiti
- Python 3.11+
- Windows (per MT5 reale) — Mac/Linux usa il mock automatico
- Node.js 18+ (per la dashboard)
- Conto demo IC Markets o MetaQuotes-Demo
- API key Anthropic (console.anthropic.com)

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
ANTHROPIC_API_KEY=sk-ant-...          # da console.anthropic.com
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

### Metodo consigliato

Apri **2 terminali**:

**Terminale 1 — Server + Dashboard:**
```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```
Apri il browser su `http://localhost:8000`

**Terminale 2 — Bot (opzionale, puoi avviarlo anche dalla dashboard):**
```bash
python bot.py --dry --mock    # MOCK: dati sintetici, nessun ordine
python bot.py --dry           # WATCH: dati MT5 reali, nessun ordine
python bot.py                 # TRADE: dati MT5 reali + ordini demo
python bot.py --once          # singolo ciclo (debug)
python bot.py --stats         # mostra statistiche journal
```

> **Nota MT5:** Deve essere aperto e con **Algo Trading abilitato** (bottone verde nella toolbar) prima di avviare il bot in modalità WATCH o TRADE.

---

## Dashboard

Accessibile su `http://localhost:8000` (o `http://<ip-tailscale>:8000` da iPhone).

| Sezione | Contenuto |
|---------|-----------|
| **Top bar** | Stato bot, prezzo corrente, fase, H4 bias, pulsanti Start/Stop |
| **Stats row** | Win rate, P&L totale, confidenza media, tasso HOLD |
| **Stato mercato** | EMA trend, RSI, ADX, H4 bias + ultima analisi Claude |
| **Confidence chart** | Ultime 40 decisioni con confidenza — BUY/SELL/HOLD |
| **Modalità operativa** | Selettore MOCK / WATCH / TRADE con conferma per TRADE |
| **Costi API** | Breakdown per stage, oggi, mese, totale |
| **Decision table** | Journal ultime 15 decisioni con R/R, score, P&L |
| **Log panel** | Log in tempo reale, color-coded, auto-scroll, clear |

### 3 modalità operative (selezionabili dalla dashboard)

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

## Strategia di trading

### Pre-filtro tecnico (4 condizioni, tutte obbligatorie)

| Condizione | Parametro | Logica |
|------------|-----------|--------|
| EMA crossover recente | EMA 9 / EMA 21 | Crossover nelle ultime 3 candele H1 |
| RSI allineato | RSI 14, soglie 45/55 | Long: RSI > 45 · Short: RSI < 55 |
| ADX trending | ADX 14 ≥ 25 | Filtra mercati ranging (falsi segnali) |
| H4 bias ok | EMA 9/21 su H4 (threshold dinamico) | Non tradare contro il trend principale |

### Risk Management

| Parametro | Valore | Formula |
|-----------|--------|---------|
| Stop Loss | 1.5 × ATR | `price ± ATR(14) × 1.5` |
| Take Profit | 2.5 × ATR | `price ± ATR(14) × 2.5` |
| Risk per trade | 1% del capitale | `lot = (balance × 0.01) / (pip_risk × contract_size)` |
| R/R atteso | ~1.67 | 2.5 / 1.5 |
| Max posizioni | 1 | Una posizione aperta alla volta |
| Limite perdita giornaliera | 2% | Stop nuovi trade se P&L oggi < -2% del saldo |

### Gestione posizioni aperte (AI Exit)

Il bot monitora ogni posizione aperta ad ogni tick (5 min), **anche fuori orario**, e la chiude anticipatamente se:

- **Scadenza tempo** — aperta da più di `MAX_TRADE_DURATION_H` ore (default 24h)
- **Inversione trend** — EMA/MACD opposti alla direzione del trade
- **RSI esausto** — > 78 per BUY, < 22 per SELL
- **Trend in esaurimento** — ADX < 20
- **Profitto a rischio** — P&L > 30% del TP + segnale di inversione

> L'exit check viene skippato nella **prima ora** dal trade aperto per evitare rumore.

---

## Analisi AI — 3 stadi

### Stadio 1 — Analisi tecnica (sempre)
Claude riceve tutti gli indicatori + ultime 10 candele e restituisce:
- Brief tecnico professionale (200 parole)
- `technical_score` (0-100)
- `bias` (bullish / bearish / neutral)

### Stadio 2 — Web Search (solo se score ≥ 65)
Claude cerca autonomamente notizie recenti su BCE, Fed, NFP, CPI, geopolitica e restituisce:
- Brief fondamentale (200 parole)
- `fundamental_score` (0-100)
- `convergence` (aligned / divergent / neutral)

### Stadio 3 — Decisione finale + Devil's Advocate
Claude applica 3 regole obbligatorie (enforce anche in post-processing):

| Regola | Condizione | Effetto |
|--------|------------|---------|
| **R1 — Convergenza** | Tecnico e fondamentale divergono > 30 punti | -20 confidence |
| **R2 — Risk/Reward** | R/R < 1.5 | Considera seriamente HOLD |
| **R3 — Trend debole** | ADX < 20 | -15 confidence, privilegia HOLD |

Poi sfida la propria decisione con **2 rischi specifici** (devil's advocate). Se la decisione regge → trade. Se no → HOLD.

> Per setup con score ≥ 80, il modello usa un path accelerato (meno token, stessa qualità).

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

## Configurazione completa

Tutte le impostazioni sono in `config.py` e sovrascrivibili via `.env`:

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `SYMBOL` | EURUSD | Simbolo da tradare |
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

## Costi API stimati

| Scenario | Costo/mese stimato |
|----------|--------------------|
| Haiku, stage2 skippato spesso (score < 65) | ~$3-5 |
| Haiku con web search regolare | ~$6-10 |
| Sonnet (analisi più profonde) | ~$12-18 |

**Ottimizzazioni attive:**
- Prompt caching sul system prompt (−70% token fissi)
- Gate stage1→stage2: web search solo se score ≥ 65 (era 55)
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

---

## File di dati generati

| File | Contenuto |
|------|-----------|
| `journal.json` | Storico completo decisioni con brief Claude, R/R, P&L |
| `journal.csv` | Versione tabellare per Excel/pandas |
| `api_costs.json` | Costi API dettagliati per ogni chiamata |
| `bot_status.json` | Stato live del bot (letto dalla dashboard ogni 5s) |
| `bot_config.json` | Configurazione runtime (dry_run, use_mock) — modificabile dalla dashboard |
| `bot.log` | Log completo del bot |
| `bot_stop.flag` | Se esiste → il bot si ferma al prossimo tick |

---

## Struttura del progetto

```
claude-trading-bot/
├── bot.py                  # Loop principale — orchestrazione tick
├── config.py               # Configurazione centrale + variabili .env
├── indicators.py           # Indicatori tecnici (EMA, RSI, ATR, ADX, MACD, BB)
├── claude_analyst.py       # AI 3 stadi + exit check + cost tracking
├── mt5_broker.py           # Wrapper MetaTrader 5 (Windows)
├── mt5_mock.py             # Broker simulato con SL/TP automatici
├── journal.py              # Trade journal JSON + CSV + statistiche
├── server.py               # FastAPI: API dashboard + avvio subprocess bot
├── dashboard/
│   ├── src/
│   │   ├── App.jsx                      # Layout principale
│   │   └── components/
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
python bot.py --dry --mock    # dati sintetici + nessun ordine reale
```

Il mock simula:
- Generazione candele OHLC con trend alternati e noise realistico
- Chiusura automatica SL/TP su ogni candela (high/low check)
- Prezzo di esecuzione = ultimo close ± spread (1.3 pip EUR/USD)
- Reset mock non persistente tra sessioni
