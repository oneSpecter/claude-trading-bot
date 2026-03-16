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
    Ora ritorna (brief, fundamental_score, convergence) per alimentare stage3.

  Stadio 3 — DECISIONE FINALE + DEVIL'S ADVOCATE
    Claude prende una decisione, poi la sfida attivamente cercando
    i motivi per cui potrebbe sbagliarsi. Se regge → trade. Se no → HOLD.

Ottimizzazioni costi:
  - Prompt caching sul system prompt (cache_control: ephemeral) → -70% token fissi
  - Gate stage1→stage2: se technical_score < WEB_SEARCH_MIN_SCORE → skip stage2
  - Web search gestita server-side (nessun loop manuale di tool_result)

Cambiamenti rispetto alla versione precedente:
  - stage2_news ora ritorna tuple[str, int, str] invece di str
    → (news_brief, fundamental_score, convergence)
  - stage3_decision riceve i nuovi parametri fundamental_score e convergence
  - analyze() aggiornato di conseguenza — nessuna modifica necessaria esternamente
"""

import json
import logging
import os
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
_bot_id    = "default"


def init(base_dir, bot_id: str = "default"):
    """
    Imposta la directory costi e il bot_id corrente.
    Chiamato da bot.py all'avvio con il BOT_DIR specifico del bot.
    """
    global COSTS_FILE, _bot_id
    from pathlib import Path
    COSTS_FILE = str(Path(base_dir) / "api_costs.json")
    _bot_id    = bot_id


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
        "bot_id":        _bot_id,
        "input_tokens":  inp,
        "output_tokens": out,
        "cache_read":    c_read,
        "cache_write":   c_write,
        "web_search":    web_search,
        "cost_usd":      round(cost, 6),
    })
    data["calls"] = data["calls"][-1000:]
    tmp = str(costs_path) + ".tmp"
    Path(tmp).write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
    os.replace(tmp, costs_path)
    log.debug(f"  💰 {stage}: ${cost:.5f} ({inp}in/{out}out/{c_read}cached)")
    return cost


# ── Tool: web_search (server-side — Anthropic esegue le ricerche) ─
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
}

# ── System prompt con prompt caching ────────────────────────────
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


def _call_api(messages: list, tools: list = None, max_tokens: int = 1500,
              timeout: int = 60) -> dict:
    """Chiama l'API Claude con prompt caching abilitato."""
    payload = {
        "model":      CLAUDE_MODEL,
        "max_tokens": max_tokens,
        "system":     SYSTEM_PROMPT_CACHED,
        "messages":   messages,
    }
    if tools:
        payload["tools"] = tools

    resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _split_json_output(raw: str) -> tuple[str, dict | None]:
    """
    Splitta la risposta Claude sul separatore ---JSON_OUTPUT--- .
    Ritorna (brief_text, parsed_dict). Se il separatore manca o il JSON è invalido,
    ritorna (raw, None).
    """
    if "---JSON_OUTPUT---" not in raw:
        return raw, None
    brief, json_part = raw.split("---JSON_OUTPUT---", 1)
    try:
        return brief.strip(), json.loads(json_part.strip())
    except (json.JSONDecodeError, ValueError):
        return brief.strip(), None


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
def stage1_technical(tech: dict) -> tuple[str, int, str]:
    """
    Claude analizza il setup tecnico.
    Ritorna (brief: str, technical_score: int 0-100, bias: str).
    Il score determina se vale la pena chiamare stage2 (web search).
    Il bias viene propagato a stage3 per cross-check.
    """
    log.info("  [Stadio 1] Analisi tecnica...")

    sr        = tech["support_resistance"]
    patterns  = ", ".join(tech["candlestick_patterns"])
    cross     = tech["cross_signal"]
    cross_str = f"{cross[0]} rilevato su candela {cross[1]}" if cross else "Nessun crossover recente"
    adx_desc  = f"{tech['adx']} ({tech['adx_trend']}) | +DI={tech['adx_plus']} -DI={tech['adx_minus']}"
    h4_bias   = tech.get("h4_bias", "N/A")

    prompt = f"""Analizza questo setup tecnico su {SYMBOL} (timeframe H1) e fornisci un brief professionale.

═══ DATI DI MERCATO ═══
Prezzo attuale:     {tech['price']}
EMA 9:              {tech['ema_fast']}
EMA 21:             {tech['ema_slow']}
Trend EMA:          {tech['ema_trend']}
Crossover:          {cross_str}

RSI (14):           {tech['rsi']}
MACD:               {tech['macd']} | Signal: {tech['macd_signal']} | Hist: {tech['macd_hist']}
MACD bias:          {tech['macd_bias']}

ATR (14):           {tech['atr']}
ADX (14):           {adx_desc}
Bias H4:            {h4_bias} (trend principale su timeframe superiore)
Bollinger:          {tech['bb_position']}
  Upper:            {tech['bb_upper']}
  Lower:            {tech['bb_lower']}

Momentum (10):      {tech['momentum_10']}

═══ LIVELLI CHIAVE ═══
Pivot:   {sr['pivot']}
R1: {sr['r1']}  R2: {sr['r2']}
S1: {sr['s1']}  S2: {sr['s2']}
Massimi recenti: {sr['recent_highs']}
Minimi recenti:  {sr['recent_lows']}

═══ PATTERN CANDLESTICK ═══
{patterns if patterns else "Nessun pattern rilevante"}

═══ ULTIME 10 CANDELE ═══
{tech['last_10_candles']}

═══ LIVELLI SL/TP SUGGERITI (ATR-based) ═══
Per LONG:  SL={tech['atr_sl']}  TP={tech['atr_tp']}
Per SHORT: SL={tech['atr_sl_short']}  TP={tech['atr_tp_short']}

Scrivi un brief tecnico professionale (massimo 200 parole) coprendo:
1. Bias direzionale tecnico (rialzista/ribassista/neutro) e solidità del setup
2. Forza del trend (ADX) e rischio di falso segnale
3. Livelli critici da monitorare (i 2-3 supporti/resistenze più rilevanti)
4. Qualità del setup (forte/medio/debole) con motivazione sintetica
5. Eventuali segnali contraddittori o warning importanti

Dopo il brief, inserisci esattamente questo separatore seguito dal JSON:
---JSON_OUTPUT---
{{"score": <intero 0-100>, "setup_quality": "strong"|"medium"|"weak", "bias": "bullish"|"bearish"|"neutral"}}

Nessun testo dopo il JSON."""

    resp  = _call_api([{"role": "user", "content": prompt}], max_tokens=650)
    _track_cost(resp, "stage1")
    raw   = _extract_text(resp)

    brief, data = _split_json_output(raw)
    if data is None:
        log.warning("  [Stadio 1] Separatore ---JSON_OUTPUT--- non trovato, uso default.")
        brief = raw
    score         = int(data.get("score", 50))         if data else 50
    setup_quality = data.get("setup_quality", "medium") if data else "medium"
    bias          = data.get("bias", "neutral")         if data else "neutral"

    log.info(f"  [Stadio 1] Score={score} ({setup_quality}) | Bias={bias} | Brief: {brief[:80]}...")
    return brief, score, bias


