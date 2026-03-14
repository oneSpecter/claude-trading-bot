"""
CLAUDE AI ANALYST
-----------------
Cuore del bot. Usa un sistema di autoprompting a 3 stadi:

  Stadio 1 — ANALISI TECNICA
    Claude riceve gli indicatori e riassume il setup tecnico.

  Stadio 2 — RICERCA NOTIZIE & GEOPOLITICA (web_search abilitato)
    Claude cerca autonomamente news su EUR/USD, Fed, BCE,
    eventi geopolitici, dati macro rilevanti.

  Stadio 3 — DECISIONE FINALE + DEVIL'S ADVOCATE
    Claude prende una decisione, poi la sfida da solo
    cercando i motivi per cui potrebbe sbagliarsi.
    Se la decisione regge → trade. Se no → HOLD.

Ogni stadio alimenta il successivo (chain-of-thought).
"""

import json
import logging
import requests
from datetime import datetime
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, SYMBOL, MIN_CONFIDENCE

log = logging.getLogger("ClaudeAnalyst")

API_URL = "https://api.anthropic.com/v1/messages"
HEADERS = {
    "x-api-key": ANTHROPIC_API_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

# ── Tool: web_search ────────────────────────────────────────────
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
}

# ── System prompt (costante, usa prompt caching) ─────────────────
SYSTEM_PROMPT = """Sei un trader forex professionale e analista di mercato con 20 anni di esperienza.
Il tuo compito è analizzare il mercato EUR/USD e fornire decisioni di trading precise e motivate.

Le tue analisi devono essere:
- Oggettive e basate su dati concreti
- Integrate tra analisi tecnica e fondamentale
- Consapevoli del contesto macro e geopolitico globale
- Calibrate sul rischio (non tradare in condizioni di incertezza estrema)

Quando non c'è un setup chiaro, la risposta corretta è HOLD — non forzare trade.
La tua priorità assoluta è la preservazione del capitale.

Rispondi SEMPRE e SOLO con JSON valido quando richiesto, senza markdown, senza testo prima o dopo."""


def _call_api(messages: list, tools: list = None, max_tokens: int = 1500) -> dict:
    """Chiama l'API Claude e gestisce errori."""
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools

    resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _extract_text(response: dict) -> str:
    """Estrae tutto il testo dalla risposta Claude (gestisce tool_use)."""
    parts = []
    for block in response.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
        elif block.get("type") == "tool_result":
            parts.append(str(block.get("content", "")))
    return "\n".join(parts)


def _extract_tool_results(response: dict) -> list:
    """Estrae i risultati delle tool call per passarli al turno successivo."""
    tool_uses = []
    tool_results = []
    for block in response.get("content", []):
        if block.get("type") == "tool_use":
            tool_uses.append(block)
    return tool_uses


# ════════════════════════════════════════════════════════════════
#  STADIO 1 — ANALISI TECNICA
# ════════════════════════════════════════════════════════════════
def stage1_technical(tech: dict) -> str:
    """Claude analizza il setup tecnico e restituisce un brief strutturato."""
    log.info("  [Stadio 1] Analisi tecnica...")

    sr = tech["support_resistance"]
    patterns = ", ".join(tech["candlestick_patterns"])
    cross = tech["cross_signal"]
    cross_str = f"{cross[0]} rilevato su candela {cross[1]}" if cross else "Nessun crossover recente"

    prompt = f"""Analizza questo setup tecnico su {SYMBOL} (timeframe H1) e fornisci un brief professionale.

═══ DATI DI MERCATO ═══
Prezzo attuale:     {tech['price']}
EMA 9:             {tech['ema_fast']}
EMA 21:            {tech['ema_slow']}
Trend EMA:         {tech['ema_trend']}
Crossover:         {cross_str}

RSI (14):          {tech['rsi']}
MACD:              {tech['macd']} | Signal: {tech['macd_signal']} | Hist: {tech['macd_hist']}
MACD bias:         {tech['macd_bias']}

ATR (14):          {tech['atr']}
Bollinger:         {tech['bb_position']}
  Upper:           {tech['bb_upper']}
  Lower:           {tech['bb_lower']}

Momentum (10):     {tech['momentum_10']}

═══ LIVELLI CHIAVE ═══
Pivot:   {sr['pivot']}
R1: {sr['r1']}  R2: {sr['r2']}
S1: {sr['s1']}  S2: {sr['s2']}
Massimi recenti: {sr['recent_highs']}
Minimi recenti:  {sr['recent_lows']}

═══ PATTERN CANDLESTICK ═══
{patterns}

═══ ULTIME 10 CANDELE ═══
{tech['last_10_candles']}

═══ LIVELLI SL/TP SUGGERITI (ATR-based) ═══
Per LONG:  SL={tech['atr_sl']}  TP={tech['atr_tp']}
Per SHORT: SL={tech['atr_sl_short']}  TP={tech['atr_tp_short']}

Fornisci un brief tecnico professionale in 150-200 parole coprendo:
1. Bias direzionale tecnico (rialzista/ribassista/neutro) e solidità del setup
2. Livelli critici da monitorare (supporti/resistenze più rilevanti)
3. Qualità del setup (forte/medio/debole) con spiegazione
4. Eventuali segnali contradditori o warning
"""
    resp = _call_api([{"role": "user", "content": prompt}])
    brief = _extract_text(resp)
    log.info(f"  [Stadio 1] Brief tecnico: {brief[:100]}...")
    return brief


