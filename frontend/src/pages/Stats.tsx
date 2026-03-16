import { useQuery } from '@tanstack/react-query'
import { getStats } from '../api'

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

export default function Stats() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
  })

  if (isLoading || !stats) return <div className="text-gray-400 py-12 text-center">Ladataan...</div>

  const active = (stats.status_counts.indexed || 0) + (stats.status_counts.kept || 0)
  const maxYear = Math.max(...stats.years.map(y => y.count), 1)

  return (
    <div className="max-w-5xl space-y-6">
      {/* Overview cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-gray-900 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-gray-100">{stats.total.toLocaleString()}</p>
          <p className="text-xs text-gray-400 mt-1">Tiedostoja</p>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-green-300">{active.toLocaleString()}</p>
          <p className="text-xs text-green-400 mt-1">Aktiivisia</p>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-blue-300">{stats.gps_count.toLocaleString()}</p>
          <p className="text-xs text-blue-400 mt-1">GPS-paikannettuja</p>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-gray-200">{formatSize(stats.total_size_bytes)}</p>
          <p className="text-xs text-gray-400 mt-1">Yhteiskoko</p>
        </div>
      </div>

      {/* Duplicates + date range */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-2">Duplikaatit</h3>
          <p className="text-2xl font-bold text-yellow-300">{stats.duplicate_groups.toLocaleString()}</p>
          <p className="text-xs text-gray-500">ryhmaa ({stats.duplicate_images.toLocaleString()} kuvaa)</p>
        </div>
        <div className="bg-gray-900 rounded-lg p-4">
          <h3 className="text-sm font-medium text-gray-300 mb-2">Ajanjakso</h3>
          <p className="text-sm text-gray-200">
            {stats.date_min?.slice(0, 10) || '?'} — {stats.date_max?.slice(0, 10) || '?'}
          </p>
          <p className="text-xs text-gray-500 mt-1">{stats.years.length} vuotta</p>
        </div>
      </div>

      {/* Timeline */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Aikajana</h3>
        <div className="flex items-end gap-1 h-32">
          {stats.years.map(y => (
            <div key={y.year} className="flex-1 flex flex-col items-center justify-end h-full min-w-0">
              <div
                className="w-full bg-blue-600 rounded-t min-h-[2px]"
                style={{ height: `${(y.count / maxYear) * 100}%` }}
                title={`${y.year}: ${y.count}`}
              />
              <span className="text-xs text-gray-600 mt-1 truncate w-full text-center">
                {y.year?.slice(2)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Cameras */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Kamerat</h3>
        <div className="space-y-2">
          {stats.cameras.map(cam => {
            const pct = active > 0 ? (cam.count / active) * 100 : 0
            return (
              <div key={cam.model} className="flex items-center gap-3">
                <span className="text-xs text-gray-300 w-40 truncate flex-shrink-0">{cam.model}</span>
                <div className="flex-1 bg-gray-800 rounded h-4 overflow-hidden">
                  <div className="bg-blue-700 h-full rounded" style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs text-gray-500 w-16 text-right flex-shrink-0">{cam.count.toLocaleString()}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Status breakdown */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Tila</h3>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {Object.entries(stats.status_counts).sort(([,a],[,b]) => b - a).map(([status, count]) => (
            <div key={status} className="text-center">
              <p className="text-lg font-bold text-gray-200">{count.toLocaleString()}</p>
              <p className="text-xs text-gray-500">{status}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
