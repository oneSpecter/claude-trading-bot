import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import BotDashboard from './components/BotDashboard'
import BotCard      from './components/BotCard'
import NewBotModal  from './components/NewBotModal'
import GlobalStats  from './components/GlobalStats'
import { GlowCard  } from './components/ui'

const POLL_MS = 5000

// ── BotGrid — solo presentazionale, dati da App ───────────────────
function BotGrid({ bots, statuses, lastEntries, error, onSelect, onStart, onStop, onDelete, onCreate }) {
  const [showModal, setShowModal] = useState(false)

  const botsWithStatus = bots.map(b => ({
    ...b,
    ...statuses[b.bot_id],
    symbol: b.symbol ?? b.bot_id,
  }))

  return (
    <div className="space-y-3 sm:space-y-4">

      {/* Global stats bar */}
      {bots.length > 0 && (
        <GlobalStats botsStatus={botsWithStatus} />
      )}

      {/* Error */}
      {error && (
        <div className="text-[11px] text-red-400 font-mono bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Header row */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-mono text-terminal-muted">
          {bots.length === 0 ? 'Nessun bot configurato' : `${bots.length} bot configurati`}
        </span>
        <button
          onClick={() => setShowModal(true)}
          className="px-4 py-2 text-[11px] font-mono rounded-lg
            bg-blue-500/15 border border-blue-500/40 text-blue-400
            hover:bg-blue-500/25 transition-colors">
          + Nuovo Bot
        </button>
      </div>

      {/* Bot cards grid */}
      {bots.length === 0 ? (
        <GlowCard glow="none" className="flex flex-col items-center justify-center py-16 gap-4">
          <div className="text-4xl opacity-30">🤖</div>
          <div className="text-sm font-mono text-terminal-muted text-center">
            Nessun bot configurato.<br />
            Clicca "+ Nuovo Bot" per iniziare.
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="px-6 py-2.5 text-sm font-mono rounded-xl
              bg-blue-500/15 border border-blue-500/40 text-blue-400
              hover:bg-blue-500/25 transition-colors">
            + Crea il primo bot
          </button>
        </GlowCard>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
          {bots.map(bot => (
            <BotCard
              key={bot.bot_id}
              bot={bot}
              status={statuses[bot.bot_id]}
              lastJournalEntry={lastEntries[bot.bot_id]}
              onSelect={onSelect}
              onStart={onStart}
              onStop={onStop}
              onDelete={onDelete}
            />
          ))}
        </div>
      )}

      {/* New Bot Modal */}
      {showModal && (
        <NewBotModal
          onClose={() => setShowModal(false)}
          onCreate={async (data) => { await onCreate(data); setShowModal(false) }}
        />
      )}
    </div>
  )
}

// ── App root — tutto lo stato bot qui, persiste tra navigazioni ────
export default function App() {
  const [selectedBotId,   setSelectedBotId]   = useState(null)
  const [selectedBotMeta, setSelectedBotMeta] = useState(null)

  // Dati bot — non si resettano mai durante la navigazione
  const [bots,        setBots]        = useState([])
  const [statuses,    setStatuses]    = useState({})
  const [lastEntries, setLastEntries] = useState({})
  const [botError,    setBotError]    = useState(null)

  const fetchBots = useCallback(async () => {
    try {
      const list = await fetch('/api/bots').then(r => r.json())
      setBots(list)
      setBotError(null)

      const statusMap = {}
      const entryMap  = {}
      await Promise.all(list.map(async (b) => {
        const bid = b.bot_id
        try {
          const [s, j] = await Promise.all([
            fetch(`/api/bots/${bid}/status`).then(r => r.json()),
            fetch(`/api/bots/${bid}/journal?limit=1`).then(r => r.json()),
          ])
          statusMap[bid] = s
          entryMap[bid]  = Array.isArray(j) ? j[0] : null
        } catch {}
      }))
      setStatuses(statusMap)
      setLastEntries(entryMap)
    } catch {
      setBotError('Server non raggiungibile — avvia: uvicorn server:app --host 0.0.0.0 --port 8000')
    }
  }, [])

  // Poll sempre — anche mentre sei nel BotDashboard
  useEffect(() => {
    fetchBots()
    const id = setInterval(fetchBots, POLL_MS)
    return () => clearInterval(id)
  }, [fetchBots])

  const handleCreate = async (botData) => {
    const r = await fetch('/api/bots', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(botData),
    })
    if (!r.ok) {
      const err = await r.json()
      throw new Error(err.detail ?? 'Errore creazione bot')
    }
    await fetchBots()
  }

  const handleStart = async (botId) => {
    const cfg = await fetch(`/api/bots/${botId}/config`).then(r => r.json()).catch(() => ({}))
    const useMock = cfg.use_mock ?? false
    const dryRun  = cfg.dry_run  ?? true
    await fetch(`/api/bots/${botId}/start?dry_run=${dryRun}&use_mock=${useMock}`, { method: 'POST' })
    setTimeout(fetchBots, 1500)
  }

  const handleStop = async (botId) => {
    await fetch(`/api/bots/${botId}/stop`, { method: 'POST' })
    setTimeout(fetchBots, 1500)
  }

  const handleDelete = async (botId) => {
    if (!window.confirm(`Eliminare il bot "${botId}"?`)) return
    await fetch(`/api/bots/${botId}`, { method: 'DELETE' })
    await fetchBots()
  }

  const handleSelectBot = (botId) => {
    const meta = bots.find(b => b.bot_id === botId) ?? { bot_id: botId }
    setSelectedBotMeta(meta)
    setSelectedBotId(botId)
  }

  const handleBack = () => {
    setSelectedBotId(null)
    setSelectedBotMeta(null)
  }

  return (
    <div className="min-h-screen bg-terminal-bg text-gray-100 font-mono bg-grid-pattern bg-grid">
      {/* Scan line effect */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0 opacity-[0.015]">
        <div className="absolute w-full h-0.5 bg-blue-400 animate-scan" />
      </div>

      <div className="relative z-10 max-w-screen-xl mx-auto p-3 sm:p-5 space-y-3 sm:space-y-4">

        {/* Header */}
        <GlowCard glow="none" className="py-3 px-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="font-mono font-bold text-sm text-white tracking-wide">FOREX AI BOT</span>
              <span className="text-[10px] text-terminal-muted font-mono">Multi-Bot Dashboard</span>
            </div>
            {selectedBotId && (
              <button onClick={handleBack}
                className="text-[11px] font-mono text-terminal-muted hover:text-white
                  px-3 py-1 border border-terminal-border rounded-lg
                  hover:border-blue-500/40 transition-colors">
                ← Tutti i bot
              </button>
            )}
          </div>
        </GlowCard>

        {/* Content: Grid or single BotDashboard */}
        <AnimatePresence mode="wait">
          {selectedBotId ? (
            <motion.div
              key={`bot-${selectedBotId}`}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2, ease: 'easeInOut' }}
            >
              <BotDashboard
                botId={selectedBotId}
                botMeta={selectedBotMeta}
                onBack={handleBack}
              />
            </motion.div>
          ) : (
            <motion.div
              key="grid"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
            >
              <BotGrid
                bots={bots}
                statuses={statuses}
                lastEntries={lastEntries}
                error={botError}
                onSelect={handleSelectBot}
                onStart={handleStart}
                onStop={handleStop}
                onDelete={handleDelete}
                onCreate={handleCreate}
              />
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </div>
  )
}
