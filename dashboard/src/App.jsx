import { useState, useEffect, useCallback } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import StatusHeader  from './components/StatusHeader'
import StatsRow      from './components/StatsRow'
import CurrentState  from './components/CurrentState'
import DecisionTable from './components/DecisionTable'
import CostPanel     from './components/CostPanel'
import LogPanel      from './components/LogPanel'

const POLL_MS = 5000

function fmt(ts) {
  if (!ts) return ''
  try { return new Date(ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) }
  catch { return '' }
}

function ConfidenceChart({ journal }) {
  if (!journal?.length) return null

  const data = [...journal]
    .reverse()
    .slice(-40)
    .map(e => ({
      t:    fmt(e.timestamp),
      conf: e.confidence ?? 0,
      dec:  e.decision,
    }))

  const dotColor = (dec) =>
    dec === 'BUY' ? '#22c55e' : dec === 'SELL' ? '#ef4444' : '#f59e0b'

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-5">
      <div className="text-xs text-terminal-muted uppercase tracking-wider mb-4">
        Confidenza ultime 40 analisi
      </div>
      <ResponsiveContainer width="100%" height={120}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}   />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" tick={{ fill: '#8899bb', fontSize: 9 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis domain={[0, 100]} tick={{ fill: '#8899bb', fontSize: 9 }} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{ backgroundColor: '#0f1629', border: '1px solid #1e2d4a', fontSize: 11 }}
            labelStyle={{ color: '#8899bb' }}
            formatter={(v, _, p) => [`${v}% (${p.payload.dec})`, 'Confidenza']}
          />
          <ReferenceLine y={65} stroke="#f59e0b" strokeDasharray="3 3" strokeOpacity={0.5} />
          <Area
            type="monotone"
            dataKey="conf"
            stroke="#3b82f6"
            strokeWidth={1.5}
            fill="url(#confGrad)"
            dot={({ cx, cy, payload }) => (
              <circle
                key={`dot-${cx}`}
                cx={cx} cy={cy} r={3}
                fill={dotColor(payload.dec)}
                stroke="none"
              />
            )}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-4 mt-2 text-xs text-terminal-muted">
        <span><span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1"/>BUY</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1"/>SELL</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-amber-500 mr-1"/>HOLD</span>
        <span className="hidden sm:inline ml-auto">linea tratteggiata = soglia 65%</span>
      </div>
    </div>
  )
}

export default function App() {
  const [status,     setStatus]     = useState(null)
  const [journal,    setJournal]    = useState([])
  const [stats,      setStats]      = useState({})
  const [costs,      setCosts]      = useState({})
  const [lastUpdate, setLastUpdate] = useState(null)
  const [error,      setError]      = useState(null)

  const fetchAll = useCallback(async () => {
    try {
      const ok = r => { if (!r.ok) throw new Error(r.status); return r.json() }
      const [s, j, st, c] = await Promise.all([
        fetch('/api/status').then(ok),
        fetch('/api/journal?limit=100').then(ok),
        fetch('/api/stats').then(ok),
        fetch('/api/costs').then(ok),
      ])
      setStatus(s)
      setJournal(j)
      setStats(st)
      setCosts(c)
      setLastUpdate(new Date())
      setError(null)
    } catch {
      setError('Server non raggiungibile — avvia: uvicorn server:app --host 0.0.0.0 --port 8000')
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const id = setInterval(fetchAll, POLL_MS)
    return () => clearInterval(id)
  }, [fetchAll])

  return (
    <div className="min-h-screen bg-terminal-bg text-gray-100 p-3 sm:p-5">
      <div className="max-w-screen-xl mx-auto space-y-3 sm:space-y-4">

        <StatusHeader
          status={status}
          lastUpdate={lastUpdate}
          error={error}
          onBotAction={fetchAll}
        />

        <StatsRow stats={stats} />

        {/* Market state + chart — stacked on mobile, side by side on lg */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 sm:gap-4">
          <div className="lg:col-span-2">
            <CurrentState status={status} journal={journal} />
          </div>
          <ConfidenceChart journal={journal} />
        </div>

        {/* Cost panel + table — stacked on mobile */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 sm:gap-4">
          <div className="lg:col-span-1">
            <CostPanel costs={costs} />
          </div>
          <div className="lg:col-span-2">
            <DecisionTable journal={journal} />
          </div>
        </div>

        {/* Log real-time */}
        <LogPanel />

      </div>
    </div>
  )
}