# ════════════════════════════════════════════════════════════════
#  STADIO 2 — NOTIZIE & GEOPOLITICA (web search server-side)
# ════════════════════════════════════════════════════════════════
def stage2_news(tech_brief: str, tech_bias: str) -> tuple[str, int, str]:
    """
    Claude cerca autonomamente notizie rilevanti tramite web search.

    NOTA: ora ritorna una tupla (news_brief, fundamental_score, convergence)
    invece di una semplice stringa, per alimentare la logica di stage3.

    - news_brief:        testo dell'analisi fondamentale
    - fundamental_score: 0-100, forza del segnale fondamentale
    - convergence:       "aligned" | "divergent" | "neutral"
                         rispetto al bias tecnico di stage1
    """
    log.info("  [Stadio 2] Ricerca notizie e contesto macro (web search)...")

    today = datetime.now(timezone.utc).strftime("%d %B %Y")

    prompt = f"""Today is {today}. You have the following technical brief on {SYMBOL_BASE}/{SYMBOL_QUOTE}:

{tech_brief}

Technical bias from stage 1: {tech_bias}

Search the web IN ENGLISH for up-to-date information. Prioritize in this order:

[PRIORITY 1 — CRITICAL]
- Recent or imminent central bank decisions/communications: {CENTRAL_BANK_BASE} and {CENTRAL_BANK_QUOTE}
- Key macro data released in the last 48h or due in the next 24h:
  CPI, NFP, GDP, PMI, PPI, retail sales, unemployment for {SYMBOL_BASE} and {SYMBOL_QUOTE}

[PRIORITY 2 — HIGH]
- Global risk sentiment in the last 24h (risk-on vs risk-off signals)
- Major geopolitical events impacting forex markets (conflicts, sanctions, elections)

[PRIORITY 3 — MEDIUM]
- Specific {SYMBOL_BASE}/{SYMBOL_QUOTE} news from the last 48h
- Speculative positioning on {SYMBOL_BASE} and {SYMBOL_QUOTE} (COT report, analyst views)

After completing your research, write a fundamental brief (maximum 200 words) in Italian covering:
- Fundamental bias (pro-{SYMBOL_BASE} / pro-{SYMBOL_QUOTE} / neutral) with key drivers
- Main catalysts currently in play
- Risks to monitor in the next 24-48h
- Whether the fundamental picture aligns or diverges from the technical bias ({tech_bias})

Then insert exactly this separator followed by the JSON:
---JSON_OUTPUT---
{{"fundamental_score": <integer 0-100>, "bias": "pro-{SYMBOL_BASE}"|"pro-{SYMBOL_QUOTE}"|"neutral", "convergence_with_technical": "aligned"|"divergent"|"neutral"}}

No text after the JSON."""

    resp       = _call_api([{"role": "user", "content": prompt}],
                           tools=[WEB_SEARCH_TOOL], max_tokens=2000, timeout=120)
    _track_cost(resp, "stage2", web_search=True)
    raw        = _extract_text(resp)

    news_brief, data = _split_json_output(raw)
    if data is None:
        log.warning("  [Stadio 2] Separatore ---JSON_OUTPUT--- non trovato, uso default.")
        news_brief = raw
    fundamental_score = int(data.get("fundamental_score", 50))      if data else 50
    convergence       = data.get("convergence_with_technical", "neutral") if data else "neutral"

    if not news_brief:
        log.warning("  [Stadio 2] Nessun testo estratto dalla risposta web search.")
        news_brief = "Analisi macro non disponibile — risposta web search vuota."

    log.info(
        f"  [Stadio 2] Fund.score={fundamental_score} | Convergence={convergence} | "
        f"Brief: {news_brief[:100]}..."
    )
    return news_brief, fundamental_score, convergence


