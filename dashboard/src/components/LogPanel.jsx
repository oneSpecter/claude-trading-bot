import { useEffect, useRef, useState, useCallback } from 'react'

const POLL_MS = 2000

function colorLine(line) {
  if (/ERROR|❌/.test(line))                       return 'text-red-400'
  if (/WARNING/.test(line))                        return 'text-amber-400'
  if (/\bBUY\b/.test(line))                        return 'text-green-400'
  if (/\bSELL\b/.test(line))                       return 'text-red-400'
  if (/\bHOLD\b/.test(line))                       return 'text-amber-300'
  if (/✅|PASS|connesso|avviato|aperto/i.test(line)) return 'text-green-300'
  if (/⏭|SKIP/.test(line))                        return 'text-terminal-muted'
  if (/🧠|Decisione AI|Stage/.test(line))          return 'text-purple-400'
  if (/Tick ───/.test(line))                       return 'text-sky-400'
  if (/\[MOCK\]/.test(line))                       return 'text-sky-600'
  return 'text-gray-300'
}

export default function LogPanel() {
  const [lines,      setLines]      = useState([])
  const [total,      setTotal]      = useState(0)
  const [autoScroll, setAutoScroll] = useState(true)
  const [collapsed,  setCollapsed]  = useState(false)
  const bottomRef = useRef(null)
  const containerRef = useRef(null)

  const fetchLogs = useCallback(async () => {
    try {
      const data = await fetch('/api/logs?lines=150').then(r => r.json())
      setLines(data.lines ?? [])
      setTotal(data.total ?? 0)
    } catch { /* server non raggiungibile */ }
  }, [])

  useEffect(() => {
    fetchLogs()
    const id = setInterval(fetchLogs, POLL_MS)
    return () => clearInterval(id)
  }, [fetchLogs])

  // Auto-scroll al fondo quando arrivano nuove righe
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'instant' })
    }
  }, [lines, autoScroll])

  // Disabilita auto-scroll se l'utente scrolla manualmente verso l'alto
  function handleScroll() {
    const el = containerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 32
    setAutoScroll(atBottom)
  }

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg overflow-hidden">

      {/* Header */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-terminal-border">
        <div className="flex items-center gap-3">
          <span className="text-xs text-terminal-muted uppercase tracking-wider">
            Log bot in tempo reale
          </span>
          {total > 0 && (
            <span className="text-[10px] text-terminal-muted bg-terminal-border px-1.5 py-0.5 rounded">
              {total} righe totali
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Auto-scroll toggle */}
          <button
            onClick={() => setAutoScroll(v => !v)}
            className={`text-[10px] px-2 py-1 rounded border transition-colors ${
              autoScroll
                ? 'border-sky-700 bg-sky-900/30 text-sky-400'
                : 'border-terminal-border text-terminal-muted hover:border-terminal-muted'
            }`}
          >
            ↓ Auto
          </button>
          {/* Clear visuale */}
          <button
            onClick={() => setLines([])}
            className="text-[10px] px-2 py-1 rounded border border-terminal-border text-terminal-muted hover:border-terminal-muted transition-colors"
          >
            Clear
          </button>
          {/* Collapse su mobile */}
          <button
            onClick={() => setCollapsed(v => !v)}
            className="text-[10px] px-2 py-1 rounded border border-terminal-border text-terminal-muted hover:border-terminal-muted transition-colors sm:hidden"
          >
            {collapsed ? '▼' : '▲'}
          </button>
        </div>
      </div>

      {/* Log body */}
      {!collapsed && (
        <div
          ref={containerRef}
          onScroll={handleScroll}
          className="h-64 sm:h-80 overflow-y-auto p-3 sm:p-4 font-mono text-[11px] sm:text-xs leading-5 space-y-px"
        >
          {lines.length === 0 ? (
            <span className="text-terminal-muted">
              In attesa di log… avvia il bot.
            </span>
          ) : (
            lines.map((line, i) => (
              <div key={i} className={`whitespace-pre-wrap break-all ${colorLine(line)}`}>
                {line}
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  )
}
