/**
 * BOT DASHBOARD — vista singolo bot
 * Stessa interfaccia di prima ma parametrizzata su botId.
 * Legge da /api/bots/{botId}/* invece di /api/*.
 */

import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip as RechartTooltip,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import LogPanel      from './LogPanel'
import ModeControl   from './ModeControl'
import SettingsPanel from './SettingsPanel'
import {
  GlowCard, Label, AnimatedNumber, Tooltip, InfoIcon,
  StatusDot, DecBadge,
} from './ui'

const POLL_MS = 5000

function fmt(ts) {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) }
  catch { return '—' }
}

const FadeIn = ({ children, delay = 0 }) => (
  <motion.div
    initial={{ opacity: 0, y: 12 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4, delay, ease: 'easeOut' }}
  >
    {children}
  </motion.div>
)

function MetricCard({ label, value, sub, color = 'text-white', glow, tooltip, prefix = '', suffix = '', decimals = 1 }) {
  return (
    <GlowCard glow={glow || 'blue'} className="flex flex-col gap-1">
      <Label className="mb-1">
        {tooltip ? (
          <Tooltip text={tooltip}><span>{label}</span><InfoIcon /></Tooltip>
        ) : label}
      </Label>
      <div className={`text-2xl font-mono font-bold ${color}`}>
        <AnimatedNumber value={typeof value === 'number' ? value : 0}
          decimals={decimals} prefix={prefix} suffix={suffix} />
        {typeof value !== 'number' && <span>{value ?? '—'}</span>}
      </div>
      {sub && <div className="text-[11px] text-terminal-muted">{sub}</div>}
    </GlowCard>
  )
}

function ConfidenceChart({ journal, minConfidence = 70 }) {
  if (!journal?.length) return (
    <GlowCard className="flex items-center justify-center h-40 text-terminal-muted text-xs font-mono">
      Nessun dato ancora
    </GlowCard>
  )
  const data = [...journal].reverse().slice(-40).map(e => ({
    t: fmt(e.timestamp), conf: e.confidence ?? 0, dec: e.decision,
  }))
  const dotColor = d => d === 'BUY' ? '#22c55e' : d === 'SELL' ? '#ef4444' : '#f59e0b'
  return (
    <GlowCard glow="blue">
      <Label>Confidenza ultime 40 analisi</Label>
      <ResponsiveContainer width="100%" height={130}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="confGrad2" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#3b82f6" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}    />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" tick={{ fill: '#6b7fa3', fontSize: 8 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis domain={[0,100]} tick={{ fill: '#6b7fa3', fontSize: 8 }} tickLine={false} axisLine={false} />
          <RechartTooltip
            contentStyle={{ backgroundColor: '#0a1020', border: '1px solid #1a2744', fontSize: 11, borderRadius: 8 }}
            labelStyle={{ color: '#6b7fa3' }}
            formatter={(v, _, p) => [`${v}% — ${p.payload.dec}`, 'Confidenza']}
          />
          <ReferenceLine y={minConfidence} stroke="#f59e0b" strokeDasharray="4 4" strokeOpacity={0.5}
            label={{ value: `${minConfidence}%`, position: 'insideTopRight', fill: '#f59e0b', fontSize: 9 }} />
          <Area type="monotone" dataKey="conf" stroke="#3b82f6" strokeWidth={1.5}
            fill="url(#confGrad2)"
            dot={({ cx, cy, payload }) => (
              <circle key={`d${cx}`} cx={cx} cy={cy} r={3} fill={dotColor(payload.dec)} stroke="none" />
            )}
          />
        </AreaChart>
      </ResponsiveContainer>
    </GlowCard>
  )
}