# ════════════════════════════════════════════════════════════════
#  STADIO 3 — DECISIONE FINALE + DEVIL'S ADVOCATE
# ════════════════════════════════════════════════════════════════
def stage3_decision(
    tech_brief:        str,
    news_brief:        str,
    tech:              dict,
    fundamental_score: int  = 50,
    convergence:       str  = "neutral",
) -> dict:
    """
    Claude prende la decisione finale, poi fa il devil's advocate —
    sfida attivamente la sua stessa analisi per validarla.

    I nuovi parametri fundamental_score e convergence arrivano da stage2
    e permettono a Claude di applicare regole esplicite di ponderazione.
    """
    log.info("  [Stadio 3] Decisione finale + devil's advocate...")

    # Calcolo R/R atteso per includere nel prompt (info contestuale)
    try:
        price       = float(tech['price'])
        atr_sl      = float(tech['atr_sl'])
        atr_tp      = float(tech['atr_tp'])
        atr_sl_s    = float(tech['atr_sl_short'])
        atr_tp_s    = float(tech['atr_tp_short'])
        rr_long     = round(abs(atr_tp - price) / abs(price - atr_sl), 2) if abs(price - atr_sl) > 0 else 0
        rr_short    = round(abs(price - atr_tp_s) / abs(atr_sl_s - price), 2) if abs(atr_sl_s - price) > 0 else 0
    except (ValueError, ZeroDivisionError):
        rr_long = rr_short = 0

    prompt = f"""Hai completato l'analisi su {SYMBOL_BASE}/{SYMBOL_QUOTE}. Prendi la decisione finale.

═══ BRIEF TECNICO ═══
{tech_brief}

═══ BRIEF FONDAMENTALE/MACRO ═══
{news_brief}

═══ PARAMETRI OPERATIVI ═══
Prezzo attuale: {tech['price']}
ADX: {tech['adx']} ({tech['adx_trend']})
Per LONG:  SL={tech['atr_sl']}  TP={tech['atr_tp']}  R/R stimato={rr_long}
Per SHORT: SL={tech['atr_sl_short']}  TP={tech['atr_tp_short']}  R/R stimato={rr_short}

═══ METADATI ANALISI ═══
Technical score (stage1):    {tech.get('technical_score_s1', 50)}/100
Fundamental score (stage2):  {fundamental_score}/100
Convergenza tecnico/fondamentale: {convergence}

═══ REGOLE DI DECISIONE OBBLIGATORIE ═══
Applica queste regole prima di formulare la decisione:

R1 — CONVERGENZA: Se technical e fundamental sono "divergent" E la differenza
     tra i due score è > 30 punti → abbassa la confidence di 20 punti.
     Segnali opposti indicano incertezza strutturale.

R2 — RISK/REWARD: Se il R/R stimato per la direzione che stai considerando
     è < 1.5 → considera seriamente HOLD. Un trade con R/R < 1.5 non
     giustifica il rischio a meno di una confluenza eccezionale.

R3 — TREND DEBOLE: Se ADX < 20 → il mercato è in ranging. Abbassa confidence
     di 15 punti e privilegia HOLD su segnali non chiari.

═══ PROCESSO DECISIONALE ═══

STEP A — DECISIONE INIZIALE:
Sulla base di tutta l'analisi e dopo aver applicato le regole R1-R3,
qual è la tua raccomandazione? (BUY / SELL / HOLD)

STEP B — DEVIL'S ADVOCATE:
Assumi la posizione OPPOSTA. Elenca ESATTAMENTE 2 rischi — né più né meno —
che potrebbero invalidare la tua decisione. Sii brutalmente onesto.

STEP C — VALUTAZIONE FINALE:
Dopo il devil's advocate, la decisione regge o cambia?
Hai applicato correttamente le regole R1-R3?

STEP D — OUTPUT:
Fornisci la decisione definitiva nel JSON qui sotto.

Dopo il ragionamento, inserisci esattamente questo separatore seguito dal JSON:
<output>
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": <intero 0-100>,
  "sl": <prezzo stop loss>,
  "tp": <prezzo take profit>,
  "reasoning": "<motivazione principale in 2-3 frasi>",
  "devil_advocate": "<i 2 rischi esatti che hai considerato, separati da ' | '>",
  "initial_decision": "BUY" | "SELL" | "HOLD",
  "decision_changed_after_review": true | false,
  "market_regime": "trending" | "ranging" | "volatile",
  "technical_score": <0-100>,
  "fundamental_score": <0-100>,
  "convergence": "aligned" | "divergent" | "neutral",
  "rr_ratio": <R/R effettivo della direzione scelta, float>
}}
</output>"""

    # 500 token bastano per l'output JSON compatto quando il segnale è già forte (score >= 80)
    tech_s1 = tech.get("technical_score_s1", 50)
    max_tok  = 500 if tech_s1 >= 80 else 900

    resp = _call_api([{"role": "user", "content": prompt}], max_tokens=max_tok)
    _track_cost(resp, "stage3")
    raw  = _extract_text(resp).strip()

    # Parsing robusto con tag <output>
    json_str = raw
    if "<output>" in raw and "</output>" in raw:
        start    = raw.index("<output>") + len("<output>")
        end      = raw.index("</output>")
        json_str = raw[start:end].strip()
    else:
        # Fallback: prova a strippare backtick markdown
        log.warning("  [Stadio 3] Tag <output> non trovato, tentativo fallback.")
        json_str = raw.replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(json_str)
        log.info(
            f"  [Stadio 3] Decisione: {result.get('decision')} "
            f"| Confidenza: {result.get('confidence')}% "
            f"| R/R: {result.get('rr_ratio')} "
            f"| Changed: {result.get('decision_changed_after_review')}"
        )
        return result
    except json.JSONDecodeError as e:
        log.error(f"  [Stadio 3] JSON parse error: {e}\nRaw: {raw[:300]}")
        return {
            "decision":                      "HOLD",
            "confidence":                    0,
            "sl":                            tech["atr_sl"],
            "tp":                            tech["atr_tp"],
            "reasoning":                     "Errore nel parsing della risposta AI — HOLD per sicurezza",
            "devil_advocate":                "N/A",
            "initial_decision":              "HOLD",
            "decision_changed_after_review": False,
            "market_regime":                 "unknown",
            "technical_score":               0,
            "fundamental_score":             fundamental_score,
            "convergence":                   convergence,
            "rr_ratio":                      0,
        }


