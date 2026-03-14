const MONTHLY_BUDGET = 11 // $11/mese stimato

function fmt(v) {
  if (v == null) return '—'
  return `$${Number(v).toFixed(4)}`
}

function BudgetBar({ used, budget }) {
  const pct = Math.min(100, (used / budget) * 100)
  const color = pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-amber-500' : 'bg-green-500'
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-terminal-muted">Budget mensile</span>
        <span className="text-white">{fmt(used)} / ${budget}</span>
      </div>
      <div className="w-full bg-terminal-border rounded-full h-1.5">
        <div className={`h-1.5 rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="text-right text-xs text-terminal-muted mt-0.5">{pct.toFixed(1)}%</div>
    </div>
  )
}

function StageRow({ stage, cost }) {
  const color = stage === 'stage2' ? 'text-purple-400' : stage === 'stage1' ? 'text-sky-400' : 'text-amber-400'
  const label = { stage1: 'Stage 1 — Tecnico', stage2: 'Stage 2 — Web Search', stage3: 'Stage 3 — Decisione' }[stage] ?? stage
  return (
    <div className="flex justify-between text-xs py-1 border-b border-terminal-border/50">
      <span className={color}>{label}</span>
      <span className="text-white tabular-nums">{fmt(cost)}</span>
    </div>
  )
}

export default function CostPanel({ costs }) {
  const { total_cost, total_calls, today_cost, month_cost, by_stage, last_calls } = costs ?? {}

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-5 space-y-4">
      <div className="text-xs text-terminal-muted uppercase tracking-wider">Consumo API</div>

      {/* Top numbers */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <div className="text-xs text-terminal-muted mb-0.5">Oggi</div>
          <div className="text-lg font-bold text-white tabular-nums">{fmt(today_cost)}</div>
        </div>
        <div>
          <div className="text-xs text-terminal-muted mb-0.5">Mese</div>
          <div className="text-lg font-bold text-green-400 tabular-nums">{fmt(month_cost)}</div>
        </div>
        <div>
          <div className="text-xs text-terminal-muted mb-0.5">Totale</div>
          <div className="text-lg font-bold text-terminal-muted tabular-nums">{fmt(total_cost)}</div>
        </div>
      </div>

      {/* Budget bar */}
      <BudgetBar used={month_cost ?? 0} budget={MONTHLY_BUDGET} />

      {/* By stage */}
      {by_stage && Object.keys(by_stage).length > 0 && (
        <div>
          <div className="text-xs text-terminal-muted mb-2">Per stadio (totale)</div>
          {['stage1', 'stage2', 'stage3'].map(s =>
            by_stage[s] != null ? <StageRow key={s} stage={s} cost={by_stage[s]} /> : null
          )}
        </div>
      )}

      {/* Calls count */}
      <div className="text-xs text-terminal-muted text-right">
        {total_calls ?? 0} chiamate totali
      </div>
    </div>
  )
}