# ════════════════════════════════════════════════════════════════
#  STADIO 2 — NOTIZIE & GEOPOLITICA (con web search)
# ════════════════════════════════════════════════════════════════
def stage2_news(tech_brief: str) -> str:
    """Claude cerca autonomamente notizie rilevanti e le analizza."""
    log.info("  [Stadio 2] Ricerca notizie e contesto macro...")

    today = datetime.utcnow().strftime("%d %B %Y")

    prompt = f"""Oggi è {today}. Hai già questo brief tecnico su EUR/USD:

{tech_brief}

Ora devi arricchire l'analisi con il contesto fondamentale e geopolitico.
Esegui ricerche web per trovare informazioni AGGIORNATE su:

1. Notizie recenti su EUR/USD (ultime 24-48 ore)
2. Decisioni o comunicazioni di Fed (Federal Reserve) e BCE (Banca Centrale Europea)
3. Dati macro importanti: inflazione USA/EU, NFP, GDP, PMI
4. Tensioni geopolitiche che impattano i mercati (guerra, sanzioni, elezioni)
5. Sentiment di rischio globale (risk-on vs risk-off)
6. Posizionamento speculativo sul dollaro e sull'euro

Dopo le ricerche, scrivi un brief fondamentale di 150-200 parole con:
- Bias fondamentale (pro-EUR / pro-USD / neutro)
- Catalizzatori principali in gioco
- Rischi da tenere presente
- Coerenza o divergenza con il setup tecnico
"""

    # Messaggio iniziale
    messages = [{"role": "user", "content": prompt}]

    # Prima chiamata con web_search abilitato
    resp = _call_api(messages, tools=[WEB_SEARCH_TOOL], max_tokens=2000)

    # Gestisci loop tool_use → tool_result fino a risposta finale
    max_iterations = 5
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        has_tool_use = any(b.get("type") == "tool_use" for b in resp.get("content", []))

        if not has_tool_use:
            break  # Claude ha finito le ricerche

        # Aggiungi la risposta dell'assistente alla conversazione
        messages.append({"role": "assistant", "content": resp["content"]})

        # Costruisci i tool_result
        tool_results = []
        for block in resp["content"]:
            if block.get("type") == "tool_use":
                # I risultati della ricerca sono già nei blocchi successivi
                # Ma dobbiamo passare un placeholder per continuare la conversazione
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": "Risultato ricerca ottenuto.",
                })

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        resp = _call_api(messages, tools=[WEB_SEARCH_TOOL], max_tokens=2000)

    news_brief = _extract_text(resp)
    log.info(f"  [Stadio 2] Brief macro: {news_brief[:100]}...")
    return news_brief