# ════════════════════════════════════════════════════════════════
#  EXIT CHECK — gestione attiva delle posizioni aperte
# ════════════════════════════════════════════════════════════════
def check_exit(position: dict, current_price: float, tech: dict, *,
               time_limit_hit: bool = False) -> dict:
    """
    Chiede a Claude se chiudere anticipatamente una posizione aperta.
    Single-stage economico (~$0.002/chiamata con Haiku).

    time_limit_hit=True: la durata massima è scaduta e il trade è in profitto o
    perdita contenuta — Claude deve valutare se è il momento giusto per uscire
    oppure se conviene aspettare ancora (es. trend ancora valido, TP vicino).

    Ritorna:
      {"action": "HOLD" | "CLOSE", "reasoning": str, "confidence": int}
    """
    direction = position.get("direction", "BUY")
    entry     = float(position.get("price", 0))
    sl        = float(position.get("sl", 0))
    tp        = float(position.get("tp", 0))
    ticket    = position.get("ticket", "?")

    pips = round(
        (current_price - entry if direction == "BUY" else entry - current_price) * 10_000, 1
    )
    tp_dist = abs(tp - entry) if tp and entry else 1
    sl_dist = abs(entry - sl) if sl and entry else 1
    tp_pct  = round(abs(current_price - entry) / tp_dist * 100, 1) if tp_dist > 0 else 0
    sl_pct  = round(abs(current_price - entry) / sl_dist * 100, 1) if sl_dist > 0 else 0

    patterns = ", ".join(tech.get("candlestick_patterns", []))

    time_ctx = ""
    if time_limit_hit:
        time_ctx = f"""
⚠️ CONTESTO SPECIALE — SCADENZA DURATA MASSIMA:
Il trade ha raggiunto la durata massima configurata. Sei stato chiamato per decidere se
è opportuno chiudere ora (P&L attuale: {pips:+.1f} pips) oppure attendere ancora.
- Se il trend è ancora valido e il TP è raggiungibile → HOLD (meglio aspettare)
- Se il momentum è esaurito o il setup originale non è più valido → CLOSE
"""

    prompt = f"""Hai un trade aperto su {SYMBOL}. Valuta se chiuderlo anticipatamente.
{time_ctx}
TRADE APERTO:
Direzione: {direction} | Entrata: {entry} | Prezzo attuale: {current_price}
Stop Loss: {sl} | Take Profit: {tp}
P&L attuale: {pips:+.1f} pips | TP raggiunto: {tp_pct}% | Distanza SL percorsa: {sl_pct}%

CONTESTO TECNICO:
EMA trend: {tech.get('ema_trend')} | RSI: {tech.get('rsi')} | ADX: {tech.get('adx')} ({tech.get('adx_trend')})
MACD bias: {tech.get('macd_bias')} | Bias H4: {tech.get('h4_bias', 'N/A')}
Pattern: {patterns}

CRITERI DI USCITA ANTICIPATA (considera questi fattori):
- Il trend si è invertito contro la direzione del trade (EMA, MACD opposti)
- RSI in zona di esaurimento estrema (>78 per BUY, <22 per SELL)
- ADX < 20 — il trend si sta esaurendo
- P&L positivo (>30% del TP) + segnale di inversione → proteggi il profitto
- Pattern bearish/bullish avverso forte sull'ultima candela

CRITERI PER TENERE (HOLD):
- Trend confermato, indicatori allineati con la direzione
- Nessun segnale di inversione chiaro
- Trade in perdita senza segnali tecnici forti → lascia lavorare lo SL

Rispondi SOLO con JSON valido:
{{"action": "HOLD" | "CLOSE", "reasoning": "<motivazione in 1-2 frasi>", "confidence": <0-100>}}"""

    resp = _call_api([{"role": "user", "content": prompt}], max_tokens=150)
    _track_cost(resp, "exit_check")
    raw = _extract_text(resp)

    try:
        clean  = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        if result.get("action") not in ("HOLD", "CLOSE"):
            result["action"] = "HOLD"
        return result
    except json.JSONDecodeError:
        log.warning(f"  [Exit Check] JSON parse error per ticket {ticket} — HOLD per sicurezza")
        return {"action": "HOLD", "reasoning": "Parse error — default HOLD", "confidence": 0}


