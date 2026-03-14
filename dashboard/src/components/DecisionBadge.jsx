export default function DecisionBadge({ decision, size = 'md' }) {
  const cfg = {
    BUY:  { bg: 'bg-green-900/40',  border: 'border-green-600',  text: 'text-green-400',  label: '▲ BUY'  },
    SELL: { bg: 'bg-red-900/40',    border: 'border-red-600',    text: 'text-red-400',    label: '▼ SELL' },
    HOLD: { bg: 'bg-amber-900/30',  border: 'border-amber-700',  text: 'text-amber-400',  label: '◆ HOLD' },
  }[decision] ?? { bg: 'bg-gray-800', border: 'border-gray-600', text: 'text-gray-400', label: decision ?? '—' }

  const px = size === 'lg' ? 'px-5 py-2 text-lg font-bold' : 'px-2.5 py-0.5 text-xs font-semibold'

  return (
    <span className={`inline-block rounded border ${cfg.bg} ${cfg.border} ${cfg.text} ${px}`}>
      {cfg.label}
    </span>
  )
}
