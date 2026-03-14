import DecisionBadge from './DecisionBadge'

function Indicator({ label, value, color = 'text-white' }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-xs text-terminal-muted uppercase tracking-wider">{label}</span>
      <span className={`text-lg font-bold ${color}`}>{value ?? '—'}</span>
    </div>
  )
}

function ConfBar({ value }) {
  const pct  = Math.min(100, Math.max(0, value ?? 0))
  const color = pct >= 75 ? 'bg-green-500' : pct >= 55 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="w-full bg-terminal-border rounded-full h-1.5 mt-1">
      <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  )
}

export default function CurrentState({ status, journal }) {
  const last    = journal?.[0]
  const price   = status?.price   ?? last?.price
  const trend   = status?.ema_trend ?? '—'
  const rsi     = status?.rsi     ?? '—'
  const adx     = status?.adx
  const adxTrend = status?.adx_trend ?? '—'
  const h4Bias  = status?.h4_bias
  const dec     = status?.last_decision   ?? last?.decision
  const conf    = status?.last_confidence ?? last?.confidence
  const regime  = status?.last_regime     ?? last?.market_regime
  const s1Score = status?.tech_score_s1
  const webDone = status?.web_search_done

  const trendColor = trend === 'RIALZISTA' ? 'text-green-400'
                   : trend === 'RIBASSISTA' ? 'text-red-400'
                   : 'text-terminal-muted'
  const adxColor   = adx >= 25 ? 'text-green-400' : 'text-amber-400'
  const rsiColor   = rsi > 70 ? 'text-red-400' : rsi < 30 ? 'text-green-400' : 'text-white'

  return (
    <div className="bg-terminal-card border border-terminal-border rounded-lg p-6">
      <div className="text-xs text-terminal-muted uppercase tracking-wider mb-4">
        Stato mercato attuale
      </div>

      {/* Mobile: prezzo + decisione in testa */}
      <div className="flex items-center justify-between mb-4 sm:hidden">
        <div>
          <div className="text-[10px] text-terminal-muted mb-0.5">PREZZO</div>
          <div className="text-2xl font-bold text-white tabular-nums">
            {price ? price.toFixed(5) : '—'}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {dec ? (
            <>
              <DecisionBadge decision={dec} size="lg" />
              {conf != null && (
                <span className="text-xs text-terminal-muted">{conf}% conf.</span>
              )}
            </>
          ) : (
            <span className="text-terminal-muted text-xs">nessuna decisione</span>
          )}
        </div>
      </div>

      {/* Mobile: indicatori in griglia 2 colonne */}
      <div className="grid grid-cols-2 gap-3 sm:hidden mb-3">
        <div className="bg-terminal-bg/60 rounded-lg p-3">
          <div className="text-[10px] text-terminal-muted mb-1">EMA TREND</div>
          <div className={`text-sm font-bold ${trendColor}`}>{trend}</div>
        </div>
        <div className="bg-terminal-bg/60 rounded-lg p-3">
          <div className="text-[10px] text-terminal-muted mb-1">RSI 14</div>
          <div className={`text-sm font-bold ${rsiColor}`}>
            {rsi !== '—' && rsi?.toFixed ? rsi.toFixed(1) : rsi}
          </div>
        </div>
        <div className="bg-terminal-bg/60 rounded-lg p-3">
          <div className="text-[10px] text-terminal-muted mb-1">ADX · {adxTrend}</div>
          <div className={`text-sm font-bold ${adxColor}`}>
            {adx != null ? adx.toFixed(1) : '—'}
          </div>
        </div>
        <div className="bg-terminal-bg/60 rounded-lg p-3">
          <div className="text-[10px] text-terminal-muted mb-1">H4 BIAS</div>
          <div className={`text-sm font-bold ${
            h4Bias === 'BULLISH' ? 'text-green-400'
            : h4Bias === 'BEARISH' ? 'text-red-400'
            : 'text-terminal-muted'
          }`}>{h4Bias ?? '—'}</div>
        </div>
      </div>

      {/* Mobile: confidence bar */}
      {conf != null && (
        <div className="sm:hidden mb-1">
          <ConfBar value={conf} />
        </div>
      )}

      {/* Mobile: stage info */}
      <div className="sm:hidden flex gap-4 text-xs text-terminal-muted">
        {s1Score != null && (
          <span>S1: <span className={s1Score >= 55 ? 'text-green-400' : 'text-amber-400'}>{s1Score}/100</span></span>
        )}
        <span>Web: <span className={webDone ? 'text-purple-400' : 'text-terminal-muted'}>
          {webDone == null ? '—' : webDone ? '✓' : '⏭'}
        </span></span>
        {regime && <span className="text-sky-400">{regime}</span>}
      </div>

      {/* Desktop: layout orizzontale originale */}
      <div className="hidden sm:flex sm:items-center sm:justify-between sm:gap-8">
        <div>
          <div className="text-xs text-terminal-muted mb-1">PREZZO</div>
          <div className="text-3xl font-bold text-white tabular-nums">
            {price ? price.toFixed(5) : '—'}
          </div>
        </div>

        <div className="flex flex-wrap gap-8">
          <Indicator label="EMA Trend" value={trend} color={trendColor} />
          <Indicator
            label="RSI 14"
            value={rsi !== '—' ? rsi?.toFixed ? rsi.toFixed(1) : rsi : '—'}
            color={rsiColor}
          />
          <Indicator
            label={`ADX 14 · ${adxTrend}`}
            value={adx != null ? adx.toFixed(1) : '—'}
            color={adxColor}
          />
          {h4Bias && h4Bias !== 'N/A' && (
            <Indicator
              label="H4 Bias"
              value={h4Bias}
              color={h4Bias === 'BULLISH' ? 'text-green-400' : h4Bias === 'BEARISH' ? 'text-red-400' : 'text-terminal-muted'}
            />
          )}
          {regime && <Indicator label="Regime" value={regime} color="text-sky-400" />}
        </div>

        <div className="w-px h-16 bg-terminal-border" />

        <div className="flex flex-col items-center gap-2 min-w-[140px]">
          <div className="text-xs text-terminal-muted uppercase tracking-wider">Ultima decisione</div>
          {dec ? (
            <>
              <DecisionBadge decision={dec} size="lg" />
              {conf != null && (
                <div className="w-full">
                  <div className="flex justify-between text-xs mb-0.5">
                    <span className="text-terminal-muted">confidenza</span>
                    <span className="text-white">{conf}%</span>
                  </div>
                  <ConfBar value={conf} />
                </div>
              )}
            </>
          ) : (
            <span className="text-terminal-muted text-sm">nessuna ancora</span>
          )}
        </div>

        <div className="flex flex-col gap-2 text-xs min-w-[120px]">
          {s1Score != null && (
            <div className="flex justify-between gap-3">
              <span className="text-terminal-muted">Stage1 score</span>
              <span className={s1Score >= 55 ? 'text-green-400' : 'text-amber-400'}>{s1Score}/100</span>
            </div>
          )}
          <div className="flex justify-between gap-3">
            <span className="text-terminal-muted">Web search</span>
            <span className={webDone ? 'text-purple-400' : 'text-terminal-muted'}>
              {webDone == null ? '—' : webDone ? '✓ eseguita' : '⏭ skippata'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
