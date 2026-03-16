/**
 * NEWBOTMODAL — form per creare un nuovo bot
 * Mostra tutte le strategie disponibili con descrizione, badge tipo e parametri default.
 */

import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GlowCard, Label } from './ui'

const SYMBOL_PRESETS = [
  { symbol: 'EURUSD', base: 'EUR', quote: 'USD', cb_base: 'BCE (Banca Centrale Europea)', cb_quote: 'Federal Reserve (Fed)' },
  { symbol: 'GBPUSD', base: 'GBP', quote: 'USD', cb_base: 'Bank of England',              cb_quote: 'Federal Reserve (Fed)' },
  { symbol: 'USDJPY', base: 'USD', quote: 'JPY', cb_base: 'Federal Reserve (Fed)',         cb_quote: 'Bank of Japan'         },
  { symbol: 'XAUUSD', base: 'Gold', quote: 'USD', cb_base: '',                             cb_quote: 'Federal Reserve (Fed)' },
]

// ── Tutte le strategie disponibili ────────────────────────────────
const STRATEGIES = [
  {
    value:       'ema_rsi_ai_main',
    label:       'Main AI — "Perfetta"',
    badge:       'AI MAIN',
    badgeColor:  'bg-purple-500/20 text-purple-300 border-purple-500/30',
    cardColor:   'border-purple-500/30 bg-purple-500/5',
    description: 'Setup altissima qualità. Web search sempre attivo. ADX≥30, H4 richiesto, convergenza tecnico+macro obbligatoria. R/R≥2.3.',
    stats:       'ADX≥30 · conf≥78% · SL×1.5 · TP×3.5',
    aiCost:      '~$0.02/analisi',
    defaultParams: {},
  },
  {
    value:       'ema_rsi_ai',
    label:       'Standard AI — 3 stadi',
    badge:       'AI',
    badgeColor:  'bg-blue-500/20 text-blue-300 border-blue-500/30',
    cardColor:   'border-blue-500/30 bg-blue-500/5',
    description: 'Strategia bilanciata. Tecnico + macro + decisione Claude. Web search attivo se tech_score alto.',
    stats:       'ADX≥25 · conf≥70% · SL×1.2 · TP×2.5',
    aiCost:      '~$0.01/analisi',
    defaultParams: {},
  },
  {
    value:       'ema_rsi_ai_scalp',
    label:       'Scalping AI — Veloce',
    badge:       'AI SCALP',
    badgeColor:  'bg-amber-500/20 text-amber-300 border-amber-500/30',
    cardColor:   'border-amber-500/30 bg-amber-500/5',
    description: 'Trade rapidi e frequenti. Solo Stage1+Stage3 (no web search). Stop stretto, target vicino.',
    stats:       'ADX≥20 · conf≥58% · SL×0.8 · TP×1.8',
    aiCost:      '~$0.002/analisi',
    defaultParams: {},
  },
  {
    value:       'ema_rsi_manual',
    label:       'Manuale — Regole pure',
    badge:       'MANUAL',
    badgeColor:  'bg-sky-500/20 text-sky-300 border-sky-500/30',
    cardColor:   'border-sky-500/30 bg-sky-500/5',
    description: 'Nessuna AI, zero costi API. Regole EMA+RSI+ADX configurabili. Parametri completamente personalizzabili.',
    stats:       'ADX≥25 · conf fisso · no Claude',
    aiCost:      '$0 (no API)',
    defaultParams: {
      rsi_bull_min:  50,
      rsi_bear_max:  50,
      adx_min:       25,
      confidence:    70,
      require_h4:    true,
      rsi_exit_high: 75,
      rsi_exit_low:  25,
    },
  },
]

const STRATEGY_MAP = Object.fromEntries(STRATEGIES.map(s => [s.value, s]))

function slugify(symbol, strategy) {
  const suffix = {
    ema_rsi_ai_main:  'main',
    ema_rsi_ai:       'ai',
    ema_rsi_ai_scalp: 'scalp',
    ema_rsi_manual:   'man',
  }[strategy] ?? strategy.slice(-3)
  return `${symbol.toLowerCase()}_${suffix}`
}

