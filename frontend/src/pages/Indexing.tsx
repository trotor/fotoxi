import { useEffect, useRef, useState } from 'react'
import type { IndexerStatus } from '../api'
import {
  getIndexerStatus,
  startIndexer,
  stopIndexer,
  getSettings,
  updateSettings,
  getCloudFolders,
  type CloudFolder,
} from '../api'
import ProgressBar from '../components/ProgressBar'
import FolderBrowser from '../components/FolderBrowser'

const PHASE_LABELS: Record<string, string> = {
  idle: 'Odottaa',
  scanning: 'Skannaus',
  metadata: 'Metadata',
  starting: 'Käynnistyy...',
  ai_analysis: 'AI-analyysi',
  grouping: 'Duplikaattien tunnistus',
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
  current_file: '',
}

export default function Indexing() {
  const [status, setStatus] = useState<IndexerStatus>(DEFAULT_STATUS)
  const [newDir, setNewDir] = useState('')
  const [sourceDirs, setSourceDirs] = useState<string[]>([])
  const [loadingDirs, setLoadingDirs] = useState(true)
  const [showBrowser, setShowBrowser] = useState(false)
  const [cloudFolders, setCloudFolders] = useState<CloudFolder[]>([])
  const wsRef = useRef<WebSocket | null>(null)

  // Poll status every 2s when running (backup for WebSocket)
  useEffect(() => {
    if (!status.running) return
    const interval = setInterval(() => {
      getIndexerStatus().then(setStatus).catch(console.error)
    }, 2000)
    return () => clearInterval(interval)
  }, [status.running])

  // Load initial status and source dirs
  useEffect(() => {
    getIndexerStatus().then(setStatus).catch(console.error)
    getSettings()
      .then(s => setSourceDirs(s.source_dirs))
      .catch(console.error)
      .finally(() => setLoadingDirs(false))
    getCloudFolders().then(setCloudFolders).catch(console.error)
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
          // Backend sends state dict directly (has 'running' field)
          if ('running' in data) {
            setStatus(data)
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
      // Poll until it actually stops
      const poll = setInterval(async () => {
        const s = await getIndexerStatus()
        setStatus(s)
        if (!s.running) clearInterval(poll)
      }, 500)
    } else {
      await startIndexer()
      // Immediately set running in UI for feedback
      setStatus(prev => ({ ...prev, running: true, phase: 'starting' }))
      setTimeout(() => getIndexerStatus().then(setStatus).catch(console.error), 1000)
    }
  }

  async function handleAddDir(dir?: string) {
    const dirToAdd = dir || newDir.trim()
    if (!dirToAdd) return
    const updated = [...sourceDirs, dirToAdd]
    setSourceDirs(updated)
    setNewDir('')
    setShowBrowser(false)
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
          {status.phase === 'scanning' ? (
            <div className="flex justify-between text-xs text-gray-400">
              <span>Löydetty {status.processed} tiedostoa...</span>
              <span className="animate-pulse">Skannataan</span>
            </div>
          ) : (
            <div className="flex justify-between text-xs text-gray-400">
              <span>{status.processed} / {status.total} käsitelty</span>
              <span>{pct}%</span>
            </div>
          )}
          {status.phase !== 'scanning' && (
            <ProgressBar value={status.processed} max={status.total} />
          )}
          {status.phase === 'scanning' && (
            <div className="w-full bg-gray-700 rounded h-2 overflow-hidden">
              <div className="h-full bg-blue-500 rounded animate-pulse" style={{ width: '100%', opacity: 0.4 }} />
            </div>
          )}
          {status.current_file && status.running && (
            <p className="text-xs text-gray-500 truncate mt-1">
              {status.current_file}
            </p>
          )}
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

        {/* Quick-add cloud folders */}
        {cloudFolders.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-gray-500">Pikalisäys:</p>
            <div className="flex flex-wrap gap-2">
              {cloudFolders
                .filter(cf => !sourceDirs.includes(cf.path))
                .map(cf => (
                  <button
                    key={cf.path}
                    onClick={() => handleAddDir(cf.path)}
                    className="bg-blue-900/40 hover:bg-blue-800/60 text-blue-300 text-xs px-3 py-1.5 rounded border border-blue-800 transition-colors"
                  >
                    + {cf.label}
                  </button>
                ))}
              {cloudFolders.every(cf => sourceDirs.includes(cf.path)) && (
                <span className="text-xs text-gray-500">Kaikki pilviikansiot lisätty</span>
              )}
            </div>
          </div>
        )}
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
            onClick={() => handleAddDir()}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded transition-colors"
          >
            Lisää
          </button>
          <button
            onClick={() => setShowBrowser(true)}
            className="bg-gray-700 hover:bg-gray-600 text-white text-sm px-4 py-2 rounded transition-colors"
          >
            Selaa...
          </button>
        </div>
      </div>

      {showBrowser && (
        <FolderBrowser
          onSelect={(path) => handleAddDir(path)}
          onCancel={() => setShowBrowser(false)}
        />
      )}
    </div>
  )
}