function DecisionTable({ journal }) {
  const rows = journal.slice(0, 15)
  if (!rows.length) return (
    <GlowCard className="flex items-center justify-center h-28 text-terminal-muted text-xs font-mono">
      Nessuna decisione ancora
    </GlowCard>
  )
  return (
    <GlowCard glow="none">
      <Label>Ultime decisioni</Label>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="text-terminal-muted border-b border-terminal-border">
              <th className="text-left pb-2 pr-3">Ora</th>
              <th className="text-left pb-2 pr-3">Decisione</th>
              <th className="text-right pb-2 pr-3">Conf</th>
              <th className="text-right pb-2 pr-3">Tech</th>
              <th className="text-right pb-2 pr-3">Fund</th>
              <th className="text-right pb-2 pr-3">R/R</th>
              <th className="text-center pb-2 pr-3">Changed</th>
              <th className="text-right pb-2">P&amp;L</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((e, i) => (
              <tr key={i} className="border-b border-terminal-border/50 hover:bg-white/2 transition-colors">
                <td className="py-1.5 pr-3 text-terminal-muted">{fmt(e.timestamp)}</td>
                <td className="py-1.5 pr-3"><DecBadge decision={e.decision} /></td>
                <td className={`py-1.5 pr-3 text-right font-bold ${
                  (e.confidence??0) >= 70 ? 'text-green-400' :
                  (e.confidence??0) >= 55 ? 'text-amber-400' : 'text-red-400'
                }`}>{e.confidence ?? '—'}%</td>
                <td className="py-1.5 pr-3 text-right text-blue-400">{e.technical_score ?? '—'}</td>
                <td className="py-1.5 pr-3 text-right text-purple-400">{e.fundamental_score ?? '—'}</td>
                <td className="py-1.5 pr-3 text-right text-terminal-muted">{e.rr_ratio?.toFixed(1) ?? '—'}</td>
                <td className="py-1.5 pr-3 text-center">
                  {e.decision_changed
                    ? <span className="text-amber-400">⚡</span>
                    : <span className="text-terminal-muted">—</span>}
                </td>
                <td className={`py-1.5 text-right font-bold ${
                  e.profit > 0 ? 'text-green-400' : e.profit < 0 ? 'text-red-400' : 'text-terminal-muted'
                }`}>
                  {e.profit != null ? `$${e.profit.toFixed(2)}` : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </GlowCard>
  )
}

function CurrentStatePanel({ status, journal }) {
  const last = journal?.[0]
  const adx  = status?.adx
  const rsi  = status?.rsi
  return (
    <GlowCard glow="none">
      <Label>Stato mercato attuale</Label>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        {[
          { label: 'EMA Trend', value: status?.ema_trend ?? '—',
            color: status?.ema_trend === 'RIALZISTA' ? 'text-green-400' : status?.ema_trend === 'RIBASSISTA' ? 'text-red-400' : 'text-gray-400',
            tip: 'Direzione trend da crossover EMA 9/21.' },
          { label: 'RSI (14)', value: rsi != null ? rsi.toFixed(1) : '—',
            color: rsi > 70 ? 'text-red-400' : rsi < 30 ? 'text-green-400' : 'text-white',
            tip: 'Relative Strength Index. > 70 ipercomprato. < 30 ipervenduto.' },
          { label: 'ADX (14)', value: adx != null ? adx.toFixed(1) : '—',
            color: adx >= 25 ? 'text-green-400' : 'text-amber-400',
            tip: 'Forza del trend. ≥ 25 = trending, < 25 = ranging.' },
          { label: 'H4 Bias', value: status?.h4_bias ?? '—',
            color: status?.h4_bias === 'BULLISH' ? 'text-green-400' : status?.h4_bias === 'BEARISH' ? 'text-red-400' : 'text-gray-400',
            tip: 'Trend principale su H4.' },
        ].map(({ label, value, color, tip }) => (
          <div key={label} className="bg-terminal-bg/60 rounded-lg p-3 border border-terminal-border/50">
            <div className="text-[9px] text-terminal-muted uppercase mb-1">
              <Tooltip text={tip}><span>{label}</span><InfoIcon /></Tooltip>
            </div>
            <div className={`text-base font-mono font-bold ${color}`}>{value}</div>
          </div>
        ))}
      </div>
      {last && (
        <div className="bg-terminal-bg/60 rounded-lg p-3 border border-terminal-border/50">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[9px] text-terminal-muted uppercase">Ultima analisi</span>
            <span className="text-[9px] text-terminal-muted">{fmt(last.timestamp)}</span>
            <DecBadge decision={last.decision} />
            {last.confidence != null && (
              <span className="text-[10px] font-mono text-terminal-muted ml-auto">{last.confidence}% conf</span>
            )}
          </div>
          {last.reasoning && (
            <p className="text-[11px] text-gray-300 leading-relaxed line-clamp-2">{last.reasoning}</p>
          )}
        </div>
      )}
    </GlowCard>
  )
}

function PnlChart({ journal }) {
  const trades = [...(journal ?? [])].filter(e => e.profit != null).reverse()
  if (!trades.length) return null
  let cum = 0
  const data = trades.map(e => {
    cum += e.profit
    return { t: fmt(e.timestamp), cum: parseFloat(cum.toFixed(2)) }
  })
  return (
    <GlowCard glow="green">
      <Label>P&amp;L cumulativo</Label>
      <ResponsiveContainer width="100%" height={120}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="pnlGrad2" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0}   />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" tick={{ fill: '#6b7fa3', fontSize: 8 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fill: '#6b7fa3', fontSize: 8 }} tickLine={false} axisLine={false} />
          <RechartTooltip contentStyle={{ backgroundColor: '#0a1020', border: '1px solid #1a2744', fontSize: 11, borderRadius: 8 }} formatter={v => [`$${v}`, 'P&L cumulativo']} />
          <ReferenceLine y={0} stroke="#6b7fa3" strokeOpacity={0.4} />
          <Area type="monotone" dataKey="cum" stroke="#22c55e" strokeWidth={1.5} fill="url(#pnlGrad2)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </GlowCard>
  )
}

function CostPanel({ costs }) {
  const byStage = costs?.by_stage ?? {}
  const entries = Object.entries(byStage).sort((a, b) => b[1] - a[1])
  return (
    <GlowCard glow="none">
      <Label>Costi API Claude</Label>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div><div className="text-[9px] text-terminal-muted uppercase mb-1">Oggi</div><div className="text-lg font-mono font-bold text-white">${(costs?.today_cost ?? 0).toFixed(3)}</div></div>
        <div><div className="text-[9px] text-terminal-muted uppercase mb-1">Mese</div><div className="text-lg font-mono font-bold text-blue-400">${(costs?.month_cost ?? 0).toFixed(2)}</div></div>
        <div><div className="text-[9px] text-terminal-muted uppercase mb-1">Totale</div><div className="text-lg font-mono font-bold text-terminal-muted">${(costs?.total_cost ?? 0).toFixed(2)}</div></div>
      </div>
      {entries.length > 0 && (
        <div className="space-y-1.5">
          {entries.map(([stage, cost]) => {
            const pct = costs?.total_cost > 0 ? cost / costs.total_cost * 100 : 0
            return (
              <div key={stage}>
                <div className="flex justify-between text-[10px] font-mono mb-0.5">
                  <span className="text-terminal-muted">{stage}</span>
                  <span className="text-white">${cost.toFixed(4)}</span>
                </div>
                <div className="h-1 bg-terminal-border rounded-full overflow-hidden">
                  <motion.div className="h-full bg-blue-500/60 rounded-full"
                    initial={{ width: 0 }} animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </GlowCard>
  )
}

const TABS = [
  { id: 'market',   label: 'Mercato',      icon: '📊' },
  { id: 'control',  label: 'Controllo',    icon: '🎛' },
  { id: 'stats',    label: 'Statistiche',  icon: '📈' },
  { id: 'settings', label: 'Impostazioni', icon: '⚙' },
]

function TabNav({ active, onChange }) {
  return (
    <div className="flex gap-1 bg-terminal-card border border-terminal-border rounded-xl p-1">
      {TABS.map(tab => (
        <button key={tab.id} onClick={() => onChange(tab.id)}
          className={`relative flex-1 flex items-center justify-center gap-2 px-4 py-2
            text-[11px] font-mono rounded-lg transition-all duration-200
            ${active === tab.id ? 'text-white' : 'text-terminal-muted hover:text-gray-300'}`}>
          {active === tab.id && (
            <motion.div layoutId="bot-tab-pill"
              className="absolute inset-0 bg-blue-500/15 border border-blue-500/30 rounded-lg"
              transition={{ type: 'spring', stiffness: 400, damping: 30 }} />
          )}
          <span className="relative z-10 text-base leading-none">{tab.icon}</span>
          <span className="relative z-10 hidden sm:inline tracking-wide">{tab.label}</span>
        </button>
      ))}
    </div>
  )
}

// ── BotDashboard — single-bot full view ────────────────────────────
export default function BotDashboard({ botId, botMeta, onBack }) {
  const [tab,         setTab]         = useState('market')
  const [status,      setStatus]      = useState(null)
  const [journal,     setJournal]     = useState([])
  const [stats,       setStats]       = useState({})
  const [costs,       setCosts]       = useState({})
  const [config,      setConfig]      = useState({ dry_run: true })
  const [settings,    setSettings]    = useState({})
  const [lastUpdate,  setLastUpdate]  = useState(null)
  const [error,       setError]       = useState(null)
  const [botStarting, setBotStarting] = useState(false)

  const api = useCallback(path => `/api/bots/${botId}${path}`, [botId])

  const fetchAll = useCallback(async () => {
    try {
      const ok = r => { if (!r.ok) throw new Error(r.status); return r.json() }
      const [s, j, st, c, sett, cfg] = await Promise.all([
        fetch(api('/status')).then(ok),
        fetch(api('/journal?limit=100')).then(ok),
        fetch(api('/stats')).then(ok),
        fetch(api('/costs')).then(ok),
        fetch(api('/settings')).then(ok),
        fetch(api('/config')).then(ok),
      ])
      setStatus(s); setJournal(j); setStats(st); setCosts(c); setSettings(sett)
      setConfig(cfg)
      setLastUpdate(new Date()); setError(null)
    } catch {
      setError('Server non raggiungibile')
    }
  }, [api])

  useEffect(() => {
    fetchAll()
    const id = setInterval(fetchAll, POLL_MS)
    return () => clearInterval(id)
  }, [fetchAll])

  const handleSaveSettings = async (newSettings) => {
    const ok = r => { if (!r.ok) throw new Error(r.status); return r.json() }
    const saved = await fetch(api('/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newSettings),
    }).then(ok)
    setSettings(saved)
  }

  const handleStop = async () => {
    await fetch(api('/stop'), { method: 'POST' }).catch(() => {})
    setTimeout(fetchAll, 1000)
  }

  const handleStart = async () => {
    if (botStarting) return
    setBotStarting(true)
    try {
      const useMock = config.use_mock ?? true
      const dryRun  = config.dry_run  ?? true
      await fetch(api(`/start?dry_run=${dryRun}&use_mock=${useMock}`), { method: 'POST' }).catch(() => {})
      // Poll fino a 15 × 800ms = 12s per dare tempo al subprocess di avviarsi
      for (let i = 0; i < 15; i++) {
        await new Promise(r => setTimeout(r, 800))
        try {
          const s = await fetch(api('/status')).then(r => r.json())
          setStatus(s)
          if (s?.running || s?.phase === 'error' || s?.phase === 'idle') break
        } catch {}
      }
      fetchAll()
    } finally {
      setBotStarting(false)
    }
  }

  const running  = status?.running
  const phase    = status?.phase ?? 'offline'
  const phaseColor = {
    scanning: 'text-blue-400', analyzing: 'text-purple-400', idle: 'text-gray-400',
    stopped: 'text-red-400', error: 'text-red-500', offline: 'text-gray-600',
  }

  const strategyLabel = {
    ema_rsi_ai_main:  'AI Main (full — 3 stadi + web)',
    ema_rsi_ai:       'AI Standard (3 stadi)',
    ema_rsi_ai_scalp: 'AI Scalping (Stage1+3)',
    ema_rsi_manual:   'Manuale (regole pure)',
  }[botMeta?.strategy] ?? botMeta?.strategy ?? '—'

  return (
    <div className="space-y-3 sm:space-y-4">

      {/* Header bot */}
      <FadeIn delay={0}>
        <GlowCard glow="none" className="py-3 px-4">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <button onClick={onBack}
                className="text-terminal-muted hover:text-white text-xs font-mono px-2 py-1
                  border border-terminal-border rounded-lg hover:border-blue-500/50 transition-colors">
                ← Grid
              </button>
              <StatusDot active={running} />
              <span className="font-mono font-bold text-sm text-white">{botMeta?.symbol ?? botId}</span>
              <span className="text-[10px] text-terminal-muted font-mono">{strategyLabel}</span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                status?.dry_run
                  ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                  : 'bg-green-500/10 border-green-500/30 text-green-400'
              }`}>
                {status?.dry_run ? 'DRY RUN' : 'LIVE'}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs font-mono">
              {status?.price && <span className="text-white font-bold">{status.price}</span>}
              <span className={`font-bold ${phaseColor[phase] || 'text-gray-400'}`}>{phase.toUpperCase()}</span>
              {lastUpdate && <span className="text-terminal-muted hidden sm:block">{fmt(lastUpdate)}</span>}
            </div>
            <div className="flex items-center gap-2">
              {running ? (
                <button onClick={handleStop}
                  className="px-3 py-1.5 text-[11px] font-mono rounded-lg
                    bg-red-500/10 border border-red-500/30 text-red-400
                    hover:bg-red-500/20 transition-colors">
                  ■ Stop
                </button>
              ) : (
                <button disabled={botStarting} onClick={handleStart}
                  className="px-3 py-1.5 text-[11px] font-mono rounded-lg
                    bg-green-500/10 border border-green-500/30 text-green-400
                    hover:bg-green-500/20 transition-colors disabled:opacity-50">
                  {botStarting ? '…' : '▶ Start'}
                </button>
              )}
            </div>
          </div>
          {error && (
            <div className="mt-2 text-[11px] text-red-400 font-mono bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}
        </GlowCard>
      </FadeIn>

      {/* Tab Nav */}
      <FadeIn delay={0.03}>
        <TabNav active={tab} onChange={setTab} />
      </FadeIn>

      {/* Page content */}
      <AnimatePresence mode="wait">
        <motion.div key={tab}
          initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.2, ease: 'easeInOut' }}>

          {tab === 'market' && (
            <div className="space-y-3 sm:space-y-4">
              <FadeIn delay={0.05}>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <MetricCard label="Win Rate" value={stats?.win_rate ?? 0} suffix="%" decimals={1}
                    color={(stats?.win_rate ?? 0) >= 50 ? 'text-green-400' : 'text-red-400'}
                    glow={(stats?.win_rate ?? 0) >= 50 ? 'green' : 'red'}
                    sub={`${stats?.trades_with_result ?? 0} trade con risultato`} />
                  <MetricCard label="P&L Totale" value={stats?.total_pnl ?? 0} prefix="$" decimals={2}
                    color={(stats?.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}
                    glow={(stats?.total_pnl ?? 0) >= 0 ? 'green' : 'red'}
                    sub={`${stats?.executed ?? 0} trade eseguiti`} />
                  <MetricCard label="Confidenza media" value={stats?.avg_confidence ?? 0} suffix="%" decimals={1}
                    color="text-blue-400" glow="blue" sub="su tutte le analisi" />
                  <MetricCard label="Tasso HOLD" value={stats?.hold_rate ?? 0} suffix="%" decimals={1}
                    color="text-amber-400" glow="amber"
                    sub={`${stats?.holds ?? 0} / ${stats?.total ?? 0} analisi`} />
                </div>
              </FadeIn>
              <FadeIn delay={0.1}>
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                  <div className="lg:col-span-2"><CurrentStatePanel status={status} journal={journal} /></div>
                  <ConfidenceChart journal={journal} minConfidence={settings?.min_confidence ?? 70} />
                </div>
              </FadeIn>
              <FadeIn delay={0.15}><DecisionTable journal={journal} /></FadeIn>
            </div>
          )}

          {tab === 'control' && (
            <div className="space-y-3 sm:space-y-4">
              <FadeIn delay={0.05}>
                <ModeControl config={config} botRunning={status?.running}
                  onUpdate={cfg => setConfig(c => ({ ...c, ...cfg }))}
                  botId={botId} />
              </FadeIn>
              <FadeIn delay={0.1}><LogPanel tall botId={botId} /></FadeIn>
            </div>
          )}

          {tab === 'stats' && (
            <div className="space-y-3 sm:space-y-4">
              <FadeIn delay={0.05}>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  <MetricCard label="Trade totali" value={stats?.executed ?? 0} decimals={0}
                    color="text-white" glow="blue" sub={`${stats?.trades_with_result ?? 0} con risultato`} />
                  <MetricCard label="Win Rate" value={stats?.win_rate ?? 0} suffix="%" decimals={1}
                    color={(stats?.win_rate ?? 0) >= 50 ? 'text-green-400' : 'text-red-400'}
                    glow={(stats?.win_rate ?? 0) >= 50 ? 'green' : 'red'} />
                  <MetricCard label="P&L netto" value={stats?.total_pnl ?? 0} prefix="$" decimals={2}
                    color={(stats?.total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400'}
                    glow={(stats?.total_pnl ?? 0) >= 0 ? 'green' : 'red'} />
                  <MetricCard label="Avg Confidenza" value={stats?.avg_confidence ?? 0} suffix="%" decimals={1}
                    color="text-blue-400" glow="blue" />
                </div>
              </FadeIn>
              <FadeIn delay={0.1}>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  <PnlChart journal={journal} />
                  <CostPanel costs={costs} />
                </div>
              </FadeIn>
            </div>
          )}

          {tab === 'settings' && (
            <FadeIn delay={0.05}>
              <SettingsPanel settings={settings} onSave={handleSaveSettings} />
            </FadeIn>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
