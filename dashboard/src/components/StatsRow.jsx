function StatCard({ label, value, sub, color = 'text-white' }) {
  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg px-5 py-4 flex-1">
      <div className="text-xs text-terminal-muted mb-1 uppercase tracking-wider">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value ?? '—'}</div>
      {sub && <div className="text-xs text-terminal-muted mt-1">{sub}</div>}
    </div>
  )
}

export default function StatsRow({ stats }) {
  const {
    total, executed, avg_confidence, hold_rate,
    web_search_rate, buys, sells,
    win_rate, total_pnl, trades_with_result,
  } = stats ?? {}

  const pnlColor = total_pnl > 0 ? 'text-green-400' : total_pnl < 0 ? 'text-red-400' : 'text-white'
  const pnlValue = total_pnl != null
    ? `${total_pnl >= 0 ? '+' : ''}$${total_pnl.toFixed(2)}`
    : '—'

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <StatCard
        label="Analisi totali"
        value={total}
        sub={`${buys ?? 0} BUY · ${sells ?? 0} SELL`}
      />
      <StatCard
        label="Trade eseguiti"
        value={executed}
        sub={total ? `${((executed / total) * 100).toFixed(0)}% exec rate` : undefined}
        color="text-sky-400"
      />
      <StatCard
        label="Win rate"
        value={win_rate != null && trades_with_result > 0 ? `${win_rate}%` : '—'}
        sub={trades_with_result ? `${trades_with_result} trade con risultato` : 'nessun risultato ancora'}
        color={win_rate >= 50 ? 'text-green-400' : win_rate > 0 ? 'text-red-400' : 'text-terminal-muted'}
      />
      <StatCard
        label="PnL totale"
        value={pnlValue}
        sub={trades_with_result ? `su ${trades_with_result} trade` : undefined}
        color={pnlColor}
      />
      <StatCard
        label="Confidenza media"
        value={avg_confidence != null ? `${avg_confidence}%` : '—'}
        sub="target ≥ 65%"
        color={avg_confidence >= 65 ? 'text-green-400' : 'text-amber-400'}
      />
      <StatCard
        label="Hold rate"
        value={hold_rate != null ? `${hold_rate}%` : '—'}
        sub={`web search ${web_search_rate ?? '—'}%`}
        color="text-terminal-muted"
      />
    </div>
  )
}
