import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GlowCard, Label, Tooltip, InfoIcon } from './ui'

const MODES = {
  mock: {
    label:       'MOCK',
    emoji:       '🧪',
    color:       'text-sky-400',
    activeBg:    'bg-sky-500/15 border-sky-500/40',
    dotColor:    'bg-sky-400',
    glow:        'blue',
    description: 'Dati sintetici generati localmente. Nessuna connessione a MT5 richiesta. Ideale per testare il codice e la strategia senza rischi.',
    features: [
      'Dati OHLC generati artificialmente',
      'Nessuna connessione MT5 necessaria',
      'Nessun ordine inviato',
      'Sempre disponibile (anche offline)',
    ],
    config: { use_mock: true, dry_run: true },
  },
  watch: {
    label:       'WATCH',
    emoji:       '👁',
    color:       'text-amber-400',
    activeBg:    'bg-amber-500/15 border-amber-500/40',
    dotColor:    'bg-amber-400',
    glow:        'amber',
    description: 'Dati reali da MetaTrader 5. Il bot analizza il mercato con Claude AI e registra le decisioni, ma non apre ordini.',
    features: [
      'Dati EURUSD reali in tempo reale',
      'MT5 deve essere aperto e connesso',
      'Nessun ordine inviato',
      'Journal e statistiche attivi',
    ],
    config: { use_mock: false, dry_run: true },
  },
  trade: {
    label:       'TRADE',
    emoji:       '💹',
    color:       'text-green-400',
    activeBg:    'bg-green-500/15 border-green-500/40',
    dotColor:    'bg-green-400',
    glow:        'green',
    description: 'Dati reali MT5 + ordini reali sul conto demo. Risk management automatico all\'1% del capitale per trade.',
    features: [
      'Dati EURUSD reali in tempo reale',
      'Ordini reali su conto DEMO MT5',
      'Risk 1% del capitale per trade',
      'AI exit check ogni 5 minuti',
    ],
    config: { use_mock: false, dry_run: false },
  },
}

function currentModeKey(config) {
  if (config?.use_mock ?? true) return 'mock'
  if (config?.dry_run ?? true)  return 'watch'
  return 'trade'
}

