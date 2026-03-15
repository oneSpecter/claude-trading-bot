import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { GlowCard, Label, Toggle, Tooltip, InfoIcon } from './ui'

const MODES = {
  dry: {
    label:       'DRY RUN',
    color:       'text-amber-400',
    bg:          'bg-amber-500/10 border-amber-500/20',
    dot:         'bg-amber-400',
    description: 'Il bot analizza il mercato con Claude AI e calcola i setup, ma non apre ordini reali su MT5. Ideale per testare la strategia senza rischi.',
    features: [
      'Analisi AI attiva (3 stadi)',
      'Tutti i filtri tecnici attivi',
      'Nessun ordine inviato a MT5',
      'Journal e statistiche aggiornati',
    ],
  },
  live: {
    label:       'LIVE DEMO',
    color:       'text-green-400',
    bg:          'bg-green-500/10 border-green-500/20',
    dot:         'bg-green-400',
    description: 'Il bot apre e chiude ordini reali sul conto demo MT5. I trade vengono eseguiti con dimensione calcolata sull\'1% del capitale.',
    features: [
      'Ordini reali su conto demo MT5',
      'Risk management 1% per trade',
      'AI exit check ogni 5 minuti',
      'Chiusura automatica SL/TP',
    ],
  },
}

export default function DryRunControl({ dryRun, onToggle, botRunning }) {
  const [showConfirm, setShowConfirm] = useState(false)
  const [loading,     setLoading]     = useState(false)
  const mode = dryRun ? MODES.dry : MODES.live

  const handleToggle = (newDry) => {
    // Se si passa da dry a live, chiedi conferma
    if (!newDry && dryRun) {
      setShowConfirm(true)
    } else {
      applyToggle(newDry)
    }
  }

  const applyToggle = async (newDry) => {
    setLoading(true)
    setShowConfirm(false)
    try {
      await fetch(`/api/config?dry_run=${newDry}`, { method: 'POST' })
      onToggle(newDry)
    } catch {
      // ignora errori di rete
    } finally {
      setLoading(false)
    }
  }

  return (
    <GlowCard glow={dryRun ? 'amber' : 'green'} className="relative overflow-hidden">

      {/* Background glow */}
      <div className={`absolute inset-0 opacity-5 rounded-xl ${dryRun ? 'bg-amber-500' : 'bg-green-500'}`} />

      <div className="relative">
        <div className="flex items-center justify-between mb-4">
          <Label className="mb-0">
            <Tooltip text="Controlla se il bot invia ordini reali a MetaTrader 5 o lavora solo in simulazione.">
              <span>Modalità bot</span>
              <InfoIcon />
            </Tooltip>
          </Label>

          <div className="flex items-center gap-3">
            <span className="text-[11px] font-mono text-terminal-muted">DRY</span>
            <Toggle
              checked={!dryRun}
              onChange={(live) => handleToggle(!live)}
              disabled={loading}
            />
            <span className="text-[11px] font-mono text-terminal-muted">LIVE</span>
          </div>
        </div>

        {/* Mode badge */}
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-mono font-bold ${mode.bg} ${mode.color} mb-3`}>
          <span className={`w-2 h-2 rounded-full ${mode.dot} ${!dryRun ? 'animate-pulse' : ''}`} />
          {mode.label}
          {loading && <span className="ml-1 opacity-60">...</span>}
        </div>

        {/* Description */}
        <p className="text-[11px] text-terminal-muted leading-relaxed mb-3">
          {mode.description}
        </p>

        {/* Features */}
        <ul className="space-y-1">
          {mode.features.map((f, i) => (
            <li key={i} className="flex items-center gap-2 text-[11px] text-terminal-muted">
              <span className={`text-[10px] ${dryRun ? 'text-amber-400' : 'text-green-400'}`}>✓</span>
              {f}
            </li>
          ))}
        </ul>

        {/* Warning bot not running */}
        {!botRunning && (
          <div className="mt-3 text-[10px] text-terminal-muted bg-gray-500/10 border border-gray-500/20 rounded-lg px-3 py-2">
            Il bot non è in esecuzione — la modifica sarà applicata al prossimo avvio.
          </div>
        )}
        {botRunning && (
          <div className="mt-3 text-[10px] text-terminal-muted bg-blue-500/10 border border-blue-500/20 rounded-lg px-3 py-2">
            Modifica attiva dal prossimo tick (~5 minuti).
          </div>
        )}
      </div>

      {/* Confirm modal — switching to LIVE */}
      <AnimatePresence>
        {showConfirm && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-terminal-bg/95 backdrop-blur-sm rounded-xl flex flex-col items-center justify-center p-5 z-10"
          >
            <div className="text-amber-400 text-2xl mb-3">⚠️</div>
            <p className="text-sm font-mono text-center text-gray-200 mb-2">
              Passare a <strong>LIVE DEMO</strong>?
            </p>
            <p className="text-[11px] text-terminal-muted text-center mb-5 leading-relaxed">
              Il bot inizierà ad aprire ordini reali sul conto demo MT5 al prossimo tick.
              Assicurati che MT5 sia connesso.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowConfirm(false)}
                className="px-4 py-2 text-xs font-mono rounded-lg border border-terminal-border text-terminal-muted hover:border-gray-500 transition-colors"
              >
                Annulla
              </button>
              <button
                onClick={() => applyToggle(false)}
                className="px-4 py-2 text-xs font-mono rounded-lg bg-green-600 hover:bg-green-500 text-white transition-colors"
              >
                Conferma LIVE
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </GlowCard>
  )
}
