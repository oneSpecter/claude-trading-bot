import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { GlowCard, Label, Tooltip, InfoIcon } from './ui'

// ── Toggle switch ──────────────────────────────────────────────
function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className={`relative w-10 h-5 rounded-full border transition-colors duration-200 flex-shrink-0 ${
        checked
          ? 'bg-blue-500/40 border-blue-500/50'
          : 'bg-terminal-border/60 border-terminal-border'
      } disabled:opacity-40`}
    >
      <motion.div
        className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow"
        animate={{ left: checked ? '1.25rem' : '0.125rem' }}
        transition={{ type: 'spring', stiffness: 500, damping: 30 }}
      />
    </button>
  )
}

// ── Field definitions ─────────────────────────────────────────
const FIELD_GROUPS = [
  {
    group: 'Filtri di ingresso',
    glow: 'blue',
    fields: [
      {
        key: 'require_ema_cross',
        label: 'Richiedi crossover EMA',
        type: 'bool',
        tip: "Analizza solo quando c'è un crossover EMA 9/21 nelle ultime 3 candele. Disabilitare aumenta le analisi ma anche i costi API.",
      },
      {
        key: 'require_rsi_aligned',
        label: 'RSI allineato al crossover',
        type: 'bool',
        tip: 'Per un cross rialzista RSI deve essere > 45. Per uno ribassista < 55. Riduce i falsi segnali in mercati con momentum debole.',
      },
      {
        key: 'require_adx',
        label: 'Filtra mercati ranging (ADX)',
        type: 'bool',
        tip: 'Salta l\'analisi se ADX < soglia. Evita falsi segnali in mercati senza trend direzionale.',
      },
      {
        key: 'adx_threshold',
        label: 'Soglia ADX',
        type: 'number',
        min: 10, max: 50, step: 1,
        tip: 'ADX minimo per considerare il mercato in trend. Default: 25. ≥ 25 = trending, < 25 = ranging (bot non analizza).',
      },
      {
        key: 'require_h4_confirm',
        label: 'Conferma bias H4',
        type: 'bool',
        tip: 'Non aprire trade H1 contro il trend principale su H4. Riduce i falsi segnali del 30-40% su EUR/USD.',
      },
    ],
  },
  {
    group: 'Soglie di esecuzione',
    glow: 'purple',
    fields: [
      {
        key: 'min_confidence',
        label: 'Confidenza minima (%)',
        type: 'number',
        min: 40, max: 95, step: 1,
        tip: 'Claude deve raggiungere almeno questa confidenza per aprire un trade. Default: 65. Alzare = meno trade, più selettivi.',
      },
      {
        key: 'web_search_min_score',
        label: 'Score minimo per ricerca notizie',
        type: 'number',
        min: 40, max: 95, step: 1,
        tip: 'Stage 2 (web search notizie) viene chiamato solo se Stage 1 dà un punteggio ≥ a questo valore. Alzare = meno chiamate API costose.',
      },
    ],
  },
  {
    group: 'Risk Management',
    glow: 'red',
    fields: [
      {
        key: 'max_daily_loss_pct',
        label: 'Perdita giornaliera massima (%)',
        type: 'number',
        min: 0, max: 10, step: 0.5,
        tip: 'Se il P&L di oggi scende sotto questa % del capitale, nessun nuovo trade per il resto del giorno. 0 = disabilitato.',
      },
      {
        key: 'max_trade_duration_h',
        label: 'Durata massima trade (ore)',
        type: 'number',
        min: 0, max: 168, step: 1,
        tip: 'Chiude forzatamente i trade aperti da più di N ore. Evita posizioni bloccate. 0 = disabilitato.',
      },
    ],
  },
  {
    group: 'Filtro orario sessione',
    glow: 'amber',
    fields: [
      {
        key: 'session_filter_enabled',
        label: 'Abilita filtro sessione',
        type: 'bool',
        tip: 'Blocca nuovi trade fuori dall\'orario attivo. I trade aperti vengono comunque gestiti (exit check). Raccomandato per EUR/USD.',
      },
      {
        key: 'session_start_utc',
        label: 'Inizio sessione (ora UTC)',
        type: 'number',
        min: 0, max: 23, step: 1,
        tip: 'Ora UTC di apertura della finestra di trading. Londra apre alle 07:00 UTC.',
      },
      {
        key: 'session_end_utc',
        label: 'Fine sessione (ora UTC)',
        type: 'number',
        min: 0, max: 23, step: 1,
        tip: 'Ora UTC di chiusura della finestra di trading. New York chiude alle 21:00 UTC.',
      },
    ],
  },
]

