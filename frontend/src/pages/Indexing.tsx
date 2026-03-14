import { useEffect, useRef, useState } from 'react'
import type { IndexerStatus } from '../api'
import {
  getIndexerStatus,
  startIndexer,
  stopIndexer,
  getSettings,
  updateSettings,
} from '../api'
import ProgressBar from '../components/ProgressBar'

const PHASE_LABELS: Record<string, string> = {
  idle: 'Odottaa',
  scanning: 'Skannaus',
  metadata: 'Metadata',
  ai_analysis: 'AI-analyysi',
  complete: 'Valmis',
  error: 'Virhe',
}

const DEFAULT_STATUS: IndexerStatus = {
  running: false,
  phase: 'idle',
  total: 0,
  processed: 0,
  errors: 0,
  speed: 0,
}

export default function Indexing() {
  const [status, setStatus] = useState<IndexerStatus>(DEFAULT_STATUS)
  const [newDir, setNewDir] = useState('')
  const [sourceDirs, setSourceDirs] = useState<string[]>([])
  const [loadingDirs, setLoadingDirs] = useState(true)
  const wsRef = useRef<WebSocket | null>(null)

  // Load initial status and source dirs
  useEffect(() => {
    getIndexerStatus().then(setStatus).catch(console.error)
    getSettings()
      .then(s => setSourceDirs(s.source_dirs))
      .catch(console.error)
      .finally(() => setLoadingDirs(false))
  }, [])

  // WebSocket for live updates
  useEffect(() => {
    const wsUrl = `ws://${window.location.host}/api/ws`
    const connect = () => {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'indexer_status') {
            setStatus(data.payload)
          }
        } catch {
          // ignore parse errors
        }
      }
      ws.onclose = () => {
        // Reconnect after 3s if component is still mounted
        setTimeout(connect, 3000)
      }
      ws.onerror = () => {
        ws.close()
      }
    }
    connect()
    return () => {
      wsRef.current?.close()
    }
  }, [])

  async function handleStartStop() {
    if (status.running) {
      await stopIndexer()
    } else {
      await startIndexer()
    }
    // Status will update via WebSocket, but also poll once for immediate feedback
    setTimeout(() => getIndexerStatus().then(setStatus).catch(console.error), 300)
  }

  async function handleAddDir() {
    if (!newDir.trim()) return
    const updated = [...sourceDirs, newDir.trim()]
    setSourceDirs(updated)
    setNewDir('')
    await updateSettings({ source_dirs: updated }).catch(console.error)
  }

  async function handleRemoveDir(dir: string) {
    const updated = sourceDirs.filter(d => d !== dir)
    setSourceDirs(updated)
    await updateSettings({ source_dirs: updated }).catch(console.error)
  }

  const pct = status.total > 0 ? Math.round((status.processed / status.total) * 100) : 0
  const phaseLabel = PHASE_LABELS[status.phase] ?? status.phase

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Status card */}
      <div className="bg-gray-900 rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span
              className={`w-3 h-3 rounded-full ${status.running ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`}
            />
            <span className="font-medium text-gray-100">{phaseLabel}</span>
          </div>
          <button
            onClick={handleStartStop}
            className={`px-5 py-2 rounded text-sm font-medium transition-colors ${
              status.running
                ? 'bg-red-800 hover:bg-red-700 text-white'
                : 'bg-green-700 hover:bg-green-600 text-white'
            }`}
          >
            {status.running ? 'Pysäytä' : 'Käynnistä'}
          </button>
        </div>

        {/* Progress bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-gray-400">
            <span>
              {status.processed} / {status.total} käsitelty
            </span>
            <span>{pct}%</span>
          </div>
          <ProgressBar value={status.processed} max={status.total} />
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-4 gap-3">
          <div className="bg-blue-900/30 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-blue-300">{status.total}</p>
            <p className="text-xs text-blue-400 mt-0.5">Löydetty</p>
          </div>
          <div className="bg-green-900/30 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-green-300">{status.processed}</p>
            <p className="text-xs text-green-400 mt-0.5">Käsitelty</p>
          </div>
          <div className="bg-red-900/30 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-red-300">{status.errors}</p>
            <p className="text-xs text-red-400 mt-0.5">Virheet</p>
          </div>
          <div className="bg-gray-800 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-gray-200">{status.speed.toFixed(1)}</p>
            <p className="text-xs text-gray-400 mt-0.5">kuvaa/s</p>
          </div>
        </div>
      </div>

      {/* Source folders */}
      <div className="bg-gray-900 rounded-lg p-5 space-y-4">
        <h2 className="font-medium text-gray-100">Lähdekansiot</h2>
        {loadingDirs ? (
          <p className="text-gray-500 text-sm">Ladataan...</p>
        ) : (
          <ul className="space-y-2">
            {sourceDirs.map(dir => (
              <li
                key={dir}
                className="flex items-center justify-between bg-gray-800 rounded px-3 py-2 text-sm"
              >
                <span className="text-gray-300 truncate font-mono text-xs">{dir}</span>
                <button
                  onClick={() => handleRemoveDir(dir)}
                  className="ml-3 text-gray-500 hover:text-red-400 transition-colors text-xs flex-shrink-0"
                >
                  Poista
                </button>
              </li>
            ))}
            {sourceDirs.length === 0 && (
              <li className="text-gray-500 text-sm">Ei kansioita.</li>
            )}
          </ul>
        )}
        <div className="flex gap-2">
          <input
            type="text"
            value={newDir}
            onChange={e => setNewDir(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAddDir()}
            placeholder="/polku/kansioon"
            className="flex-1 bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500 font-mono"
          />
          <button
            onClick={handleAddDir}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded transition-colors"
          >
            Lisää
          </button>
        </div>
      </div>
    </div>
  )
}
