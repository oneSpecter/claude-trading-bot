/**
 * UI Primitives — React Bits inspired
 * Glassmorphism cards, animated counters, tooltips, glow effects
 */
import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

// ── Glassmorphism Card ───────────────────────────────────────────
export function GlowCard({ children, className = '', glow = 'blue', hover = true }) {
  const glowMap = {
    blue:   'hover:shadow-[0_0_24px_rgba(59,130,246,0.25)] hover:border-blue-500/30',
    green:  'hover:shadow-[0_0_24px_rgba(34,197,94,0.25)]  hover:border-green-500/30',
    amber:  'hover:shadow-[0_0_24px_rgba(245,158,11,0.25)] hover:border-amber-500/30',
    red:    'hover:shadow-[0_0_24px_rgba(239,68,68,0.25)]  hover:border-red-500/30',
    none:   '',
  }
  return (
    <div className={`
      bg-terminal-card border border-terminal-border rounded-xl p-5
      transition-all duration-300
      ${hover ? glowMap[glow] || glowMap.blue : ''}
      ${className}
    `}>
      {children}
    </div>
  )
}

// ── Section Label ────────────────────────────────────────────────
export function Label({ children, className = '' }) {
  return (
    <div className={`text-[10px] font-mono uppercase tracking-[0.15em] text-terminal-muted mb-3 ${className}`}>
      {children}
    </div>
  )
}

// ── Animated Number Counter ──────────────────────────────────────
export function AnimatedNumber({ value, decimals = 1, prefix = '', suffix = '', className = '' }) {
  const [display, setDisplay] = useState(value)
  const prev = useRef(value)

  useEffect(() => {
    if (prev.current === value) return
    const start    = prev.current
    const end      = value
    const duration = 600
    const startTs  = performance.now()

    const step = (ts) => {
      const p  = Math.min((ts - startTs) / duration, 1)
      const ep = 1 - Math.pow(1 - p, 3)  // ease-out cubic
      setDisplay(start + (end - start) * ep)
      if (p < 1) requestAnimationFrame(step)
      else { setDisplay(end); prev.current = end }
    }
    requestAnimationFrame(step)
  }, [value])

  const formatted = typeof display === 'number'
    ? `${prefix}${display.toFixed(decimals)}${suffix}`
    : `${prefix}${display}${suffix}`

  return <span className={className}>{formatted}</span>
}

// ── Tooltip ──────────────────────────────────────────────────────
export function Tooltip({ text, children }) {
  const [show, setShow] = useState(false)
  return (
    <span className="relative inline-flex items-center gap-1"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}>
      {children}
      <AnimatePresence>
        {show && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            transition={{ duration: 0.15 }}
            className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50
                       w-52 bg-[#0a1020] border border-blue-500/30 rounded-lg p-3
                       text-[11px] text-gray-300 font-mono shadow-xl leading-relaxed pointer-events-none"
          >
            {text}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4
                            border-transparent border-t-blue-500/30" />
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  )
}

// ── Info Icon (da usare dentro Tooltip) ─────────────────────────
export function InfoIcon() {
  return (
    <svg className="w-3 h-3 text-terminal-muted cursor-help flex-shrink-0" fill="none"
      viewBox="0 0 24 24" stroke="currentColor">
      <circle cx="12" cy="12" r="10" strokeWidth={1.5}/>
      <path strokeLinecap="round" strokeWidth={1.5} d="M12 16v-4M12 8h.01"/>
    </svg>
  )
}

// ── Status Dot (pulsante) ────────────────────────────────────────
export function StatusDot({ active, className = '' }) {
  return (
    <span className={`relative inline-flex h-2.5 w-2.5 ${className}`}>
      {active && (
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-60" />
      )}
      <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
        active ? 'bg-green-400' : 'bg-gray-600'
      }`} />
    </span>
  )
}

// ── Decision Badge ───────────────────────────────────────────────
export function DecBadge({ decision }) {
  const map = {
    BUY:  'bg-green-500/15 text-green-400 border-green-500/30',
    SELL: 'bg-red-500/15 text-red-400 border-red-500/30',
    HOLD: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  }
  return (
    <span className={`inline-flex px-2 py-0.5 rounded-md border text-[10px] font-mono font-bold tracking-wider ${
      map[decision] || 'bg-gray-500/15 text-gray-400 border-gray-500/30'
    }`}>
      {decision ?? '—'}
    </span>
  )
}

// ── Toggle Switch ────────────────────────────────────────────────
export function Toggle({ checked, onChange, disabled = false }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2
        transition-colors duration-200 ease-in-out focus:outline-none
        ${checked ? 'bg-blue-600 border-blue-500' : 'bg-gray-700 border-gray-600'}
        ${disabled ? 'opacity-50 cursor-not-allowed' : 'hover:opacity-90'}
      `}
    >
      <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow-lg
        transition-transform duration-200 ease-in-out
        ${checked ? 'translate-x-5' : 'translate-x-0'}
      `} />
    </button>
  )
}