// ── SettingsPanel ─────────────────────────────────────────────
export default function SettingsPanel({ settings, onSave }) {
  const [local,  setLocal]  = useState({})
  const [saving, setSaving] = useState(false)
  const [saved,  setSaved]  = useState(false)

  // Sync local when settings prop changes (initial load / external update)
  useEffect(() => {
    if (settings && Object.keys(settings).length > 0) {
      setLocal(settings)
    }
  }, [settings])

  const isDirty = settings
    ? Object.keys(settings).some(k => local[k] !== settings[k])
    : false

  const handleChange = (key, value) => setLocal(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(local)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch {}
    setSaving(false)
  }

  const handleReset = () => setLocal(settings)

  if (!settings || Object.keys(settings).length === 0) {
    return (
      <GlowCard className="flex items-center justify-center h-32 text-terminal-muted text-xs font-mono">
        Caricamento impostazioni…
      </GlowCard>
    )
  }

  return (
    <div className="space-y-3 sm:space-y-4">

      {/* Save / discard bar — visibile solo quando ci sono modifiche */}
      {isDirty && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between gap-3 px-4 py-2.5 rounded-xl
            bg-blue-500/10 border border-blue-500/30 text-xs font-mono"
        >
          <span className="text-blue-300 flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
            Modifiche non salvate
          </span>
          <div className="flex gap-2">
            <button
              onClick={handleReset}
              className="px-3 py-1 rounded-lg bg-terminal-border/40 text-terminal-muted hover:text-white transition-colors"
            >
              Annulla
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-1 rounded-lg bg-blue-500/20 border border-blue-500/40
                text-blue-300 hover:bg-blue-500/30 transition-colors disabled:opacity-50"
            >
              {saving ? 'Salvataggio…' : 'Salva impostazioni'}
            </button>
          </div>
        </motion.div>
      )}

      {/* Confirmation toast */}
      {saved && !isDirty && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="px-4 py-2.5 rounded-xl bg-green-500/10 border border-green-500/30
            text-green-400 text-xs font-mono"
        >
          ✓ Impostazioni salvate — attive al prossimo tick
        </motion.div>
      )}

      {/* Field groups */}
      {FIELD_GROUPS.map(group => (
        <GlowCard key={group.group} glow={group.glow}>
          <Label>{group.group}</Label>
          <div className="space-y-1 mt-2">
            {group.fields.map(field => {
              const val     = local[field.key]
              const orig    = settings[field.key]
              const changed = val !== orig
              return (
                <div
                  key={field.key}
                  className={`flex items-center justify-between gap-4 py-2.5 px-3 rounded-lg border transition-colors ${
                    changed
                      ? 'border-blue-500/30 bg-blue-500/5'
                      : 'border-terminal-border/40 bg-terminal-bg/40'
                  }`}
                >
                  {/* Label + dirty dot */}
                  <div className="flex items-center gap-2 min-w-0 flex-1">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 transition-colors ${
                      changed ? 'bg-blue-400' : 'bg-transparent'
                    }`} />
                    <div className="text-[11px] font-mono text-gray-200 flex items-center gap-1">
                      <Tooltip text={field.tip}>
                        <span>{field.label}</span>
                        <InfoIcon />
                      </Tooltip>
                    </div>
                  </div>

                  {/* Badge + control */}
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded border
                      bg-green-500/10 border-green-500/30 text-green-400 hidden sm:inline">
                      LIVE
                    </span>
                    {field.type === 'bool' ? (
                      <Toggle
                        checked={!!val}
                        onChange={v => handleChange(field.key, v)}
                      />
                    ) : (
                      <input
                        type="number"
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        value={val ?? ''}
                        onChange={e => {
                          const n = field.step < 1
                            ? parseFloat(e.target.value)
                            : parseInt(e.target.value, 10)
                          if (!isNaN(n)) handleChange(field.key, n)
                        }}
                        className="w-20 text-right px-2 py-1 text-xs font-mono rounded-lg
                          bg-terminal-bg border border-terminal-border text-white
                          focus:outline-none focus:border-blue-500/50 focus:bg-blue-500/5
                          transition-colors"
                      />
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </GlowCard>
      ))}

      {/* Info footer */}
      <GlowCard glow="none">
        <Label>Parametri strutturali (richiedono riavvio)</Label>
        <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2 text-[10px] font-mono">
          {[
            { label: 'Simbolo',       key: 'symbol' },
            { label: 'Timeframe',     key: 'timeframe' },
            { label: 'Modello AI',    key: 'claude_model' },
            { label: 'Check interval',key: 'check_interval' },
            { label: 'ATR SL mult',   key: 'atr_sl_mult' },
            { label: 'ATR TP mult',   key: 'atr_tp_mult' },
          ].map(({ label, key }) => (
            <div key={key} className="bg-terminal-bg/60 rounded-lg p-2 border border-terminal-border/40">
              <div className="text-terminal-muted mb-0.5">{label}</div>
              <div className="flex items-center gap-1">
                <span className="text-[9px] px-1 py-0.5 rounded border
                  bg-amber-500/10 border-amber-500/30 text-amber-400">
                  RESTART
                </span>
              </div>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[10px] text-terminal-muted leading-relaxed">
          Per modificare simbolo, timeframe, modello AI e moltiplicatori ATR, aggiorna il file{' '}
          <code className="text-blue-300">.env</code> e riavvia il bot dalla tab Controllo.
        </p>
      </GlowCard>

    </div>
  )
}
