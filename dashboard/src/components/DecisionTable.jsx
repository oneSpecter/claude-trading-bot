import { useState } from 'react'
import DecisionBadge from './DecisionBadge'

function fmt(ts) {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('it-IT', {
      month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return ts }
}

function ConfDot({ value }) {
  const color = value >= 75 ? 'bg-green-500' : value >= 55 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <span className="flex items-center gap-1.5 tabular-nums">
      <span className={`inline-block w-2 h-2 rounded-full ${color}`} />
      {value}%
    </span>
  )
}

function ExpandedDetail({ e }) {
  return (
    <div className="space-y-3">
      {e.devil_advocate && (
        <div>
          <div className="text-amber-400 text-xs font-semibold mb-1">⚔ Devil's Advocate</div>
          <div className="text-terminal-muted text-xs leading-relaxed">{e.devil_advocate}</div>
        </div>
      )}
      {e.tech_brief && (
        <div>
          <div className="text-sky-400 text-xs font-semibold mb-1">📊 Brief Tecnico</div>
          <div className="text-terminal-muted text-xs leading-relaxed line-clamp-4">{e.tech_brief}</div>
        </div>
      )}
      {e.news_brief && (
        <div>
          <div className="text-purple-400 text-xs font-semibold mb-1">🌐 Brief Macro</div>
          <div className="text-terminal-muted text-xs leading-relaxed line-clamp-3">{e.news_brief}</div>
        </div>
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-terminal-muted border-t border-terminal-border pt-2">
        {e.technical_score != null  && <span>Tech: <span className="text-white">{e.technical_score}</span></span>}
        {e.fundamental_score != null && <span>Fund: <span className="text-white">{e.fundamental_score}</span></span>}
        {e.price != null && <span>Price: <span className="text-white">{e.price}</span></span>}
        {e.sl   != null && <span>SL: <span className="text-red-400">{e.sl}</span></span>}
        {e.tp   != null && <span>TP: <span className="text-green-400">{e.tp}</span></span>}
        {e.lot  != null && <span>Lot: <span className="text-white">{e.lot}</span></span>}
      </div>
    </div>
  )
}

/* ── Card singola per mobile ─────────────────────────────── */
function MobileCard({ e, isOpen, onToggle }) {
  return (
    <div
      className={`px-4 py-3.5 cursor-pointer transition-colors border-b border-terminal-border/60
        ${isOpen ? 'bg-white/[0.04]' : 'hover:bg-white/[0.03]'}`}
      onClick={onToggle}
    >
      {/* Riga 1: badge + confidenza + timestamp */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2.5">
          <DecisionBadge decision={e.decision} />
          {e.confidence != null && <ConfDot value={e.confidence} />}
          {e.decision_changed && (
            <span className="text-amber-400 text-xs" title={`Iniziale: ${e.initial_decision}`}>⚠️</span>
          )}
        </div>
        <span className="text-xs text-terminal-muted tabular-nums">{fmt(e.timestamp)}</span>
      </div>

      {/* Riga 2: tag info */}
      <div className="flex flex-wrap gap-2 mb-2">
        {e.market_regime && (
          <span className="text-[10px] text-sky-400 bg-sky-900/30 border border-sky-800/50 px-1.5 py-0.5 rounded">
            {e.market_regime}
          </span>
        )}
        {e.tech_score_s1 != null && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
            e.tech_score_s1 >= 55
              ? 'text-green-400 bg-green-900/20 border-green-800/50'
              : 'text-amber-400 bg-amber-900/20 border-amber-800/50'
          }`}>S1: {e.tech_score_s1}</span>
        )}
        {e.web_search_done && (
          <span className="text-[10px] text-purple-400 bg-purple-900/20 border border-purple-800/50 px-1.5 py-0.5 rounded">
            🌐 web
          </span>
        )}
        {e.executed && (
          <span className="text-[10px] text-green-400 bg-green-900/20 border border-green-800/50 px-1.5 py-0.5 rounded">
            ✓ trade
          </span>
        )}
      </div>

      {/* Reasoning */}
      {e.reasoning && (
        <div className="text-xs text-terminal-muted leading-relaxed">
          {isOpen ? e.reasoning : `${e.reasoning.slice(0, 100)}${e.reasoning.length > 100 ? '…' : ''}`}
        </div>
      )}

      {/* Expanded */}
      {isOpen && (
        <div className="mt-3 pt-3 border-t border-terminal-border">
          <ExpandedDetail e={e} />
        </div>
      )}
    </div>
  )
}

/* ── Tabella desktop ─────────────────────────────────────── */
function DesktopTable({ journal, expanded, setExpanded }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-terminal-border text-xs text-terminal-muted uppercase">
            <th className="text-left px-4 py-3">Timestamp</th>
            <th className="text-left px-4 py-3">Decisione</th>
            <th className="text-left px-4 py-3">Conf.</th>
            <th className="text-left px-4 py-3">S1</th>
            <th className="text-left px-4 py-3">Web</th>
            <th className="text-left px-4 py-3">Regime</th>
            <th className="text-left px-4 py-3">⚠</th>
            <th className="text-left px-4 py-3">Trade</th>
            <th className="text-left px-4 py-3 min-w-[220px]">Reasoning</th>
          </tr>
        </thead>
        <tbody>
          {journal.map((e, i) => {
            const isOpen = expanded === i
            return (
              <>
                <tr
                  key={i}
                  onClick={() => setExpanded(isOpen ? null : i)}
                  className={`border-b border-terminal-border/50 cursor-pointer transition-colors
                    hover:bg-white/5 ${isOpen ? 'bg-white/5' : ''}`}
                >
                  <td className="px-4 py-3 text-terminal-muted whitespace-nowrap">{fmt(e.timestamp)}</td>
                  <td className="px-4 py-3"><DecisionBadge decision={e.decision} /></td>
                  <td className="px-4 py-3">
                    {e.confidence != null ? <ConfDot value={e.confidence} /> : '—'}
                  </td>
                  <td className="px-4 py-3">
                    {e.tech_score_s1 != null
                      ? <span className={e.tech_score_s1 >= 55 ? 'text-green-400' : 'text-amber-400'}>
                          {e.tech_score_s1}
                        </span>
                      : <span className="text-terminal-muted">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {e.web_search_done == null ? '—'
                      : e.web_search_done
                        ? <span className="text-purple-400">✓</span>
                        : <span className="text-terminal-muted">⏭</span>}
                  </td>
                  <td className="px-4 py-3 text-xs text-sky-400 whitespace-nowrap">
                    {e.market_regime ?? '—'}
                  </td>
                  <td className="px-4 py-3">
                    {e.decision_changed
                      ? <span title={`Iniziale: ${e.initial_decision}`}>⚠️</span>
                      : <span className="text-terminal-muted">—</span>}
                  </td>
                  <td className="px-4 py-3">
                    {e.executed
                      ? <span className="text-green-400 text-xs">✓ {e.ticket ?? ''}</span>
                      : <span className="text-terminal-muted text-xs">—</span>}
                  </td>
                  <td className="px-4 py-3 text-terminal-muted text-xs">
                    {e.reasoning
                      ? (isOpen ? e.reasoning : `${e.reasoning.slice(0, 70)}${e.reasoning.length > 70 ? '…' : ''}`)
                      : '—'}
                  </td>
                </tr>

                {isOpen && (
                  <tr key={`${i}-exp`} className="bg-white/[0.03]">
                    <td colSpan={9} className="px-6 py-4">
                      <div className="grid grid-cols-2 gap-4">
                        <ExpandedDetail e={e} />
                      </div>
                    </td>
                  </tr>
                )}
              </>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

/* ── Componente principale ───────────────────────────────── */
export default function DecisionTable({ journal }) {
  const [expanded, setExpanded] = useState(null)

  if (!journal?.length) {
    return (
      <div className="bg-terminal-card border border-terminal-border rounded-lg p-8 text-center text-terminal-muted text-sm">
        Nessuna decisione registrata. Avvia il bot per iniziare.
      </div>
    )
  }

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg overflow-hidden">
      <div className="px-4 sm:px-6 py-3 border-b border-terminal-border text-xs text-terminal-muted uppercase tracking-wider">
        Storico decisioni ({journal.length})
      </div>

      {/* Mobile: cards */}
      <div className="sm:hidden divide-y divide-terminal-border/40">
        {journal.map((e, i) => (
          <MobileCard
            key={i}
            e={e}
            isOpen={expanded === i}
            onToggle={() => setExpanded(expanded === i ? null : i)}
          />
        ))}
      </div>

      {/* Desktop: tabella */}
      <div className="hidden sm:block">
        <DesktopTable journal={journal} expanded={expanded} setExpanded={setExpanded} />
      </div>
    </div>
  )
}
