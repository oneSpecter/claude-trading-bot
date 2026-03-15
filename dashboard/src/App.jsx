import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip as RechartTooltip,
  ResponsiveContainer, ReferenceLine, BarChart, Bar, Cell,
} from 'recharts'
import LogPanel        from './components/LogPanel'
import ModeControl     from './components/ModeControl'
import SettingsPanel   from './components/SettingsPanel'
import {
  GlowCard, Label, AnimatedNumber, Tooltip, InfoIcon,
  StatusDot, DecBadge,
} from './components/ui'

const POLL_MS = 5000

function fmt(ts) {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) }
  catch { return '—' }
}
// ── Fade-in wrapper ───────────────────────────────────────────────
const FadeIn = ({ children, delay = 0 }) => (
  <motion.div
    initial={{ opacity: 0, y: 12 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.4, delay, ease: 'easeOut' }}
  >
    {children}
  </motion.div>
)

// ── Metric Card ──────────────────────────────────────────────────
function MetricCard({ label, value, sub, color = 'text-white', glow, tooltip, prefix = '', suffix = '', decimals = 1 }) {
  return (
    <GlowCard glow={glow || 'blue'} className="flex flex-col gap-1">
      <Label className="mb-1">
        {tooltip ? (
          <Tooltip text={tooltip}>
            <span>{label}</span>
            <InfoIcon />
          </Tooltip>
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

// ── Confidence Chart ─────────────────────────────────────────────
function ConfidenceChart({ journal, minConfidence = 70 }) {
  if (!journal?.length) return (
    <GlowCard className="flex items-center justify-center h-40 text-terminal-muted text-xs font-mono">
      Nessun dato ancora
    </GlowCard>
  )
  const data = [...journal].reverse().slice(-40).map(e => ({
    t:    fmt(e.timestamp),
    conf: e.confidence ?? 0,
    dec:  e.decision,
  }))
  const dotColor = d => d === 'BUY' ? '#22c55e' : d === 'SELL' ? '#ef4444' : '#f59e0b'
  return (
    <GlowCard glow="blue">
      <Label>
        <Tooltip text="Confidenza del modello AI per ogni analisi. Sopra la linea tratteggiata (65%) il bot può aprire trade.">
          <span>Confidenza ultime 40 analisi</span>
          <InfoIcon />
        </Tooltip>
      </Label>
      <ResponsiveContainer width="100%" height={130}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="confGrad" x1="0" y1="0" x2="0" y2="1">
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
          <ReferenceLine y={minConfidence} stroke="#f59e0b" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: `${minConfidence}%`, position: 'insideTopRight', fill: '#f59e0b', fontSize: 9 }} />
          <Area type="monotone" dataKey="conf" stroke="#3b82f6" strokeWidth={1.5}
            fill="url(#confGrad)"
            dot={({ cx, cy, payload }) => (
              <circle key={`d${cx}`} cx={cx} cy={cy} r={3}
                fill={dotColor(payload.dec)} stroke="none" />
            )}
          />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2 text-[10px] text-terminal-muted">
        <span><span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1" />BUY</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-red-500 mr-1" />SELL</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-amber-500 mr-1" />HOLD</span>
        <span className="ml-auto hidden sm:block">— soglia {minConfidence}%</span>
      </div>
    </GlowCard>
  )
}

// ── Top Bar ──────────────────────────────────────────────────────
function TopBar({ status, lastUpdate, error, onStop, onStart }) {
  const [btnLoading, setBtnLoading] = useState(false)
  const [btnMsg,     setBtnMsg]     = useState('')
  const [countdown,  setCountdown]  = useState(null)

  const running  = status?.running
  const phase    = status?.phase ?? 'offline'
  const dryRun   = status?.dry_run
  const price    = status?.price
  const h4       = status?.h4_bias

  // Countdown live al prossimo tick (aggiorna ogni secondo)
  useEffect(() => {
    if (!running || !status?.timestamp) { setCountdown(null); return }
    const interval = status.check_interval ?? 300
    const tick = () => {
      const elapsed  = (Date.now() - new Date(status.timestamp)) / 1000
      const remaining = Math.max(0, Math.round(interval - elapsed))
      setCountdown(remaining)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [running, status?.timestamp, status?.check_interval])

  const handleAction = async (fn, label) => {
    setBtnLoading(true)
    setBtnMsg(label)
    try { await fn() } catch {}
    setTimeout(() => { setBtnLoading(false); setBtnMsg('') }, 2000)
  }

  const phaseColor = {
    scanning:  'text-blue-400',
    analyzing: 'text-purple-400',
    idle:      'text-gray-400',
    stopped:   'text-red-400',
    error:     'text-red-500',
    offline:   'text-gray-600',
  }

  return (
    <GlowCard glow="none" className="py-3 px-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">

        {/* Brand */}
        <div className="flex items-center gap-3">
          <StatusDot active={running} />
          <span className="font-mono font-bold text-sm text-white tracking-wide">
            FOREX AI BOT
          </span>
          {dryRun !== undefined && (
            <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
              dryRun
                ? 'bg-amber-500/10 border-amber-500/30 text-amber-400'
                : 'bg-green-500/10 border-green-500/30 text-green-400'
            }`}>
              {dryRun ? 'DRY RUN' : 'LIVE DEMO'}
            </span>
          )}
        </div>

        {/* Market data */}
        <div className="flex items-center gap-5 text-xs font-mono">
          {price && (
            <div className="flex flex-col items-end">
              <span className="text-[9px] text-terminal-muted uppercase">EUR/USD</span>
              <span className="text-white font-bold">{price}</span>
            </div>
          )}
          {h4 && h4 !== 'N/A' && (
            <div className="flex flex-col items-end">
              <span className="text-[9px] text-terminal-muted uppercase">H4 Bias</span>
              <span className={`font-bold ${h4 === 'BULLISH' ? 'text-green-400' : h4 === 'BEARISH' ? 'text-red-400' : 'text-gray-400'}`}>
                {h4}
              </span>
            </div>
          )}
          <div className="flex flex-col items-end">
            <span className="text-[9px] text-terminal-muted uppercase">Fase</span>
            <span className={`font-bold ${phaseColor[phase] || 'text-gray-400'}`}>
              {phase.toUpperCase()}
            </span>
          </div>
          {countdown !== null && (
            <div className="flex flex-col items-end">
              <span className="text-[9px] text-terminal-muted uppercase">Prossimo tick</span>
              <span className={`font-mono font-bold tabular-nums ${
                countdown <= 30 ? 'text-amber-400' : 'text-white'
              }`}>
                {Math.floor(countdown / 60)}:{String(countdown % 60).padStart(2, '0')}
              </span>
            </div>
          )}
          {lastUpdate && (
            <div className="flex flex-col items-end hidden sm:flex">
              <span className="text-[9px] text-terminal-muted uppercase">Aggiornato</span>
              <span className="text-terminal-muted">{fmt(lastUpdate)}</span>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          {btnMsg && (
            <span className="text-[10px] font-mono text-terminal-muted animate-pulse">
              {btnMsg}
            </span>
          )}
          {running ? (
            <button
              disabled={btnLoading}
              onClick={() => handleAction(onStop, 'Stop in corso…')}
              className="px-3 py-1.5 text-[11px] font-mono rounded-lg
                bg-red-500/10 border border-red-500/30 text-red-400
                hover:bg-red-500/20 transition-colors disabled:opacity-50">
              {btnLoading ? '…' : '■ Stop'}
            </button>
          ) : (
            <button
              disabled={btnLoading}
              onClick={() => handleAction(onStart, 'Avvio in corso…')}
              className="px-3 py-1.5 text-[11px] font-mono rounded-lg
                bg-green-500/10 border border-green-500/30 text-green-400
                hover:bg-green-500/20 transition-colors disabled:opacity-50">
              {btnLoading ? '…' : '▶ Start'}
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
  )
}

// ── Tab Nav ───────────────────────────────────────────────────────
const TABS = [
  { id: 'market',   label: 'Mercato',       icon: '📊' },
  { id: 'control',  label: 'Controllo',     icon: '🎛️' },
  { id: 'stats',    label: 'Statistiche',   icon: '📈' },
  { id: 'settings', label: 'Impostazioni',  icon: '⚙️' },
]

function TabNav({ active, onChange }) {
  return (
    <div className="flex gap-1 bg-terminal-card border border-terminal-border rounded-xl p-1">
      {TABS.map(tab => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`relative flex-1 flex items-center justify-center gap-2 px-4 py-2
            text-[11px] font-mono rounded-lg transition-all duration-200
            ${active === tab.id
              ? 'text-white'
              : 'text-terminal-muted hover:text-gray-300'
            }`}
        >
          {active === tab.id && (
            <motion.div
              layoutId="tab-pill"
              className="absolute inset-0 bg-blue-500/15 border border-blue-500/30 rounded-lg"
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
            />
          )}
          <span className="relative z-10 text-base leading-none">{tab.icon}</span>
          <span className="relative z-10 hidden sm:inline tracking-wide">{tab.label}</span>
        </button>
      ))}
    </div>
  )
}

// ── Decision Table ───────────────────────────────────────────────
function DecisionTable({ journal }) {
  const rows = journal.slice(0, 15)
  if (!rows.length) return (
    <GlowCard className="flex items-center justify-center h-28 text-terminal-muted text-xs font-mono">
      Nessuna decisione ancora
    </GlowCard>
  )
  return (
    <GlowCard glow="none">
      <Label>
        <Tooltip text="Ultime 15 decisioni del bot. 'Changed' indica quando il Devil's Advocate ha cambiato la decisione iniziale.">
          <span>Ultime decisioni</span>
          <InfoIcon />
        </Tooltip>
      </Label>
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
              <th className="text-right pb-2">P&L</th>
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

// ── Current State Panel ──────────────────────────────────────────
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
            tip: 'Direzione del trend rilevata dal crossover EMA 9/21 sull\'H1.' },
          { label: 'RSI (14)', value: rsi != null ? rsi.toFixed(1) : '—',
            color: rsi > 70 ? 'text-red-400' : rsi < 30 ? 'text-green-400' : 'text-white',
            tip: 'Relative Strength Index. > 70 = ipercomprato. < 30 = ipervenduto. Range 45-55 = neutro.' },
          { label: 'ADX (14)', value: adx != null ? adx.toFixed(1) : '—',
            color: adx >= 25 ? 'text-green-400' : 'text-amber-400',
            tip: 'Average Directional Index: misura la FORZA del trend (non la direzione). ≥ 25 = trending, < 25 = ranging (bot non apre trade).' },
          { label: 'H4 Bias', value: status?.h4_bias ?? '—',
            color: status?.h4_bias === 'BULLISH' ? 'text-green-400' : status?.h4_bias === 'BEARISH' ? 'text-red-400' : 'text-gray-400',
            tip: 'Direzione del trend principale su H4 (timeframe superiore). Il bot non apre trade contro questo bias.' },
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
              <span className="text-[10px] font-mono text-terminal-muted ml-auto">
                {last.confidence}% conf
              </span>
            )}
          </div>
          {last.reasoning && (
            <p className="text-[11px] text-gray-300 leading-relaxed line-clamp-2">
              {last.reasoning}
            </p>
          )}
        </div>
      )}
    </GlowCard>
  )
}

// ── Cost Panel ───────────────────────────────────────────────────
function CostPanel({ costs }) {
  const byStage = costs?.by_stage ?? {}
  const entries = Object.entries(byStage).sort((a, b) => b[1] - a[1])
  return (
    <GlowCard glow="none">
      <Label>
        <Tooltip text="Costi Claude API accumulati. Stage1=analisi tecnica, Stage2=web search notizie, Stage3=decisione finale, exit_check=gestione posizioni aperte.">
          <span>Costi API Claude</span>
          <InfoIcon />
        </Tooltip>
      </Label>
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div>
          <div className="text-[9px] text-terminal-muted uppercase mb-1">Oggi</div>
          <div className="text-lg font-mono font-bold text-white">
            ${(costs?.today_cost ?? 0).toFixed(3)}
          </div>
        </div>
        <div>
          <div className="text-[9px] text-terminal-muted uppercase mb-1">Mese</div>
          <div className="text-lg font-mono font-bold text-blue-400">
            ${(costs?.month_cost ?? 0).toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-[9px] text-terminal-muted uppercase mb-1">Totale</div>
          <div className="text-lg font-mono font-bold text-terminal-muted">
            ${(costs?.total_cost ?? 0).toFixed(2)}
          </div>
        </div>
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
                  <motion.div
                    className="h-full bg-blue-500/60 rounded-full"
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </GlowCard>
  )
}

// ── P&L Chart ────────────────────────────────────────────────────
function PnlChart({ journal }) {
  if (!journal?.length) return null
  // Calcola P&L cumulativo nel tempo
  const trades = [...journal]
    .filter(e => e.profit != null)
    .reverse()
  if (!trades.length) return null

  let cum = 0
  const data = trades.map(e => {
    cum += e.profit
    return { t: fmt(e.timestamp), cum: parseFloat(cum.toFixed(2)), pnl: e.profit }
  })

  return (
    <GlowCard glow="green">
      <Label>P&L cumulativo</Label>
      <ResponsiveContainer width="100%" height={120}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -10, bottom: 0 }}>
          <defs>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#22c55e" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0}   />
            </linearGradient>
          </defs>
          <XAxis dataKey="t" tick={{ fill: '#6b7fa3', fontSize: 8 }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fill: '#6b7fa3', fontSize: 8 }} tickLine={false} axisLine={false} />
          <RechartTooltip
            contentStyle={{ backgroundColor: '#0a1020', border: '1px solid #1a2744', fontSize: 11, borderRadius: 8 }}
            formatter={(v) => [`$${v}`, 'P&L cumulativo']}
          />
          <ReferenceLine y={0} stroke="#6b7fa3" strokeOpacity={0.4} />
          <Area type="monotone" dataKey="cum" stroke="#22c55e" strokeWidth={1.5} fill="url(#pnlGrad)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </GlowCard>
  )
}

// ── Decision Distribution Bar ─────────────────────────────────────
function DecisionDistribution({ stats }) {
  const total  = stats?.total ?? 0
  if (!total) return null
  const buys  = stats?.buys  ?? 0
  const sells = stats?.sells ?? 0
  const holds = stats?.holds ?? 0

  const bars = [
    { label: 'BUY',  count: buys,  color: '#22c55e', bg: 'bg-green-500/60' },
    { label: 'SELL', count: sells, color: '#ef4444', bg: 'bg-red-500/60'   },
    { label: 'HOLD', count: holds, color: '#f59e0b', bg: 'bg-amber-500/60' },
  ]

  return (
    <GlowCard glow="none">
      <Label>Distribuzione decisioni</Label>
      <div className="space-y-3">
        {bars.map(b => (
          <div key={b.label}>
            <div className="flex justify-between text-[10px] font-mono mb-1">
              <span className="text-terminal-muted">{b.label}</span>
              <span className="text-white">{b.count} <span className="text-terminal-muted">/ {total}</span></span>
            </div>
            <div className="h-2 bg-terminal-border rounded-full overflow-hidden">
              <motion.div
                className={`h-full ${b.bg} rounded-full`}
                initial={{ width: 0 }}
                animate={{ width: `${total > 0 ? b.count / total * 100 : 0}%` }}
                transition={{ duration: 0.8, ease: 'easeOut' }}
              />
            </div>
          </div>
        ))}
      </div>
    </GlowCard>
  )
}

// ── Page: Mercato ─────────────────────────────────────────────────
function PageMercato({ status, journal, stats, settings }) {
  const winRate  = stats?.win_rate   ?? 0
  const pnl      = stats?.total_pnl  ?? 0
  const holdRate = stats?.hold_rate  ?? 0
  const avgConf  = stats?.avg_confidence ?? 0
  const executed = stats?.executed   ?? 0
  const withRes  = stats?.trades_with_result ?? 0

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* Stats Row */}
      <FadeIn delay={0.05}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard
            label="Win Rate"
            value={winRate} suffix="%" decimals={1}
            color={winRate >= 50 ? 'text-green-400' : winRate >= 40 ? 'text-amber-400' : 'text-red-400'}
            glow={winRate >= 50 ? 'green' : 'amber'}
            tooltip="Percentuale di trade chiusi in profitto. Target ≥ 50%."
            sub={`${withRes} trade con risultato`}
          />
          <MetricCard
            label="P&L Totale"
            value={pnl} prefix="$" decimals={2}
            color={pnl > 0 ? 'text-green-400' : pnl < 0 ? 'text-red-400' : 'text-white'}
            glow={pnl >= 0 ? 'green' : 'red'}
            tooltip="Profitto/perdita totale accumulato su tutti i trade chiusi."
            sub={`${executed} trade eseguiti`}
          />
          <MetricCard
            label="Confidenza media"
            value={avgConf} suffix="%" decimals={1}
            color={avgConf >= 70 ? 'text-blue-400' : 'text-white'}
            glow="blue"
            tooltip="Media della confidenza AI. Soglia minima per tradare: 65%."
            sub="su tutte le analisi"
          />
          <MetricCard
            label="Tasso HOLD"
            value={holdRate} suffix="%" decimals={1}
            color="text-amber-400"
            glow="amber"
            tooltip="% analisi dove il bot ha deciso HOLD. 60-80% è normale — il bot è selettivo."
            sub={`${stats?.holds ?? 0} HOLD / ${stats?.total ?? 0} analisi`}
          />
        </div>
      </FadeIn>

      {/* Stato mercato + grafico confidenza */}
      <FadeIn delay={0.1}>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <div className="lg:col-span-2">
            <CurrentStatePanel status={status} journal={journal} />
          </div>
          <ConfidenceChart journal={journal} minConfidence={settings?.min_confidence ?? 70} />
        </div>
      </FadeIn>

      {/* Tabella decisioni */}
      <FadeIn delay={0.15}>
        <DecisionTable journal={journal} />
      </FadeIn>
    </div>
  )
}

// ── Page: Controllo ───────────────────────────────────────────────
function PageControllo({ status, config, onUpdate, onStart, onStop }) {
  const [btnLoading, setBtnLoading] = useState(false)
  const [btnMsg,     setBtnMsg]     = useState('')

  const running = status?.running

  const handleAction = async (fn, label) => {
    setBtnLoading(true)
    setBtnMsg(label)
    try { await fn() } catch {}
    setTimeout(() => { setBtnLoading(false); setBtnMsg('') }, 2000)
  }

  return (
    <div className="space-y-3 sm:space-y-4">
      <FadeIn delay={0.05}>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">

          {/* Modalità operativa */}
          <ModeControl
            config={config}
            botRunning={status?.running}
            onUpdate={onUpdate}
          />

          {/* Pannello avvio / stop con info stato */}
          <GlowCard glow="none">
            <Label>Controllo bot</Label>
            <div className="space-y-4">

              {/* Stato corrente */}
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Stato',   value: running ? 'In esecuzione' : 'Fermo',
                    color: running ? 'text-green-400' : 'text-red-400' },
                  { label: 'Fase',    value: (status?.phase ?? 'offline').toUpperCase(),
                    color: status?.phase === 'analyzing' ? 'text-purple-400' :
                           status?.phase === 'scanning'  ? 'text-blue-400'   : 'text-gray-400' },
                  { label: 'Modalità', value: config?.use_mock ? 'MOCK' : config?.dry_run ? 'WATCH' : 'TRADE',
                    color: config?.use_mock ? 'text-sky-400' : config?.dry_run ? 'text-amber-400' : 'text-green-400' },
                  { label: 'Prezzo',  value: status?.price ?? '—', color: 'text-white' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-terminal-bg/60 rounded-lg p-3 border border-terminal-border/50">
                    <div className="text-[9px] text-terminal-muted uppercase mb-1">{label}</div>
                    <div className={`text-sm font-mono font-bold ${color}`}>{value}</div>
                  </div>
                ))}
              </div>

              {/* Pulsante grande start/stop */}
              <div className="flex items-center gap-3">
                {btnMsg && (
                  <span className="text-[10px] font-mono text-terminal-muted animate-pulse flex-1">
                    {btnMsg}
                  </span>
                )}
                {running ? (
                  <button
                    disabled={btnLoading}
                    onClick={() => handleAction(onStop, 'Stop in corso…')}
                    className="flex-1 py-3 text-sm font-mono rounded-xl
                      bg-red-500/10 border border-red-500/30 text-red-400
                      hover:bg-red-500/20 transition-colors disabled:opacity-50">
                    {btnLoading ? '…' : '■ Ferma il bot'}
                  </button>
                ) : (
                  <button
                    disabled={btnLoading}
                    onClick={() => handleAction(onStart, 'Avvio in corso…')}
                    className="flex-1 py-3 text-sm font-mono rounded-xl
                      bg-green-500/10 border border-green-500/30 text-green-400
                      hover:bg-green-500/20 transition-colors disabled:opacity-50">
                    {btnLoading ? '…' : '▶ Avvia il bot'}
                  </button>
                )}
              </div>

              <p className="text-[10px] text-terminal-muted leading-relaxed">
                Il bot si ferma al prossimo tick (max 5 min). Cambio WATCH↔TRADE attivo al tick successivo senza riavvio.
              </p>
            </div>
          </GlowCard>
        </div>
      </FadeIn>

      {/* Log panel — più grande in questa pagina */}
      <FadeIn delay={0.1}>
        <LogPanel tall />
      </FadeIn>
    </div>
  )
}

// ── Page: Statistiche ─────────────────────────────────────────────
function PageStatistiche({ stats, costs, journal, settings }) {
  const winRate   = stats?.win_rate   ?? 0
  const pnl       = stats?.total_pnl  ?? 0
  const executed  = stats?.executed   ?? 0
  const withRes   = stats?.trades_with_result ?? 0
  const avgConf   = stats?.avg_confidence ?? 0

  // Stima proiezione mensile costi
  const todayCost = costs?.today_cost ?? 0
  const monthCost = costs?.month_cost ?? 0

  return (
    <div className="space-y-3 sm:space-y-4">

      {/* Metriche performance */}
      <FadeIn delay={0.05}>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard
            label="Trade totali"
            value={executed} decimals={0}
            color="text-white" glow="blue"
            tooltip="Numero totale di trade eseguiti (BUY + SELL)."
            sub={`${withRes} con risultato`}
          />
          <MetricCard
            label="Win Rate"
            value={winRate} suffix="%" decimals={1}
            color={winRate >= 50 ? 'text-green-400' : 'text-red-400'}
            glow={winRate >= 50 ? 'green' : 'red'}
            tooltip="% trade chiusi in profitto."
          />
          <MetricCard
            label="P&L netto"
            value={pnl} prefix="$" decimals={2}
            color={pnl >= 0 ? 'text-green-400' : 'text-red-400'}
            glow={pnl >= 0 ? 'green' : 'red'}
            tooltip="Profitto/perdita totale in dollari."
          />
          <MetricCard
            label="Avg Confidenza"
            value={avgConf} suffix="%" decimals={1}
            color="text-blue-400" glow="blue"
            tooltip="Media della confidenza AI su tutte le analisi."
          />
        </div>
      </FadeIn>

      {/* P&L chart + distribuzione */}
      <FadeIn delay={0.1}>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <PnlChart journal={journal} />
          <DecisionDistribution stats={stats} />
        </div>
      </FadeIn>

      {/* Costi API estesi */}
      <FadeIn delay={0.15}>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          <CostPanel costs={costs} />

          {/* Proiezioni e info modello */}
          <GlowCard glow="none">
            <Label>Info modello & proiezioni</Label>
            <div className="space-y-3">

              <div className="bg-terminal-bg/60 rounded-lg p-3 border border-terminal-border/50">
                <div className="text-[9px] text-terminal-muted uppercase mb-2">Costo stimato mensile</div>
                <div className="text-xl font-mono font-bold text-blue-400">
                  ${(monthCost > 0 ? monthCost : todayCost * 22).toFixed(2)}
                  <span className="text-[10px] text-terminal-muted ml-2 font-normal">
                    {monthCost > 0 ? 'mese corrente' : 'proiezione (22 giorni lavorativi)'}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                {[
                  { label: 'Stage 1 (tecnico)',  desc: 'Ogni tick con segnale' },
                  { label: 'Stage 2 (notizie)',  desc: `Solo se score ≥ ${settings?.web_search_min_score ?? 60}` },
                  { label: 'Stage 3 (decisione)',desc: 'Dopo stage 2' },
                  { label: 'Exit check',         desc: 'Ogni tick, posizioni aperte' },
                ].map(({ label, desc }) => (
                  <div key={label} className="bg-terminal-bg/60 rounded-lg p-2 border border-terminal-border/50">
                    <div className="text-white mb-0.5">{label}</div>
                    <div className="text-terminal-muted text-[9px]">{desc}</div>
                  </div>
                ))}
              </div>

              <div className="text-[10px] text-terminal-muted leading-relaxed bg-terminal-bg/40 rounded-lg p-3 border border-terminal-border/40">
                Prompt caching attivo → −70% token fissi. Web search gate a score 65 riduce le chiamate Stage 2 costose.
              </div>
            </div>
          </GlowCard>
        </div>
      </FadeIn>
    </div>
  )
}

// ── Main App ─────────────────────────────────────────────────────
export default function App() {
  const [tab,        setTab]        = useState('market')
  const [status,     setStatus]     = useState(null)
  const [journal,    setJournal]    = useState([])
  const [stats,      setStats]      = useState({})
  const [costs,      setCosts]      = useState({})
  const [config,     setConfig]     = useState({ dry_run: true })
  const [settings,   setSettings]   = useState({})
  const [lastUpdate, setLastUpdate] = useState(null)
  const [error,      setError]      = useState(null)

  const fetchAll = useCallback(async () => {
    try {
      const ok = r => { if (!r.ok) throw new Error(r.status); return r.json() }
      const [s, j, st, c, cfg, sett] = await Promise.all([
        fetch('/api/status').then(ok),
        fetch('/api/journal?limit=100').then(ok),
        fetch('/api/stats').then(ok),
        fetch('/api/costs').then(ok),
        fetch('/api/config').then(ok),
        fetch('/api/settings').then(ok),
      ])
      setStatus(s); setJournal(j); setStats(st); setCosts(c); setConfig(cfg); setSettings(sett)
      setLastUpdate(new Date()); setError(null)
    } catch {
      setError('Server non raggiungibile — avvia: uvicorn server:app --host 0.0.0.0 --port 8000')
    }
  }, [])

  useEffect(() => {
    fetchAll()
    const id = setInterval(fetchAll, POLL_MS)
    return () => clearInterval(id)
  }, [fetchAll])

  const handleSaveSettings = async (newSettings) => {
    const ok = r => { if (!r.ok) throw new Error(r.status); return r.json() }
    const saved = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newSettings),
    }).then(ok)
    setSettings(saved)
  }

  const handleStop = async () => {
    await fetch('/api/bot/stop', { method: 'POST' }).catch(() => {})
    setTimeout(fetchAll, 1000)
  }
  const handleStart = async () => {
    // Ri-legge il config dal server nell'istante dell'avvio
    // per evitare stato React stale (es: mode appena cambiata ma fetch non ancora tornato)
    let cfg = config
    try {
      const fresh = await fetch('/api/config').then(r => r.json())
      cfg = fresh
      setConfig(fresh)
    } catch { /* usa cache React se server non raggiungibile */ }
    const useMock = cfg.use_mock ?? true
    const dryRun  = cfg.dry_run  ?? true
    await fetch(`/api/bot/start?dry_run=${dryRun}&use_mock=${useMock}`, { method: 'POST' }).catch(() => {})
    setTimeout(fetchAll, 1000)
  }

  const tabVariants = {
    initial:  { opacity: 0, y: 8  },
    animate:  { opacity: 1, y: 0  },
    exit:     { opacity: 0, y: -8 },
  }

  return (
    <div className="min-h-screen bg-terminal-bg text-gray-100 font-mono bg-grid-pattern bg-grid">
      {/* Scan line effect */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0 opacity-[0.015]">
        <div className="absolute w-full h-0.5 bg-blue-400 animate-scan" />
      </div>

      <div className="relative z-10 max-w-screen-xl mx-auto p-3 sm:p-5 space-y-3 sm:space-y-4">

        {/* Top Bar — sempre visibile */}
        <FadeIn delay={0}>
          <TopBar
            status={status}
            lastUpdate={lastUpdate}
            error={error}
            onStop={handleStop}
            onStart={handleStart}
          />
        </FadeIn>

        {/* Tab Nav */}
        <FadeIn delay={0.03}>
          <TabNav active={tab} onChange={setTab} />
        </FadeIn>

        {/* Page Content */}
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            variants={tabVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            transition={{ duration: 0.2, ease: 'easeInOut' }}
          >
            {tab === 'market'   && <PageMercato     status={status} journal={journal} stats={stats} settings={settings} />}
            {tab === 'control'  && <PageControllo   status={status} config={config} onUpdate={cfg => setConfig(c => ({ ...c, ...cfg }))} onStart={handleStart} onStop={handleStop} />}
            {tab === 'stats'    && <PageStatistiche stats={stats} costs={costs} journal={journal} settings={settings} />}
            {tab === 'settings' && (
              <div className="space-y-3 sm:space-y-4">
                <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: 'easeOut' }}>
                  <SettingsPanel settings={settings} onSave={handleSaveSettings} />
                </motion.div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>

      </div>
    </div>
  )
}
