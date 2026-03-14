"""
CLAUDE AI ANALYST
-----------------
Cuore del bot. Sistema di autoprompting a 3 stadi:

  Stadio 1 — ANALISI TECNICA
    Claude analizza gli indicatori e restituisce un brief strutturato
    + un technical_score (0-100) per decidere se procedere con stage2.

  Stadio 2 — RICERCA NOTIZIE & GEOPOLITICA (web_search — solo se score >= soglia)
    Chiamata server-side: Anthropic esegue le ricerche autonomamente.
    Skippata se il setup tecnico è marginale → risparmio costi.

  Stadio 3 — DECISIONE FINALE + DEVIL'S ADVOCATE
    Claude prende una decisione, poi la sfida attivamente cercando
    i motivi per cui potrebbe sbagliarsi. Se regge → trade. Se no → HOLD.

Ottimizzazioni costi:
  - Prompt caching sul system prompt (cache_control: ephemeral) → -70% token fissi
  - Gate stage1→stage2: se technical_score < WEB_SEARCH_MIN_SCORE → skip stage2
  - Web search gestita server-side (nessun loop manuale di tool_result)
"""

import json
import logging
import requests
from datetime import datetime, timezone
from pathlib import Path
from config import (
    ANTHROPIC_API_KEY, CLAUDE_MODEL, SYMBOL, MIN_CONFIDENCE,
    SYMBOL_BASE, SYMBOL_QUOTE, CENTRAL_BANK_BASE, CENTRAL_BANK_QUOTE,
    WEB_SEARCH_MIN_SCORE,
)

log = logging.getLogger("ClaudeAnalyst")

API_URL = "https://api.anthropic.com/v1/messages"
HEADERS = {
    "x-api-key":          ANTHROPIC_API_KEY,
    "anthropic-version":  "2023-06-01",
    "anthropic-beta":     "prompt-caching-2024-07-31",
    "content-type":       "application/json",
}

# ── Costi API ───────────────────────────────────────────────────
COSTS_FILE = "api_costs.json"
PRICING = {
    "claude-haiku-4-5-20251001": {
        "input":       0.80 / 1_000_000,
        "output":      4.00 / 1_000_000,
        "cache_read":  0.08 / 1_000_000,
        "cache_write": 1.00 / 1_000_000,
    },
    "claude-sonnet-4-6": {
        "input":        3.00 / 1_000_000,
        "output":      15.00 / 1_000_000,
        "cache_read":   0.30 / 1_000_000,
        "cache_write":  3.75 / 1_000_000,
    },
}
WEB_SEARCH_COST = 0.01  # $0.01 per chiamata con web search attivo


def _track_cost(response: dict, stage: str, web_search: bool = False) -> float:
    """Registra il costo della chiamata API in api_costs.json."""
    usage   = response.get("usage", {})
    model   = response.get("model", CLAUDE_MODEL)
    p       = PRICING.get(model, PRICING["claude-haiku-4-5-20251001"])

    inp     = usage.get("input_tokens", 0)
    out     = usage.get("output_tokens", 0)
    c_read  = usage.get("cache_read_input_tokens", 0)
    c_write = usage.get("cache_creation_input_tokens", 0)
    billable = max(0, inp - c_read - c_write)

    cost = (
        billable * p["input"]  +
        out      * p["output"] +
        c_read   * p["cache_read"]  +
        c_write  * p["cache_write"] +
        (WEB_SEARCH_COST if web_search else 0)
    )

    costs_path = Path(COSTS_FILE)
    data = json.loads(costs_path.read_text("utf-8")) if costs_path.exists() else {
        "total_cost": 0.0, "total_calls": 0, "calls": []
    }
    data["total_cost"]  = round(data["total_cost"] + cost, 8)
    data["total_calls"] += 1
    data["calls"].append({
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "stage":         stage,
        "model":         model,
        "input_tokens":  inp,
        "output_tokens": out,
        "cache_read":    c_read,
        "cache_write":   c_write,
        "web_search":    web_search,
        "cost_usd":      round(cost, 6),
    })
    data["calls"] = data["calls"][-1000:]
    costs_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    log.debug(f"  💰 {stage}: ${cost:.5f} ({inp}in/{out}out/{c_read}cached)")
    return cost


# ── Tool: web_search (server-side — Anthropic esegue le ricerche) ─
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
}

# ── System prompt con prompt caching ────────────────────────────
# Formato lista per abilitare cache_control (risparmio ~70% token fissi)
SYSTEM_PROMPT_CACHED = [
    {
        "type": "text",
        "text": (
            f"Sei un trader forex professionale e analista di mercato con 20 anni di esperienza.\n"
            f"Il tuo compito è analizzare il mercato {SYMBOL_BASE}/{SYMBOL_QUOTE} "
            f"e fornire decisioni di trading precise e motivate.\n\n"
            f"Le tue analisi devono essere:\n"
            f"- Oggettive e basate su dati concreti\n"
            f"- Integrate tra analisi tecnica e fondamentale\n"
            f"- Consapevoli del contesto macro e geopolitico globale\n"
            f"- Calibrate sul rischio (non tradare in condizioni di incertezza estrema)\n\n"
            f"Quando non c'è un setup chiaro, la risposta corretta è HOLD — non forzare trade.\n"
            f"La tua priorità assoluta è la preservazione del capitale.\n\n"
            f"Rispondi SEMPRE e SOLO con JSON valido quando richiesto, "
            f"senza markdown, senza testo prima o dopo."
        ),
        "cache_control": {"type": "ephemeral"},
    }
]