# ════════════════════════════════════════════════════════════════
#  ENTRY POINT PRINCIPALE
# ════════════════════════════════════════════════════════════════
def analyze(tech_summary: dict, *, min_confidence: int = None, web_search_min_score: int = None) -> dict:
    """
    Esegue l'analisi completa a 3 stadi e restituisce la decisione.

    I parametri keyword-only permettono di sovrascrivere le soglie da config.py
    a runtime (usati dalla pagina Impostazioni della dashboard).

    Ottimizzazioni costi:
      - Stage2 (web search) viene skippato se technical_score < WEB_SEARCH_MIN_SCORE
      - Prompt caching attivo su tutte e 3 le chiamate
    """
    _min_conf = MIN_CONFIDENCE       if min_confidence       is None else min_confidence
    _web_min  = WEB_SEARCH_MIN_SCORE if web_search_min_score is None else web_search_min_score

    log.info("🧠 Avvio analisi Claude (3 stadi)...")

    # ── Stadio 1: analisi tecnica + score + bias ─────────────────
    tech_brief, tech_score, tech_bias = stage1_technical(tech_summary)

    # Propaga il technical_score al dict per stage3
    tech_summary["technical_score_s1"] = tech_score

    # ── Gate stage1 → stage2: web search solo se vale ────────────
    if tech_score >= _web_min:
        news_brief, fundamental_score, convergence = stage2_news(tech_brief, tech_bias)
    else:
        log.info(
            f"  ⏭  Stage2 skippato — technical_score={tech_score} < {_web_min} "
            f"(setup marginale, risparmio web search)"
        )
        news_brief        = (
            f"Analisi macro non eseguita — setup tecnico marginale "
            f"(score: {tech_score}/{_web_min}). Decisione basata solo su analisi tecnica."
        )
        fundamental_score = 50
        convergence       = "neutral"

    # ── Stadio 3: decisione + devil's advocate ───────────────────
    decision = stage3_decision(
        tech_brief,
        news_brief,
        tech_summary,
        fundamental_score=fundamental_score,
        convergence=convergence,
    )

    # Aggiungi brief e metadati alla risposta per log e journal
    decision["tech_brief"]        = tech_brief
    decision["news_brief"]        = news_brief
    decision["tech_score_s1"]     = tech_score
    decision["technical_score"]   = tech_score   # usa sempre il valore calcolato in stage1
    decision["tech_bias_s1"]      = tech_bias
    decision["web_search_done"]   = tech_score >= _web_min

    # ── Enforce R3: ADX < 20 → riduzione confidence obbligatoria ─
    # Claude potrebbe ignorare la regola — la applichiamo in post-processing
    adx = float(tech_summary.get("adx", 25))
    if adx < 20 and decision.get("decision") != "HOLD":
        orig_conf    = decision.get("confidence", 0)
        enforced     = max(0, orig_conf - 15)
        if enforced != orig_conf:
            log.info(f"  [R3 enforced] ADX={adx:.1f} < 20 → confidence {orig_conf}% → {enforced}%")
            decision["confidence"] = enforced
            decision["reasoning"]  = f"[Trend debole ADX={adx:.0f}] " + decision.get("reasoning", "")

    # ── Soglia minima confidenza ─────────────────────────────────
    if decision.get("confidence", 0) < _min_conf:
        log.info(
            f"  ⚠️  Confidenza {decision['confidence']}% < soglia {_min_conf}% → HOLD forzato"
        )
        decision["decision"]  = "HOLD"
        decision["reasoning"] = (
            f"Confidenza insufficiente ({decision['confidence']}% < {_min_conf}%). "
            + decision.get("reasoning", "")
        )

    return decision