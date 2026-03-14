interface FilterBarProps {
  dateFrom: string
  dateTo: string
  camera: string
  minQuality: string
  total: number
  onDateFrom: (v: string) => void
  onDateTo: (v: string) => void
  onCamera: (v: string) => void
  onMinQuality: (v: string) => void
  onFilter: () => void
}

const inputClass =
  'bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500'

export default function FilterBar({
  dateFrom,
  dateTo,
  camera,
  minQuality,
  total,
  onDateFrom,
  onDateTo,
  onCamera,
  onMinQuality,
  onFilter,
}: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-3 py-3 border-b border-gray-800">
      <input
        type="date"
        value={dateFrom}
        onChange={e => onDateFrom(e.target.value)}
        className={inputClass}
        placeholder="Alku pvm"
      />
      <span className="text-gray-500 text-sm">–</span>
      <input
        type="date"
        value={dateTo}
        onChange={e => onDateTo(e.target.value)}
        className={inputClass}
        placeholder="Loppu pvm"
      />
      <input
        type="text"
        value={camera}
        onChange={e => onCamera(e.target.value)}
        className={`${inputClass} w-40`}
        placeholder="Kamera"
      />
      <input
        type="number"
        value={minQuality}
        onChange={e => onMinQuality(e.target.value)}
        className={`${inputClass} w-24`}
        placeholder="Min laatu"
        min="0"
        max="10"
        step="0.1"
      />
      <button
        onClick={onFilter}
        className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-1.5 rounded transition-colors"
      >
        Suodata
      </button>
      <span className="text-gray-400 text-sm ml-auto">{total} kuvaa</span>
    </div>
  )
}