def _call_api(messages: list, tools: list = None, max_tokens: int = 1500) -> dict:
    """Chiama l'API Claude con prompt caching abilitato."""
    payload = {
        "model":      CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system":     SYSTEM_PROMPT_CACHED,
        "messages":   messages,
    }
    if tools:
        payload["tools"] = tools

    resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def _extract_text(response: dict) -> str:
    """Estrae solo i blocchi di testo dalla risposta Claude."""
    return "\n".join(
        block["text"]
        for block in response.get("content", [])
        if block.get("type") == "text"
    ).strip()


# ════════════════════════════════════════════════════════════════
#  STADIO 1 — ANALISI TECNICA + SCORE
# ════════════════════════════════════════════════════════════════
def stage1_technical(tech: dict) -> tuple[str, int]:
    """
    Claude analizza il setup tecnico.
    Ritorna (brief: str, technical_score: int 0-100).
    Il score determina se vale la pena chiamare stage2 (web search).
    """
    log.info("  [Stadio 1] Analisi tecnica...")

    sr       = tech["support_resistance"]
    patterns = ", ".join(tech["candlestick_patterns"])
    cross    = tech["cross_signal"]
    cross_str = f"{cross[0]} rilevato su candela {cross[1]}" if cross else "Nessun crossover recente"
    adx_desc  = f"{tech['adx']} ({tech['adx_trend']}) | +DI={tech['adx_plus']} -DI={tech['adx_minus']}"
    h4_bias   = tech.get("h4_bias", "N/A")

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
ADX (14):          {adx_desc}
Bias H4:           {h4_bias} (trend principale su timeframe superiore)
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
2. Forza del trend (ADX) e rischio di falso segnale
3. Livelli critici da monitorare (supporti/resistenze più rilevanti)
4. Qualità del setup (forte/medio/debole) con spiegazione
5. Eventuali segnali contradditori o warning

Al termine, aggiungi ESATTAMENTE questa riga (nessun testo dopo):
SCORE:{{"score": <0-100>, "setup_quality": "strong"|"medium"|"weak"}}"""

    resp  = _call_api([{"role": "user", "content": prompt}], max_tokens=600)
    _track_cost(resp, "stage1")
    raw   = _extract_text(resp)

    # Estrai score dall'ultima riga SCORE:{...}
    score         = 50
    setup_quality = "medium"
    brief         = raw

    for line in reversed(raw.splitlines()):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                data          = json.loads(line[6:])
                score         = int(data.get("score", 50))
                setup_quality = data.get("setup_quality", "medium")
                brief         = raw[:raw.rfind("SCORE:")].strip()
            except (json.JSONDecodeError, ValueError):
                pass
            break

    log.info(f"  [Stadio 1] Score={score} ({setup_quality}) | Brief: {brief[:80]}...")
    return brief, score


# ════════════════════════════════════════════════════════════════
#  STADIO 2 — NOTIZIE & GEOPOLITICA (web search server-side)
# ════════════════════════════════════════════════════════════════
def stage2_news(tech_brief: str) -> str:
    """
    Claude cerca autonomamente notizie rilevanti tramite web search.
    Il tool web_search_20250305 è server-side: Anthropic esegue le ricerche
    automaticamente — nessun loop manuale necessario.
    """
    log.info("  [Stadio 2] Ricerca notizie e contesto macro (web search)...")

    today = datetime.now(timezone.utc).strftime("%d %B %Y")

    prompt = f"""Oggi è {today}. Hai già questo brief tecnico su {SYMBOL_BASE}/{SYMBOL_QUOTE}:

{tech_brief}

Ora devi arricchire l'analisi con il contesto fondamentale e geopolitico.
Esegui ricerche web per trovare informazioni AGGIORNATE su:

1. Notizie recenti su {SYMBOL_BASE}/{SYMBOL_QUOTE} (ultime 24-48 ore)
2. Decisioni o comunicazioni di {CENTRAL_BANK_BASE} e {CENTRAL_BANK_QUOTE}
3. Dati macro importanti: inflazione {SYMBOL_BASE}/{SYMBOL_QUOTE}, NFP, GDP, PMI
4. Tensioni geopolitiche che impattano i mercati (guerra, sanzioni, elezioni)
5. Sentiment di rischio globale (risk-on vs risk-off)
6. Posizionamento speculativo su {SYMBOL_BASE} e {SYMBOL_QUOTE}

