import { useState } from 'react'

async function apiPost(url) {
  const r = await fetch(url, { method: 'POST' })
  return r.json()
}

export default function StatusHeader({ status, lastUpdate, error, onBotAction }) {
  const running   = status?.running
  const phase     = status?.phase ?? 'offline'
  const symbol    = status?.symbol ?? '—'
  const tf        = status?.timeframe ?? '—'
  const isDry     = status?.dry_run
  const [loading,  setLoading]  = useState(false)
  const [confirm,  setConfirm]  = useState(false) // conferma avvio LIVE
  const [stopping, setStopping] = useState(false) // in attesa che il bot si fermi

  const phaseLabel = {
    scanning:  'SCANNING',
    analyzing: 'ANALYZING',
    idle:      'IDLE',
    stopped:   'STOPPED',
    offline:   'OFFLINE',
  }[phase] ?? phase.toUpperCase()

  const phaseColor = {
    scanning:  'text-sky-400',
    analyzing: 'text-amber-400 animate-pulse',
    idle:      'text-green-400',
    stopped:   'text-gray-500',
    offline:   'text-red-500',
  }[phase] ?? 'text-gray-400'

  async function handleStop() {
    setLoading(true)
    setStopping(true)
    await apiPost('/api/bot/stop')
    setLoading(false)
    onBotAction?.()
    // Polling finché running diventa false (max 40s)
    for (let i = 0; i < 8; i++) {
      await new Promise(r => setTimeout(r, 5000))
      try {
        const s = await fetch('/api/status').then(r => r.json())
        if (!s.running) { setStopping(false); onBotAction?.(); return }
      } catch { /* ignora */ }
    }
    setStopping(false)
    onBotAction?.()
  }

  async function handleStart(dry) {
    setConfirm(false)
    setLoading(true)
    await apiPost(`/api/bot/start?dry_run=${dry}`)
    setLoading(false)
    onBotAction?.()
  }

  return (
    <div className="border border-terminal-border bg-terminal-card rounded-lg px-4 py-3 sm:px-6 sm:py-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">

        {/* Left: title + symbol */}
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-base sm:text-xl font-bold text-white tracking-wide">
            🤖 FOREX AI BOT
          </span>
          <span className="text-terminal-muted text-sm hidden sm:inline">×</span>
          <span className="text-sky-400 font-semibold">{symbol}</span>
          <span className="text-terminal-muted text-xs">{tf}</span>
          {isDry && (
            <span className="text-xs bg-amber-900/40 text-amber-400 border border-amber-700 px-2 py-0.5 rounded">
              DRY-RUN
            </span>
          )}
        </div>

        {/* Center: phase dot */}
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${running ? 'bg-green-400' : 'bg-red-500'}`} />
          <span className={`text-xs font-semibold ${phaseColor}`}>{phaseLabel}</span>
        </div>

        {/* Right: controls + update time */}
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {error ? (
            <span className="text-xs text-red-400">{error}</span>
          ) : lastUpdate ? (
            <span className="text-xs text-terminal-muted hidden sm:inline">
              {lastUpdate.toLocaleTimeString('it-IT')}
            </span>
          ) : null}

          {/* Stop button */}
          {(running || stopping) && (
            <button
              onClick={handleStop}
              disabled={loading || stopping}
              className="text-xs px-3 py-2.5 min-h-[44px] rounded border border-red-700 bg-red-900/30 text-red-400
                         hover:bg-red-900/60 disabled:opacity-60 transition-colors"
            >
              {stopping ? '⏳ Stopping…' : loading ? '…' : '⏹ Ferma'}
            </button>
          )}

          {/* Start buttons */}
          {!running && !stopping && !confirm && (
            <>
              <button
                onClick={() => handleStart(true)}
                disabled={loading}
                className="text-xs px-3 py-2.5 min-h-[44px] rounded border border-amber-700 bg-amber-900/30 text-amber-400
                           hover:bg-amber-900/60 disabled:opacity-50 transition-colors"
              >
                {loading ? '…' : '▶ Dry-Run'}
              </button>
              <button
                onClick={() => setConfirm(true)}
                disabled={loading}
                className="text-xs px-3 py-2.5 min-h-[44px] rounded border border-green-700 bg-green-900/30 text-green-400
                           hover:bg-green-900/60 disabled:opacity-50 transition-colors"
              >
                ▶ Live
              </button>
            </>
          )}

          {/* Conferma avvio live */}
          {!running && confirm && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-amber-400">Ordini reali. Sicuro?</span>
              <button
                onClick={() => handleStart(false)}
                className="text-xs px-2 py-1 rounded border border-green-700 bg-green-900/40 text-green-400 hover:bg-green-900/70"
              >
                Sì
              </button>
              <button
                onClick={() => setConfirm(false)}
                className="text-xs px-2 py-1 rounded border border-terminal-border text-terminal-muted hover:bg-white/5"
              >
                No
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
