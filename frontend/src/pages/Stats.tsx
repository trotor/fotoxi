import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
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
  const navigate = useNavigate()
  const [showAllCameras, setShowAllCameras] = useState(false)
  const [expandedYear, setExpandedYear] = useState<string | null>(null)

  if (isLoading || !stats) return <div className="text-gray-400 py-12 text-center">Ladataan...</div>

  const active = (stats.status_counts.indexed || 0) + (stats.status_counts.kept || 0)
  const maxYear = Math.max(...stats.years.map(y => y.count), 1)

  // Navigate to search with filters
  const goSearch = (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString()
    navigate(`/search?${qs}`)
  }

  const camerasToShow = showAllCameras ? stats.cameras : stats.cameras.slice(0, 10)

  return (
    <div className="max-w-5xl space-y-6">
      {/* Overview cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-gray-900 rounded-lg p-4 text-center">
          <p className="text-3xl font-bold text-gray-100">{stats.total.toLocaleString()}</p>
          <p className="text-xs text-gray-400 mt-1">Tiedostoja</p>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 text-center cursor-pointer hover:bg-gray-800"
          onClick={() => goSearch({})}>
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
        <div className="bg-gray-900 rounded-lg p-4 cursor-pointer hover:bg-gray-800"
          onClick={() => navigate('/duplicates')}>
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

      {/* Timeline - clickable, expandable to months */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3">
          Aikajana
          {expandedYear && (
            <button onClick={() => setExpandedYear(null)} className="ml-2 text-xs text-blue-400 hover:text-blue-300 font-normal">
              [takaisin vuosiin]
            </button>
          )}
        </h3>

        {!expandedYear ? (
          /* Year view */
          <div className="flex items-end gap-1 h-32">
            {stats.years.map(y => (
              <div key={y.year} className="flex-1 flex flex-col items-center justify-end h-full min-w-0 cursor-pointer group"
                onClick={() => setExpandedYear(y.year)}
                title={`${y.year}: ${y.count} kuvaa — klikkaa nahdaksesi kuukaudet`}>
                <div
                  className={`w-full rounded-t min-h-[2px] transition-colors ${
                    expandedYear === y.year ? 'bg-blue-400' : 'bg-blue-600 group-hover:bg-blue-400'
                  }`}
                  style={{ height: `${(y.count / maxYear) * 100}%` }}
                />
                <span className="text-xs text-gray-600 group-hover:text-gray-300 mt-1 truncate w-full text-center transition-colors">
                  {y.year?.slice(2)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          /* Month view for selected year */
          (() => {
            const MONTH_NAMES = ['Tammi','Helmi','Maalis','Huhti','Touko','Kesa','Heina','Elo','Syys','Loka','Marras','Joulu']
            const yearMonths = stats.months.filter(m => m.month.startsWith(expandedYear))
            // Fill missing months
            const monthData = Array.from({ length: 12 }, (_, i) => {
              const key = `${expandedYear}-${String(i + 1).padStart(2, '0')}`
              const found = yearMonths.find(m => m.month === key)
              return { month: key, count: found?.count || 0, label: MONTH_NAMES[i] }
            })
            const maxMonth = Math.max(...monthData.map(m => m.count), 1)
            const yearTotal = monthData.reduce((s, m) => s + m.count, 0)

            return (
              <div>
                <p className="text-xs text-gray-400 mb-2">{expandedYear} — {yearTotal.toLocaleString()} kuvaa</p>
                <div className="flex items-end gap-2 h-32">
                  {monthData.map(m => (
                    <div key={m.month} className="flex-1 flex flex-col items-center justify-end h-full min-w-0 cursor-pointer group"
                      onClick={() => {
                        const [y, mo] = m.month.split('-')
                        const lastDay = new Date(Number(y), Number(mo), 0).getDate()
                        goSearch({ date_from: `${m.month}-01`, date_to: `${m.month}-${lastDay}` })
                      }}
                      title={`${m.label} ${expandedYear}: ${m.count} kuvaa`}>
                      <span className="text-xs text-gray-500 group-hover:text-gray-300 mb-1">{m.count || ''}</span>
                      <div
                        className="w-full bg-green-600 group-hover:bg-green-400 rounded-t min-h-[2px] transition-colors"
                        style={{ height: `${(m.count / maxMonth) * 100}%` }}
                      />
                      <span className="text-xs text-gray-600 group-hover:text-gray-300 mt-1 truncate w-full text-center transition-colors">
                        {m.label.slice(0, 3)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )
          })()
        )}
      </div>

      {/* Cameras - clickable */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Kamerat (klikkaa suodattaaksesi)</h3>
        <div className="space-y-2">
          {camerasToShow.map(cam => {
            const pct = active > 0 ? (cam.count / active) * 100 : 0
            return (
              <div key={cam.model}
                className="flex items-center gap-3 cursor-pointer hover:bg-gray-800 rounded px-1 py-0.5 transition-colors"
                onClick={() => goSearch({ camera: cam.model })}>
                <span className="text-xs text-gray-300 w-48 truncate flex-shrink-0">{cam.model}</span>
                <div className="flex-1 bg-gray-800 rounded h-4 overflow-hidden">
                  <div className="bg-blue-700 h-full rounded" style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs text-gray-500 w-16 text-right flex-shrink-0">{cam.count.toLocaleString()}</span>
              </div>
            )
          })}
        </div>
        {stats.cameras.length > 10 && (
          <button onClick={() => setShowAllCameras(!showAllCameras)}
            className="text-xs text-blue-400 hover:text-blue-300 mt-2">
            {showAllCameras ? 'Nayta vahemman' : `Nayta kaikki (${stats.cameras.length})`}
          </button>
        )}
      </div>

      {/* Status breakdown */}
      <div className="bg-gray-900 rounded-lg p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Tila</h3>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {Object.entries(stats.status_counts).sort(([,a],[,b]) => b - a).map(([status, count]) => (
            <div key={status} className="text-center cursor-pointer hover:bg-gray-800 rounded p-2 transition-colors"
              onClick={() => goSearch({ status })}>
              <p className="text-lg font-bold text-gray-200">{count.toLocaleString()}</p>
              <p className="text-xs text-gray-500">{status}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