Dopo le ricerche, scrivi un brief fondamentale di 150-200 parole con:
- Bias fondamentale (pro-{SYMBOL_BASE} / pro-{SYMBOL_QUOTE} / neutro)
- Catalizzatori principali in gioco
- Rischi da tenere presente
- Coerenza o divergenza con il setup tecnico"""

    resp       = _call_api([{"role": "user", "content": prompt}],
                           tools=[WEB_SEARCH_TOOL], max_tokens=2000)
    _track_cost(resp, "stage2", web_search=True)
    news_brief = _extract_text(resp)

    if not news_brief:
        log.warning("  [Stadio 2] Nessun testo estratto dalla risposta web search.")
        news_brief = "Analisi macro non disponibile — risposta web search vuota."

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

    prompt = f"""Hai completato l'analisi su {SYMBOL_BASE}/{SYMBOL_QUOTE}. Prendi la decisione finale.

═══ BRIEF TECNICO ═══
{tech_brief}

═══ BRIEF FONDAMENTALE/MACRO ═══
{news_brief}

═══ PARAMETRI OPERATIVI ═══
Prezzo attuale: {tech['price']}
ADX: {tech['adx']} ({tech['adx_trend']})
Per LONG:  SL={tech['atr_sl']}  TP={tech['atr_tp']}
Per SHORT: SL={tech['atr_sl_short']}  TP={tech['atr_tp_short']}

═══ PROCESSO DECISIONALE ═══

STEP A — DECISIONE INIZIALE:
Basandoti su tutta l'analisi, qual è la tua raccomandazione? (BUY / SELL / HOLD)

STEP B — DEVIL'S ADVOCATE:
Assumi la posizione OPPOSTA. Elenca i 3 motivi più forti per cui potresti sbagliarti.
Sii brutalmente onesto. Considera anche la forza del trend (ADX) e il rischio macro.

STEP C — VALUTAZIONE FINALE:
Dopo il devil's advocate, la decisione regge o cambia?

STEP D — DECISIONE DEFINITIVA:
Qual è la tua decisione finale considerando tutto?

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
}}"""

    resp = _call_api([{"role": "user", "content": prompt}], max_tokens=800)
    _track_cost(resp, "stage3")
    raw  = _extract_text(resp).strip().replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(raw)
        log.info(
            f"  [Stadio 3] Decisione: {result.get('decision')} "
            f"| Confidenza: {result.get('confidence')}% "
            f"| Changed: {result.get('decision_changed_after_review')}"
        )
        return result
    except json.JSONDecodeError as e:
        log.error(f"  [Stadio 3] JSON parse error: {e}\nRaw: {raw[:200]}")
        return {
            "decision":                   "HOLD",
            "confidence":                 0,
            "sl":                         tech["atr_sl"],
            "tp":                         tech["atr_tp"],
            "reasoning":                  "Errore nel parsing della risposta AI — HOLD per sicurezza",
            "devil_advocate":             "N/A",
            "initial_decision":           "HOLD",
            "decision_changed_after_review": False,
            "market_regime":              "unknown",
            "technical_score":            0,
            "fundamental_score":          0,
        }


# ════════════════════════════════════════════════════════════════
#  ENTRY POINT PRINCIPALE
# ════════════════════════════════════════════════════════════════
def analyze(tech_summary: dict) -> dict:
    """
    Esegue l'analisi completa a 3 stadi e restituisce la decisione.

    Ottimizzazione costi:
      - Stage2 (web search) viene skippato se technical_score < WEB_SEARCH_MIN_SCORE
      - Prompt caching attivo su tutte e 3 le chiamate
    """
    log.info("🧠 Avvio analisi Claude (3 stadi)...")

    # ── Stadio 1: analisi tecnica + score ────────────────────────
    tech_brief, tech_score = stage1_technical(tech_summary)

    # ── Gate stage1 → stage2: web search solo se vale ────────────
    if tech_score >= WEB_SEARCH_MIN_SCORE:
        news_brief = stage2_news(tech_brief)
    else:
        log.info(
            f"  ⏭  Stage2 skippato — technical_score={tech_score} < {WEB_SEARCH_MIN_SCORE} "
            f"(setup marginale, risparmio web search)"
        )
        news_brief = (
            f"Analisi macro non eseguita — setup tecnico marginale "
            f"(score: {tech_score}/100). Decisione basata solo su analisi tecnica."
        )

    # ── Stadio 3: decisione + devil's advocate ───────────────────
    decision = stage3_decision(tech_brief, news_brief, tech_summary)

    # Aggiungi brief e score alla risposta per log e journal
    decision["tech_brief"]   = tech_brief
    decision["news_brief"]   = news_brief
    decision["tech_score_s1"] = tech_score
    decision["web_search_done"] = tech_score >= WEB_SEARCH_MIN_SCORE

    # ── Soglia minima confidenza ─────────────────────────────────
    if decision.get("confidence", 0) < MIN_CONFIDENCE:
        log.info(
            f"  ⚠️  Confidenza {decision['confidence']}% < soglia {MIN_CONFIDENCE}% → HOLD forzato"
        )
        decision["decision"]  = "HOLD"
        decision["reasoning"] = (
            f"Confidenza insufficiente ({decision['confidence']}% < {MIN_CONFIDENCE}%). "
            + decision.get("reasoning", "")
        )

    return decision