# ════════════════════════════════════════════════════════════════
#  STADIO 3 — DECISIONE FINALE + DEVIL'S ADVOCATE
# ════════════════════════════════════════════════════════════════
def stage3_decision(tech_brief: str, news_brief: str, tech: dict) -> dict:
    """
    Claude prende la decisione finale, poi fa il devil's advocate —
    sfida attivamente la sua stessa analisi per validarla.
    """
    log.info("  [Stadio 3] Decisione finale + devil's advocate...")

    prompt = f"""Hai completato l'analisi tecnica e fondamentale su EUR/USD. Ora devi prendere la decisione finale.

═══ BRIEF TECNICO ═══
{tech_brief}

═══ BRIEF FONDAMENTALE/MACRO ═══
{news_brief}

═══ PARAMETRI OPERATIVI ═══
Prezzo attuale: {tech['price']}
Per LONG:  SL={tech['atr_sl']}  TP={tech['atr_tp']}
Per SHORT: SL={tech['atr_sl_short']}  TP={tech['atr_tp_short']}

═══ PROCESSO DECISIONALE RICHIESTO ═══

STEP A — DECISIONE INIZIALE:
Basandoti su tutta l'analisi, qual è la tua raccomandazione iniziale? (BUY / SELL / HOLD)

STEP B — DEVIL'S ADVOCATE:
Ora assumi la posizione OPPOSTA. Elenca i 3 motivi più forti per cui la tua decisione iniziale
potrebbe essere SBAGLIATA. Sii brutalmente onesto.

STEP C — VALUTAZIONE FINALE:
Dopo il devil's advocate, la tua decisione regge o cambia?
Quanto pesi i rischi identificati (1-10)?

STEP D — DECISIONE DEFINITIVA:
Considerando tutto, qual è la tua decisione finale?

Rispondi SOLO con questo JSON (senza markdown, senza testo extra):
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": <numero 0-100>,
  "sl": <prezzo stop loss>,
  "tp": <prezzo take profit>,
  "reasoning": "<motivazione principale in 2-3 frasi>",
  "devil_advocate": "<i 2 rischi principali che hai considerato>",
  "initial_decision": "BUY" | "SELL" | "HOLD",
  "decision_changed_after_review": true | false,
  "market_regime": "trending" | "ranging" | "volatile",
  "technical_score": <0-100>,
  "fundamental_score": <0-100>
}}
"""

    resp = _call_api([{"role": "user", "content": prompt}], max_tokens=800)
    raw  = _extract_text(resp).strip()

    # Pulizia JSON (rimuovi eventuali backtick)
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
        log.info(f"  [Stadio 3] Decisione: {result.get('decision')} "
                 f"| Confidenza: {result.get('confidence')}% "
                 f"| Changed: {result.get('decision_changed_after_review')}")
        return result
    except json.JSONDecodeError as e:
        log.error(f"  [Stadio 3] JSON parse error: {e}\nRaw: {raw[:200]}")
        return {
            "decision": "HOLD",
            "confidence": 0,
            "sl": tech["atr_sl"],
            "tp": tech["atr_tp"],
            "reasoning": "Errore nel parsing della risposta AI — HOLD per sicurezza",
            "devil_advocate": "N/A",
            "initial_decision": "HOLD",
            "decision_changed_after_review": False,
            "market_regime": "unknown",
            "technical_score": 0,
            "fundamental_score": 0,
        }


# ════════════════════════════════════════════════════════════════
#  ENTRY POINT PRINCIPALE
# ════════════════════════════════════════════════════════════════
def analyze(tech_summary: dict) -> dict:
    """
    Esegue l'analisi completa a 3 stadi e restituisce la decisione.
    Usare questo metodo dal bot principale.
    """
    log.info("🧠 Avvio analisi Claude (3 stadi)...")

    # Stadio 1: tecnica
    tech_brief = stage1_technical(tech_summary)

    # Stadio 2: news + macro (con web search)
    news_brief = stage2_news(tech_brief)

    # Stadio 3: decisione + devil's advocate
    decision = stage3_decision(tech_brief, news_brief, tech_summary)

    # Aggiungi i brief alla risposta per il log
    decision["tech_brief"]  = tech_brief
    decision["news_brief"]  = news_brief

    # Applica soglia minima confidenza
    if decision.get("confidence", 0) < MIN_CONFIDENCE:
        log.info(f"  ⚠️  Confidenza {decision['confidence']}% < soglia {MIN_CONFIDENCE}% → HOLD forzato")
        decision["decision"]  = "HOLD"
        decision["reasoning"] = (f"Confidenza insufficiente ({decision['confidence']}% < {MIN_CONFIDENCE}%). "
                                 + decision.get("reasoning", ""))

    return decision
