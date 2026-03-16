import { useState } from 'react'
import { motion } from 'framer-motion'
import { GlowCard, StatusDot, DecBadge } from './ui'

const STRATEGY_LABEL = {
  ema_rsi_ai_main:  'AI Main',
  ema_rsi_ai:       'AI Standard',
  ema_rsi_ai_scalp: 'AI Scalp',
  ema_rsi_manual:   'Manuale',
}

const STRATEGY_BADGE_COLOR = {
  ema_rsi_ai_main:  'bg-purple-500/10 border-purple-500/30 text-purple-400',
  ema_rsi_ai:       'bg-blue-500/10 border-blue-500/30 text-blue-400',
  ema_rsi_ai_scalp: 'bg-amber-500/10 border-amber-500/30 text-amber-400',
  ema_rsi_manual:   'bg-sky-500/10 border-sky-500/30 text-sky-400',
}

const PHASE_COLOR = {
  scanning:  'text-blue-400',
  analyzing: 'text-purple-400',
  idle:      'text-gray-400',
  stopped:   'text-red-400',
  error:     'text-red-500',
  offline:   'text-gray-600',
}

function fmt(ts) {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) }
  catch { return '—' }
}

export default function BotCard({ bot, status, lastJournalEntry, onSelect, onStart, onStop, onDelete }) {
  const [starting, setStarting] = useState(false)
  const [stopping, setStopping] = useState(false)

  const running  = status?.running
  const phase    = status?.phase ?? 'offline'
  const strategy = STRATEGY_LABEL[bot.strategy] ?? bot.strategy

  const handleStart = async (e) => {
    e.stopPropagation()
    setStarting(true)
    try { await onStart(bot.bot_id) } catch {}
    setStarting(false)
  }

  const handleStop = async (e) => {
    e.stopPropagation()
    setStopping(true)
    try { await onStop(bot.bot_id) } catch {}
    setStopping(false)
  }

  return (
    <motion.div whileHover={{ y: -2 }} transition={{ type: 'spring', stiffness: 400, damping: 30 }}>
      <GlowCard glow={running ? 'green' : 'none'}>

        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <StatusDot active={running} />
            <div>
              <div className="font-mono font-bold text-white text-base">{bot.symbol}</div>
              <div className="text-[10px] text-terminal-muted font-mono">{bot.bot_id}</div>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <span className={`text-[10px] px-2 py-0.5 rounded border font-mono ${
              STRATEGY_BADGE_COLOR[bot.strategy] ?? 'bg-gray-500/10 border-gray-500/30 text-gray-400'
            }`}>
              {strategy}
            </span>
            <span className={`text-[9px] font-mono ${PHASE_COLOR[phase] || 'text-gray-400'}`}>
              {phase.toUpperCase()}
            </span>
          </div>
        </div>

        {/* Market data */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          <div>
            <div className="text-[9px] text-terminal-muted uppercase mb-0.5">Prezzo</div>
            <div className="text-sm font-mono font-bold text-white">{status?.price ?? '—'}</div>
          </div>
          <div>
            <div className="text-[9px] text-terminal-muted uppercase mb-0.5">Ultima dec.</div>
            <div className="text-sm font-mono">
              {lastJournalEntry
                ? <DecBadge decision={lastJournalEntry.decision} />
                : <span className="text-terminal-muted">—</span>}
            </div>
          </div>
          <div>
            <div className="text-[9px] text-terminal-muted uppercase mb-0.5">Ora</div>
            <div className="text-[10px] font-mono text-terminal-muted">{fmt(lastJournalEntry?.timestamp)}</div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex gap-2 pt-2 border-t border-terminal-border/50">
          {/* Start / Stop */}
          {running ? (
            <button disabled={stopping} onClick={handleStop}
              className="flex-1 py-1.5 text-[11px] font-mono rounded-lg
                bg-red-500/10 border border-red-500/30 text-red-400
                hover:bg-red-500/20 transition-colors disabled:opacity-50">
              {stopping ? '…' : '■ Stop'}
            </button>
          ) : (
            <button disabled={starting} onClick={handleStart}
              className="flex-1 py-1.5 text-[11px] font-mono rounded-lg
                bg-green-500/10 border border-green-500/30 text-green-400
                hover:bg-green-500/20 transition-colors disabled:opacity-50">
              {starting ? '…' : '▶ Start'}
            </button>
          )}

          {/* Apri dashboard */}
          <button onClick={() => onSelect(bot.bot_id)}
            className="px-4 py-1.5 text-[11px] font-mono rounded-lg
              bg-blue-500/10 border border-blue-500/30 text-blue-400
              hover:bg-blue-500/20 transition-colors">
            Apri →
          </button>

          {/* Elimina */}
          {onDelete && (
            <button disabled={running} onClick={() => !running && onDelete(bot.bot_id)}
              title="Elimina bot"
              className="px-2.5 py-1.5 text-[11px] font-mono rounded-lg
                border border-terminal-border/60 text-terminal-muted/50
                hover:border-red-500/40 hover:text-red-400
                transition-colors disabled:opacity-25 disabled:cursor-not-allowed">
              ✕
            </button>
          )}
        </div>

      </GlowCard>
    </motion.div>
  )
}