export default function NewBotModal({ onClose, onCreate }) {
  const [botId,       setBotId]       = useState('')
  const [symbol,      setSymbol]      = useState('EURUSD')
  const [strategy,    setStrategy]    = useState('ema_rsi_ai_main')
  const [paramsJson,  setParamsJson]  = useState('{}')
  const [paramsError, setParamsError] = useState('')
  const [loading,     setLoading]     = useState(false)
  const [error,       setError]       = useState('')
  const [botIdTouched, setBotIdTouched] = useState(false)

  const preset  = SYMBOL_PRESETS.find(p => p.symbol === symbol) ?? SYMBOL_PRESETS[0]
  const stratDef = STRATEGY_MAP[strategy]

  const autoId = slugify(symbol, strategy)

  const handleSymbolChange = (s) => {
    setSymbol(s)
    if (!botIdTouched) setBotId(slugify(s, strategy))
  }

  const handleStrategyChange = (s) => {
    setStrategy(s)
    const def = STRATEGY_MAP[s]?.defaultParams ?? {}
    const hasParams = Object.keys(def).length > 0
    setParamsJson(hasParams ? JSON.stringify(def, null, 2) : '{}')
    setParamsError('')
    if (!botIdTouched) setBotId(slugify(symbol, s))
  }

  const handleBotIdChange = (v) => {
    setBotId(v)
    setBotIdTouched(v !== '' && v !== autoId)
  }

  const handleParamsChange = (raw) => {
    setParamsJson(raw)
    try { JSON.parse(raw); setParamsError('') }
    catch { setParamsError('JSON non valido') }
  }

  const handleSubmit = async () => {
    const id = botId.trim() || autoId
    if (!id) { setError('Bot ID richiesto'); return }
    if (!/^[a-zA-Z0-9_-]+$/.test(id)) { setError('Bot ID: solo lettere, numeri, _ e -'); return }
    if (paramsError) { setError('Correggi i parametri JSON prima di salvare'); return }
    let params = {}
    try { params = JSON.parse(paramsJson) } catch { setError('JSON parametri non valido'); return }

    setLoading(true)
    setError('')
    try {
      await onCreate({
        bot_id:             id,
        symbol:             preset.symbol,
        symbol_base:        preset.base,
        symbol_quote:       preset.quote,
        central_bank_base:  preset.cb_base,
        central_bank_quote: preset.cb_quote,
        strategy,
        params,
      })
      onClose()
    } catch (e) {
      setError(e.message ?? 'Errore creazione bot')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      >
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.95 }}
          animate={{ opacity: 1, y: 0,  scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          onClick={e => e.stopPropagation()}
          className="w-full max-w-lg max-h-[90vh] overflow-y-auto"
        >
          <GlowCard glow="blue" className="space-y-5">

            {/* Header */}
            <div className="flex items-center justify-between">
              <Label>Nuovo Bot</Label>
              <button onClick={onClose} className="text-terminal-muted hover:text-white text-lg leading-none">×</button>
            </div>

            {/* Simbolo */}
            <div>
              <div className="text-[10px] text-terminal-muted uppercase tracking-wider mb-2">Simbolo</div>
              <div className="grid grid-cols-4 gap-2">
                {SYMBOL_PRESETS.map(p => (
                  <button key={p.symbol} onClick={() => handleSymbolChange(p.symbol)}
                    className={`py-2 text-sm font-mono rounded-lg border transition-colors ${
                      symbol === p.symbol
                        ? 'bg-blue-500/20 border-blue-500/50 text-blue-400'
                        : 'bg-terminal-bg border-terminal-border text-terminal-muted hover:border-blue-500/30'
                    }`}>
                    {p.symbol}
                  </button>
                ))}
              </div>
              <div className="text-[9px] text-terminal-muted mt-1 font-mono">
                {preset.cb_base && `${preset.cb_base} / `}{preset.cb_quote}
              </div>
            </div>

            {/* Strategia — card selector */}
            <div>
              <div className="text-[10px] text-terminal-muted uppercase tracking-wider mb-2">Strategia</div>
              <div className="space-y-2">
                {STRATEGIES.map(opt => (
                  <button key={opt.value} onClick={() => handleStrategyChange(opt.value)}
                    className={`w-full text-left rounded-lg border p-3 transition-all ${
                      strategy === opt.value
                        ? `${opt.cardColor} border-opacity-60`
                        : 'bg-terminal-bg border-terminal-border hover:border-gray-500'
                    }`}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className={`text-[9px] px-1.5 py-0.5 rounded border font-mono font-bold ${opt.badgeColor}`}>
                          {opt.badge}
                        </span>
                        <span className={`text-[11px] font-mono font-bold ${strategy === opt.value ? 'text-white' : 'text-terminal-muted'}`}>
                          {opt.label}
                        </span>
                      </div>
                      <span className="text-[9px] font-mono text-terminal-muted">{opt.aiCost}</span>
                    </div>
                    <div className="text-[10px] text-terminal-muted leading-relaxed">{opt.description}</div>
                    <div className={`text-[9px] font-mono mt-1 ${strategy === opt.value ? 'text-terminal-muted' : 'text-terminal-muted/50'}`}>
                      {opt.stats}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Bot ID */}
            <div>
              <div className="text-[10px] text-terminal-muted uppercase tracking-wider mb-2">
                Bot ID
                <span className="ml-2 normal-case text-terminal-muted/60">
                  (auto: <span className="text-blue-400/70">{autoId}</span>)
                </span>
              </div>
              <input
                value={botId}
                onChange={e => handleBotIdChange(e.target.value)}
                placeholder={autoId}
                className="w-full bg-terminal-bg border border-terminal-border rounded-lg px-3 py-2
                  text-sm font-mono text-white placeholder-terminal-muted/40
                  focus:outline-none focus:border-blue-500/60"
              />
              <div className="text-[9px] text-terminal-muted mt-1">Lascia vuoto per usare il nome automatico.</div>
            </div>

            {/* Parametri — solo per strategie con default non vuoti, o se l'utente vuole override */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-[10px] text-terminal-muted uppercase tracking-wider">
                  Parametri strategia (JSON)
                </div>
                {Object.keys(stratDef?.defaultParams ?? {}).length > 0 && (
                  <span className="text-[9px] text-green-400/70 font-mono">default precompilati</span>
                )}
              </div>
              <textarea
                value={paramsJson}
                onChange={e => handleParamsChange(e.target.value)}
                rows={Object.keys(stratDef?.defaultParams ?? {}).length > 0 ? 8 : 2}
                className={`w-full bg-terminal-bg border rounded-lg px-3 py-2
                  text-[11px] font-mono text-white resize-none
                  focus:outline-none ${paramsError ? 'border-red-500/60' : 'border-terminal-border focus:border-blue-500/60'}`}
              />
              {paramsError && (
                <div className="text-[10px] text-red-400 mt-1 font-mono">{paramsError}</div>
              )}
              {!paramsError && stratDef && (
                <div className="text-[9px] text-terminal-muted mt-1">
                  {strategy.startsWith('ema_rsi_ai')
                    ? 'Override opzionali: min_confidence, adx_min, sl_mult, tp_mult, …'
                    : 'Modifica i valori sopra per personalizzare la strategia.'}
                </div>
              )}
            </div>

            {error && (
              <div className="text-[11px] text-red-400 font-mono bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <div className="flex gap-2 pt-1">
              <button onClick={onClose}
                className="flex-1 py-2 text-sm font-mono rounded-lg
                  bg-terminal-bg border border-terminal-border text-terminal-muted
                  hover:border-blue-500/30 transition-colors">
                Annulla
              </button>
              <button onClick={handleSubmit} disabled={loading}
                className="flex-1 py-2 text-sm font-mono rounded-lg
                  bg-blue-500/15 border border-blue-500/40 text-blue-400
                  hover:bg-blue-500/25 transition-colors disabled:opacity-50">
                {loading ? '…' : 'Crea Bot'}
              </button>
            </div>

          </GlowCard>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
