/**
 * GLOBALSTATS — statistiche aggregate su tutti i bot
 */

import { GlowCard, Label, AnimatedNumber } from './ui'

export default function GlobalStats({ botsStatus }) {
  if (!botsStatus?.length) return null

  const running  = botsStatus.filter(b => b.running).length
  const total    = botsStatus.length

  return (
    <GlowCard glow="none" className="py-2 px-4">
      <div className="flex items-center gap-6 flex-wrap text-[11px] font-mono">
        <span className="text-terminal-muted uppercase tracking-wide">Fleet</span>
        <div className="flex items-center gap-1.5">
          <span className={`inline-block w-2 h-2 rounded-full ${running > 0 ? 'bg-green-500 animate-pulse' : 'bg-gray-600'}`} />
          <span className={running > 0 ? 'text-green-400' : 'text-terminal-muted'}>
            {running}/{total} attivi
          </span>
        </div>
        <div className="flex items-center gap-4">
          {botsStatus.map(b => (
            <div key={b.bot_id} className="flex items-center gap-1.5">
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${
                b.running ? 'bg-green-500' :
                b.phase === 'error' ? 'bg-red-500' : 'bg-gray-600'
              }`} />
              <span className={b.running ? 'text-white' : 'text-terminal-muted'}>
                {b.symbol ?? b.bot_id}
              </span>
              {b.price && (
                <span className="text-terminal-muted text-[10px]">{b.price}</span>
              )}
            </div>
          ))}
        </div>
      </div>
    </GlowCard>
  )
}