export default function ModeControl({ config, onUpdate, botRunning, botId }) {
  // Per multi-bot usa /api/bots/{botId}/config, altrimenti legacy /api/config
  const configEndpoint = botId
    ? `/api/bots/${botId}/config`
    : '/api/config'
  const [showConfirm, setShowConfirm] = useState(null)
  const [loading,     setLoading]     = useState(false)

  const modeKey = currentModeKey(config)
  const mode    = MODES[modeKey]

  const handleSelect = (newKey) => {
    if (newKey === modeKey || loading) return
    const newCfg     = MODES[newKey].config
    const isTradeSwitch = newKey === 'trade'
    const dataSourceChanges = newCfg.use_mock !== MODES[modeKey].config.use_mock

    // Conferma sempre per TRADE; conferma se bot running e cambia la fonte dati
    if (isTradeSwitch || (botRunning && dataSourceChanges)) {
      setShowConfirm(newKey)
    } else {
      applyMode(newKey)
    }
  }

  const applyMode = async (newKey) => {
    setLoading(true)
    setShowConfirm(null)
    const cfg = MODES[newKey].config
    try {
      await fetch(`${configEndpoint}?dry_run=${cfg.dry_run}&use_mock=${cfg.use_mock}`, { method: 'POST' })
      onUpdate(cfg)
    } catch { /* ignora errori di rete */ }
    finally { setLoading(false) }
  }

  const confirmKey   = showConfirm ? MODES[showConfirm] : null
  const dataChanges  = showConfirm
    ? MODES[showConfirm].config.use_mock !== MODES[modeKey].config.use_mock
    : false

  return (
    <GlowCard glow={mode.glow} className="relative overflow-hidden">

      {/* Background tint */}
      <div className={`absolute inset-0 rounded-xl opacity-[0.04] ${
        modeKey === 'mock' ? 'bg-sky-500' : modeKey === 'watch' ? 'bg-amber-500' : 'bg-green-500'
      }`} />

      <div className="relative">
        <div className="mb-4">
          <Label className="mb-0">
            <Tooltip text="Controlla la fonte dati e se il bot invia ordini reali a MetaTrader 5.">
              <span>Modalità operativa</span>
              <InfoIcon />
            </Tooltip>
          </Label>
        </div>

        {/* 3-mode selector */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          {Object.entries(MODES).map(([key, m]) => (
            <button
              key={key}
              disabled={loading}
              onClick={() => handleSelect(key)}
              className={`flex flex-col items-center gap-1.5 py-3 px-1 rounded-lg border
                text-[11px] font-mono font-bold tracking-wider transition-all duration-200
                ${key === modeKey
                  ? `${m.activeBg} ${m.color} shadow-sm`
                  : 'bg-transparent border-terminal-border text-terminal-muted hover:border-gray-500 hover:text-gray-300'}
                ${loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
              `}
            >
              <span className="text-lg leading-none">{m.emoji}</span>
              <span>{m.label}</span>
            </button>
          ))}
        </div>

        {/* Active badge */}
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border
          text-xs font-mono font-bold ${mode.activeBg} ${mode.color} mb-3`}>
          <span className={`w-2 h-2 rounded-full ${mode.dotColor} ${modeKey === 'trade' ? 'animate-pulse' : ''}`} />
          {mode.emoji} {mode.label}
          {loading && <span className="ml-1 opacity-60 animate-pulse">...</span>}
        </div>

        {/* Description */}
        <p className="text-[11px] text-terminal-muted leading-relaxed mb-3">
          {mode.description}
        </p>

        {/* Features */}
        <ul className="space-y-1 mb-3">
          {mode.features.map((f, i) => (
            <li key={i} className="flex items-center gap-2 text-[11px] text-terminal-muted">
              <span className={`text-[10px] ${mode.color}`}>✓</span>
              {f}
            </li>
          ))}
        </ul>

        {/* Status note */}
        {!botRunning && (
          <div className="text-[10px] text-terminal-muted bg-gray-500/10 border border-gray-500/20 rounded-lg px-3 py-2">
            Bot non in esecuzione — la modalità sarà applicata al prossimo avvio.
          </div>
        )}
        {botRunning && modeKey === 'watch' && (
          <div className="text-[10px] text-terminal-muted bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
            Modalità attiva. Cambio su TRADE: ordini dal prossimo tick. Cambio su MOCK: riavvio necessario.
          </div>
        )}
        {botRunning && modeKey === 'trade' && (
          <div className="text-[10px] text-green-400/70 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2">
            ● Ordini LIVE DEMO attivi sul conto MT5.
          </div>
        )}
        {botRunning && modeKey === 'mock' && (
          <div className="text-[10px] text-terminal-muted bg-blue-500/10 border border-blue-500/20 rounded-lg px-3 py-2">
            Cambio su WATCH o TRADE richiede il riavvio del bot.
          </div>
        )}
      </div>

      {/* Confirm modal */}
      <AnimatePresence>
        {showConfirm && confirmKey && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-terminal-bg/96 backdrop-blur-sm rounded-xl
                       flex flex-col items-center justify-center p-5 z-10"
          >
            <div className="text-3xl mb-3">{confirmKey.emoji}</div>
            <p className="text-sm font-mono text-center text-gray-200 mb-2">
              Passare a <strong className={confirmKey.color}>{confirmKey.label}</strong>?
            </p>

            {showConfirm === 'trade' && (
              <p className="text-[11px] text-terminal-muted text-center mb-3 leading-relaxed max-w-[220px]">
                Il bot inizierà ad aprire <strong>ordini reali</strong> sul conto demo MT5 al prossimo tick.
              </p>
            )}

            {dataChanges && botRunning && (
              <div className="text-[11px] text-amber-400 text-center mb-3 leading-relaxed
                              bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 max-w-[220px]">
                ⚠️ Il cambio della fonte dati (mock ↔ reale) richiede il <strong>riavvio del bot</strong>.
              </div>
            )}

            <div className="flex gap-3 mt-1">
              <button
                onClick={() => setShowConfirm(null)}
                className="px-4 py-2 text-xs font-mono rounded-lg border border-terminal-border
                           text-terminal-muted hover:border-gray-500 transition-colors"
              >
                Annulla
              </button>
              <button
                onClick={() => applyMode(showConfirm)}
                className={`px-4 py-2 text-xs font-mono rounded-lg text-white transition-colors ${
                  showConfirm === 'trade' ? 'bg-green-700 hover:bg-green-600' :
                  showConfirm === 'mock'  ? 'bg-sky-700   hover:bg-sky-600'   :
                                           'bg-amber-700 hover:bg-amber-600'
                }`}
              >
                Conferma
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlowCard>
  )
}
