import { useEffect, useRef, useState } from 'react'
import type { IndexerStatus } from '../api'
import {
  getIndexerStatus,
  startIndexer,
  stopIndexer,
  processOnly,
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
          // WS updates don't include db_summary, so merge with existing
          if ('running' in data) {
            setStatus(prev => ({ ...prev, ...data, db_summary: data.db_summary ?? prev.db_summary }))
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
    <div className="space-y-6 max-w-5xl">
      {/* Status card */}
      <div className="bg-gray-900 rounded-lg p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span
              className={`w-3 h-3 rounded-full ${status.running ? 'bg-green-400 animate-pulse' : 'bg-gray-600'}`}
            />
            <span className="font-medium text-gray-100">{phaseLabel}</span>
          </div>
          <div className="flex gap-2">
            {!status.running && (
              <button
                onClick={async () => {
                  await processOnly()
                  setStatus(prev => ({ ...prev, running: true, phase: 'metadata' }))
                }}
                className="px-4 py-2 rounded text-sm font-medium bg-blue-700 hover:bg-blue-600 text-white transition-colors"
                title="Käsittele vain puuttuvat metatiedot ja AI (ei skannaa kansioita)"
              >
                Käsittele puuttuvat
              </button>
            )}
            <button
              onClick={handleStartStop}
              className={`px-5 py-2 rounded text-sm font-medium transition-colors ${
                status.running
                  ? 'bg-red-800 hover:bg-red-700 text-white'
                  : 'bg-green-700 hover:bg-green-600 text-white'
              }`}
            >
              {status.running ? 'Pysäytä' : 'Skannaa & käsittele'}
            </button>
          </div>
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
            <div className="flex items-center gap-3 mt-2 bg-gray-800/50 rounded p-2">
              {status.current_image_id ? (
                <img
                  src={`/api/images/${status.current_image_id}/thumb`}
                  alt=""
                  className="w-12 h-12 rounded object-cover flex-shrink-0 bg-gray-700"
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
              ) : (
                <div className="w-12 h-12 rounded bg-gray-700 flex-shrink-0 animate-pulse" />
              )}
              <div className="min-w-0">
                <p className="text-xs text-gray-300 truncate">{status.current_file}</p>
                <p className="text-xs text-gray-600 truncate">
                  {status.current_file_path?.split('/').slice(-4, -1).join('/') || ''}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* AI analysis progress (separate from metadata) */}
        {status.running && (status.ai_total ?? 0) > 0 && (
          <div className="bg-gray-900/50 rounded p-3 space-y-1 border border-purple-900/30">
            <div className="flex justify-between text-xs text-gray-400">
              <span>AI-analyysi: {status.ai_processed}/{status.ai_total}</span>
              <span>{status.ai_total! > 0 ? Math.round((status.ai_processed ?? 0) / status.ai_total! * 100) : 0}%</span>
            </div>
            <ProgressBar value={status.ai_processed ?? 0} max={status.ai_total ?? 0} />
            <div className="flex items-center gap-3 text-xs text-gray-500">
              {(status.ai_speed ?? 0) > 0 && (
                <>
                  <span>{(1 / status.ai_speed!).toFixed(1)} s/kuva</span>
                  <span className="text-gray-600">
                    ~{(() => {
                      const remaining = (status.ai_total ?? 0) - (status.ai_processed ?? 0)
                      const secs = remaining / (status.ai_speed ?? 1)
                      if (secs < 60) return `${Math.round(secs)}s`
                      if (secs < 3600) return `${Math.round(secs / 60)} min`
                      return `${(secs / 3600).toFixed(1)} h`
                    })()} jäljellä
                  </span>
                </>
              )}
              {status.ai_current_file && (
                <span className="truncate text-purple-400">{status.ai_current_file}</span>
              )}
            </div>
          </div>
        )}

        {/* Database summary - always visible */}
        {status.db_summary && (() => {
          const db = status.db_summary!
          const active = db.total - db.missing - db.rejected - db.error
          const photos = active - db.videos
          return (
            <div className="space-y-3">
              {/* Main stats */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <div className="bg-gray-800 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-gray-100">{db.total}</p>
                  <p className="text-xs text-gray-400 mt-0.5">Tiedostoja</p>
                </div>
                <div className="bg-green-900/30 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-green-300">{photos}</p>
                  <p className="text-xs text-green-400 mt-0.5">Kuvia</p>
                  <p className="text-xs text-gray-600">Aktiivisia</p>
                </div>
                <div className="bg-blue-900/30 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-blue-300">{db.videos}</p>
                  <p className="text-xs text-blue-400 mt-0.5">Videoita</p>
                </div>
                <div className="bg-yellow-900/20 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-yellow-300">{db.pending}</p>
                  <p className="text-xs text-yellow-400 mt-0.5">Odottaa</p>
                  <p className="text-xs text-gray-600">Käsittelemättä</p>
                </div>
                <div className="bg-red-900/20 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-red-300">{db.rejected}</p>
                  <p className="text-xs text-red-400 mt-0.5">Hylätty</p>
                </div>
              </div>
              {/* Secondary stats */}
              <div className="flex flex-wrap gap-4 text-xs text-gray-500 px-1">
                <span>Indeksoitu: <span className="text-gray-300">{db.indexed}</span></span>
                <span>Säilytetty: <span className="text-blue-300">{db.kept}</span></span>
                <span>AI-kuvaus: <span className="text-green-300">{db.ai_done}</span>{db.ai_missing > 0 && <span className="text-yellow-400"> / puuttuu {db.ai_missing}</span>}</span>
                <span>Videot: <span className="text-blue-300">{db.videos_indexed}</span>{db.videos_pending > 0 && <span className="text-yellow-400"> / odottaa {db.videos_pending}</span>}</span>
                <span>Puuttuvat: <span className="text-gray-400">{db.missing}</span></span>
                <span>Virheet: <span className="text-red-400">{db.error}</span></span>
              </div>
              {/* Format breakdown */}
              {db.formats && Object.keys(db.formats).length > 0 && (
                <div className="flex flex-wrap gap-2 text-xs text-gray-500 px-1">
                  <span className="text-gray-600">Tiedostotyypit:</span>
                  {Object.entries(db.formats)
                    .sort(([,a], [,b]) => b - a)
                    .slice(0, 12)
                    .map(([fmt, cnt]) => (
                      <span key={fmt} className="bg-gray-800 px-1.5 py-0.5 rounded text-gray-400">
                        {fmt} <span className="text-gray-500">{cnt}</span>
                      </span>
                    ))}
                </div>
              )}
            </div>
          )
        })()}

        {/* Current phase stats (when running) */}
        {status.running && status.total > 0 && (
          <div className="flex items-center gap-4 text-xs text-gray-400 bg-gray-800/50 rounded p-2">
            <span>{phaseLabel}: {status.processed}/{status.total}</span>
            <span>Virheet: {status.errors}</span>
            {status.speed > 0 && status.phase === 'metadata' && (
              <span>{status.speed.toFixed(1)} kuvaa/s ({(1000 / status.speed).toFixed(0)} ms/kuva)</span>
            )}
            {status.speed > 0 && status.phase === 'ai_analysis' && (
              <span>{status.speed.toFixed(2)} kuvaa/s ({(1 / status.speed).toFixed(1)} s/kuva)</span>
            )}
            {status.speed > 0 && status.phase !== 'metadata' && status.phase !== 'ai_analysis' && (
              <span>{status.speed.toFixed(1)}/s</span>
            )}
            {status.total > 0 && status.speed > 0 && (
              <span className="text-gray-500">
                ~{(() => {
                  const remaining = status.total - status.processed
                  const secs = remaining / status.speed
                  if (secs < 60) return `${Math.round(secs)}s`
                  if (secs < 3600) return `${Math.round(secs / 60)} min`
                  return `${(secs / 3600).toFixed(1)} h`
                })()} jäljellä
              </span>
            )}
          </div>
        )}
      </div>

      {/* Live log */}
      {status.running && status.recent_log && status.recent_log.length > 0 && (
        <div className="bg-gray-900 rounded-lg p-3">
          <p className="text-xs text-gray-500 mb-1">Loki:</p>
          <div className="font-mono text-xs text-gray-400 space-y-0.5 max-h-40 overflow-y-auto">
            {status.recent_log.slice().reverse().map((line, i) => (
              <div key={i} className={
                line.startsWith('✓') ? 'text-green-400' :
                line.startsWith('↓') ? 'text-blue-400' :
                line.startsWith('↑') ? 'text-yellow-400' :
                line.startsWith('✗') ? 'text-red-400' :
                'text-gray-500'
              }>
                {line}
              </div>
            ))}
          </div>
        </div>
      )}

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
            {sourceDirs.map(dir => {
              const isScanning = status.running && status.current_source_dir === dir
              const isDone = status.completed_source_dirs?.includes(dir)
              return (
              <li
                key={dir}
                className={`flex items-center justify-between rounded px-3 py-2 text-sm transition-colors ${
                  isScanning ? 'bg-blue-900/40 border border-blue-700' : isDone ? 'bg-green-900/20 border border-green-900' : 'bg-gray-800'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  {isScanning && <span className="text-blue-400 animate-pulse flex-shrink-0">...</span>}
                  {isDone && <span className="text-green-400 flex-shrink-0">OK</span>}
                  {!isScanning && !isDone && <span className="text-gray-600 flex-shrink-0">--</span>}
                  <span className="text-gray-300 truncate font-mono text-xs">{dir}</span>
                </div>
                <button
                  onClick={() => handleRemoveDir(dir)}
                  className="ml-3 text-gray-500 hover:text-red-400 transition-colors text-xs flex-shrink-0"
                >
                  Poista
                </button>
              </li>
              )
            })}
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
