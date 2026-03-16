import { useState, useCallback, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ImageData } from '../api'
import { searchImages, thumbUrl, fullUrl, updateImageStatus, getImageFolders, excludeFolder } from '../api'
import FilterBar from '../components/FilterBar'

const PAGE_SIZE = 40

function formatBytes(b: number | null | undefined): string {
  if (b == null || isNaN(b)) return '-'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

function DetailModal({ image, onClose, onStatusChange, onFolderSelect, onTimeNear, onPrev, onNext }: {
  image: ImageData; onClose: () => void; onStatusChange: (id: number, status: string) => void;
  onFolderSelect: (folder: string) => void; onTimeNear?: (date: string) => void;
  onPrev?: () => void; onNext?: () => void;
}) {
  const isRejected = image.status === 'rejected'
  const VIDEO_FORMATS = ['MP4','MOV','AVI','MKV','WMV','FLV','WEBM','M4V','MPG','MPEG','3GP','MTS']
  const isVideo = image.format ? VIDEO_FORMATS.includes(image.format.toUpperCase()) : false

  // Keyboard navigation + quick actions
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' && onPrev) onPrev()
      else if (e.key === 'ArrowRight' && onNext) onNext()
      else if (e.key === 'Escape') onClose()
      else if (e.key === 'Enter') {
        // Keep + next
        if (!isRejected && image.status !== 'kept') onStatusChange(image.id, 'kept')
        if (onNext) onNext()
      }
      else if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault()
        // Reject + next
        if (!isRejected) onStatusChange(image.id, 'rejected')
        else onStatusChange(image.id, 'indexed') // restore if already rejected
        if (onNext) onNext()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onPrev, onNext, onClose, onStatusChange, image.id, image.status, isRejected])

  // Compact EXIF line
  const exifParts: string[] = []
  if (image.exif_date) exifParts.push(image.exif_date.slice(0, 10))
  if (image.exif_camera_model) exifParts.push(image.exif_camera_model)
  if (image.exif_aperture != null) exifParts.push(`f/${image.exif_aperture}`)
  if (image.exif_iso != null) exifParts.push(`ISO ${image.exif_iso}`)
  if (image.exif_exposure) exifParts.push(`${image.exif_exposure}s`)
  if (image.exif_focal_length != null) exifParts.push(`${image.exif_focal_length}mm`)

  return (
    <div className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center" onClick={onClose}>
      {/* Prev arrow */}
      {onPrev && (
        <button onClick={(e) => { e.stopPropagation(); onPrev() }}
          className="absolute left-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/80 text-white w-10 h-16 rounded flex items-center justify-center text-xl z-10">
          {'<'}
        </button>
      )}
      {/* Next arrow */}
      {onNext && (
        <button onClick={(e) => { e.stopPropagation(); onNext() }}
          className="absolute right-2 top-1/2 -translate-y-1/2 bg-black/50 hover:bg-black/80 text-white w-10 h-16 rounded flex items-center justify-center text-xl z-10">
          {'>'}
        </button>
      )}

      <div className="bg-gray-900 rounded-lg max-w-4xl w-full mx-12 max-h-[95vh] flex flex-col" onClick={e => e.stopPropagation()}>
        {/* Image or Video */}
        <div className="relative flex-shrink-0 bg-black rounded-t-lg">
          {isVideo ? (
            <video
              src={fullUrl(image.id)}
              poster={thumbUrl(image.id)}
              controls
              className="w-full max-h-[60vh] object-contain"
            />
          ) : (
            <img src={fullUrl(image.id)} alt={image.file_name}
              className="w-full max-h-[60vh] object-contain" />
          )}
          <button onClick={onClose}
            className="absolute top-2 right-2 bg-black/60 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/80">
            X
          </button>
        </div>

        {/* Info bar - compact */}
        <div className="p-3 space-y-2 overflow-y-auto">
          {/* Title + size */}
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium text-white truncate">{image.file_name}</h3>
            <span className="text-xs text-gray-400 flex-shrink-0 ml-2">
              {image.width && image.height ? `${image.width}x${image.height}` : ''} {formatBytes(image.file_size)}
            </span>
          </div>

          {/* EXIF line + nearby button */}
          {exifParts.length > 0 && (
            <div className="flex items-center gap-2">
              <p className="text-xs text-gray-400">{exifParts.join(' · ')}</p>
              {image.exif_date && onTimeNear && (
                <button
                  onClick={() => { onTimeNear(image.exif_date!); onClose() }}
                  className="text-xs text-cyan-400 hover:text-cyan-300 flex-shrink-0"
                >
                  [samaan aikaan]
                </button>
              )}
            </div>
          )}

          {/* AI description + tags */}
          {image.ai_description && (
            <p className="text-xs text-gray-300">{image.ai_description}</p>
          )}
          {image.ai_tags && image.ai_tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {image.ai_tags.map(tag => (
                <span key={tag} className="bg-blue-900/60 text-blue-300 text-xs px-1.5 py-0.5 rounded-full">{tag}</span>
              ))}
            </div>
          )}

          {/* Path + actions row */}
          <div className="flex items-center justify-between pt-1 border-t border-gray-800">
            {image.file_path && (
              <button
                onClick={() => { onFolderSelect(image.file_path.split('/').slice(0, -1).join('/')); onClose() }}
                className="text-purple-400 text-xs hover:text-purple-300 truncate max-w-[60%]"
              >
                {image.file_path.split('/').slice(-4).join('/')}
              </button>
            )}
            <div className="flex gap-2 flex-shrink-0">
              {!isRejected ? (
                <button onClick={() => { onStatusChange(image.id, 'rejected'); onNext?.() }}
                  className="bg-red-800 hover:bg-red-700 text-red-100 text-xs px-3 py-1 rounded"
                  title="Backspace">
                  Havita &amp; seur.
                </button>
              ) : (
                <button onClick={() => { onStatusChange(image.id, 'indexed'); onNext?.() }}
                  className="bg-green-700 hover:bg-green-600 text-white text-xs px-3 py-1 rounded">
                  Palauta &amp; seur.
                </button>
              )}
              {image.status !== 'kept' && !isRejected && (
                <button onClick={() => { onStatusChange(image.id, 'kept'); onNext?.() }}
                  className="bg-green-800 hover:bg-green-700 text-green-100 text-xs px-3 py-1 rounded"
                  title="Enter">
                  Sailyta &amp; seur.
                </button>
              )}
            </div>
          </div>
          {/* Keyboard shortcuts hint */}
          <p className="text-xs text-gray-700 text-center pt-1">
            Enter = sailyta · Backspace = havita · Nuolet = edellinen/seuraava · Esc = sulje
          </p>
        </div>
      </div>
    </div>
  )
}

const STATUS_BADGES: Record<string, { label: string; bg: string; text: string } | null> = {
  kept: { label: 'Sailytetty', bg: 'bg-green-600', text: 'text-white' },
  rejected: { label: 'Hylatty', bg: 'bg-red-700', text: 'text-red-100' },
  pending: { label: 'Odottaa', bg: 'bg-yellow-700', text: 'text-yellow-100' },
  indexed: null, // no badge for normal state
  error: { label: 'Virhe', bg: 'bg-red-900', text: 'text-red-300' },
}

function ImageCard({ image, onClick, onStatusChange, onFolderSelect }: { image: ImageData; onClick: () => void; onStatusChange: (id: number, status: string) => void; onFolderSelect: (folder: string) => void }) {
  const badge = STATUS_BADGES[image.status]
  const isRejected = image.status === 'rejected'
  return (
    <div
      className={`relative aspect-square bg-gray-800 rounded overflow-hidden cursor-pointer group transition-transform duration-150 hover:scale-105 hover:z-10 ${isRejected ? 'opacity-40 hover:opacity-80' : ''}`}
      onClick={onClick}
    >
      <img
        src={thumbUrl(image.id)}
        alt={image.file_name}
        className="w-full h-full object-cover"
        loading="lazy"
      />
      {badge && (
        image.status === 'kept' ? (
          <button
            onClick={(e) => { e.stopPropagation(); onStatusChange(image.id, 'indexed') }}
            className={`absolute top-1 left-1 ${badge.bg} ${badge.text} text-xs px-1.5 py-0.5 rounded hover:opacity-70 transition-opacity cursor-pointer`}
            title="Klikkaa poistaaksesi sailytys-merkinta"
          >
            {badge.label} x
          </button>
        ) : (
          <div className={`absolute top-1 left-1 ${badge.bg} ${badge.text} text-xs px-1.5 py-0.5 rounded`}>
            {badge.label}
          </div>
        )
      )}
      {image.format && ['MP4','MOV','AVI','MKV','WMV','FLV','WEBM','M4V','MPG','MPEG','3GP','MTS'].includes(image.format.toUpperCase()) && (
        <div className="absolute bottom-1 left-1 bg-black/70 text-blue-300 text-xs px-1.5 py-0.5 rounded pointer-events-none">
          Video
        </div>
      )}
      {/* Quick action buttons on hover */}
      <div className="absolute top-1 right-1 flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
        {/* Keep button - only for non-kept, non-rejected */}
        {image.status !== 'kept' && !isRejected && (
          <button
            onClick={(e) => { e.stopPropagation(); onStatusChange(image.id, 'kept') }}
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold bg-green-600 hover:bg-green-500 text-white shadow-lg hover:scale-110 transition-all"
            title="Sailyta (Enter)"
          >
            v
          </button>
        )}
        {/* Reject button - NOT shown for kept images (must un-keep first) */}
        {image.status !== 'kept' && !isRejected && (
          <button
            onClick={(e) => { e.stopPropagation(); onStatusChange(image.id, 'rejected') }}
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold bg-red-600 hover:bg-red-500 text-white shadow-lg hover:scale-110 transition-all"
            title="Havita (Backspace)"
          >
            x
          </button>
        )}
        {/* Restore button - for rejected images */}
        {isRejected && (
          <button
            onClick={(e) => { e.stopPropagation(); onStatusChange(image.id, 'indexed') }}
            className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold bg-blue-500 hover:bg-blue-400 text-white shadow-lg hover:scale-110 transition-all"
            title="Palauta"
          >
            +
          </button>
        )}
      </div>
      {/* Info overlay - only bottom part */}
      <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-2 opacity-0 group-hover:opacity-100 transition-opacity">
        {image.exif_date && (
          <p className="text-gray-300 text-xs pointer-events-none">{image.exif_date.slice(0, 10)}</p>
        )}
        {image.file_path && (
          <button
            onClick={(e) => { e.stopPropagation(); onFolderSelect(image.file_path.split('/').slice(0, -1).join('/')) }}
            className="text-purple-400 text-xs truncate block w-full text-left hover:text-purple-300"
            title="Nayta taman kansion kuvat"
          >
            {image.file_path.split('/').slice(-3, -1).join('/')}
          </button>
        )}
      </div>
    </div>
  )
}

export default function Search() {
  const [searchParams] = useSearchParams()

  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [camera, setCamera] = useState('')
  const [minQuality, setMinQuality] = useState('')
  const [mediaType, setMediaType] = useState<'all' | 'photo' | 'video'>('all')
  const [sortBy, setSortBy] = useState('exif_date')
  const [sortOrder, setSortOrder] = useState('desc')
  const [excludeStatuses, setExcludeStatuses] = useState<Set<string>>(new Set(['rejected', 'pending']))
  const [folderFilter, setFolderFilter] = useState('')
  const [timeNear, setTimeNear] = useState('')
  const [timeRange, setTimeRange] = useState(300) // seconds, default ±5min
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [activeFilters, setActiveFilters] = useState({
    dateFrom: '',
    dateTo: '',
    camera: '',
    minQuality: '',
    status: '',
    exclude: 'rejected,pending',
    folder: '',
    media: 'all',
    timeNear: '',
  })
  const [selectedImage, setSelectedImage] = useState<ImageData | null>(null)

  // Sync URL params -> filters (when navigating from Stats etc.)
  useEffect(() => {
    const df = searchParams.get('date_from') || ''
    const dt = searchParams.get('date_to') || ''
    const cam = searchParams.get('camera') || ''
    const st = searchParams.get('status') || ''
    if (df || dt || cam || st) {
      setDateFrom(df); setDateTo(dt); setCamera(cam)
      const excl = st ? '' : 'rejected,pending'
      setExcludeStatuses(st ? new Set() : new Set(['rejected', 'pending']))
      setActiveFilters(prev => ({ ...prev, dateFrom: df, dateTo: dt, camera: cam, status: st, exclude: excl }))
    }
  }, [searchParams])
  const [showScrollTop, setShowScrollTop] = useState(false)
  const loadMoreRef = useRef<HTMLDivElement>(null)

  const {
    data,
    isLoading,
    isError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['search', submittedQuery, activeFilters, sortBy, sortOrder],
    queryFn: ({ pageParam = 1 }) =>
      searchImages({
        q: submittedQuery || undefined,
        date_from: activeFilters.dateFrom || undefined,
        date_to: activeFilters.dateTo || undefined,
        camera: activeFilters.camera || undefined,
        min_quality: activeFilters.minQuality ? Number(activeFilters.minQuality) : undefined,
        status: activeFilters.status || undefined,
        exclude: activeFilters.status ? undefined : (activeFilters.exclude || undefined),
        folder: activeFilters.folder || undefined,
        media: activeFilters.media !== 'all' ? activeFilters.media : undefined,
        time_near: activeFilters.timeNear || undefined,
        time_range: activeFilters.timeNear ? timeRange : undefined,
        sort: activeFilters.timeNear ? 'exif_date' : sortBy,
        order: sortOrder,
        page: pageParam,
        limit: PAGE_SIZE,
      }),
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, p) => sum + p.images.length, 0)
      return loaded < lastPage.total ? allPages.length + 1 : undefined
    },
    initialPageParam: 1,
  })

  // Infinite scroll - IntersectionObserver
  useEffect(() => {
    const el = loadMoreRef.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage()
        }
      },
      { threshold: 0.1 }
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [hasNextPage, isFetchingNextPage, fetchNextPage])

  // Show scroll-to-top button
  useEffect(() => {
    const handleScroll = () => setShowScrollTop(window.scrollY > 800)
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  const handleSearch = useCallback(() => {
    setSubmittedQuery(query)
  }, [query])

  const handleFilter = useCallback(() => {
    setActiveFilters({ dateFrom, dateTo, camera, minQuality, status: '', exclude: Array.from(excludeStatuses).join(','), folder: folderFilter, media: mediaType, timeNear })
  }, [dateFrom, dateTo, camera, minQuality, excludeStatuses, folderFilter, mediaType, timeNear])

  const handleTimeNear = useCallback((date: string) => {
    setTimeNear(date)
    setActiveFilters(f => ({ ...f, timeNear: date }))
  }, [])

  const { data: folders } = useQuery({
    queryKey: ['image-folders'],
    queryFn: getImageFolders,
  })

  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set())

  const toggleExpand = useCallback((path: string) => {
    setExpandedFolders(prev => {
      const next = new Set(prev)
      if (next.has(path)) {
        // Collapse: remove this and all children
        for (const p of next) {
          if (p.startsWith(path)) next.delete(p)
        }
      } else {
        next.add(path)
      }
      return next
    })
  }, [])

  const handleFolderSelect = useCallback((path: string) => {
    const newFolder = folderFilter === path ? '' : path
    setFolderFilter(newFolder)
    setShowFolderPicker(false)
    setActiveFilters(f => ({ ...f, folder: newFolder }))
  }, [folderFilter])

  const toggleExclude = useCallback((s: string) => {
    setExcludeStatuses(prev => {
      const next = new Set(prev)
      if (next.has(s)) {
        next.delete(s)
      } else {
        next.add(s)
      }
      const excludeStr = Array.from(next).join(',')
      setActiveFilters(f => ({ ...f, exclude: excludeStr }))
      return next
    })
  }, [])

  const allImages = data?.pages.flatMap(p => p.images) ?? []
  const total = data?.pages[0]?.total ?? 0
  const queryClient = useQueryClient()

  const handleStatusChange = useCallback(async (imageId: number, newStatus: string) => {
    await updateImageStatus(imageId, newStatus)
    queryClient.invalidateQueries({ queryKey: ['search'] })
  }, [queryClient])

  return (
    <div>
      <div className="flex gap-3 mb-2">
        <input
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
          placeholder="Hae kuvia..."
          className="flex-1 bg-gray-800 border border-gray-600 rounded px-4 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500"
        />
        <button
          onClick={handleSearch}
          className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded transition-colors"
        >
          Hae
        </button>
      </div>

      <FilterBar
        dateFrom={dateFrom}
        dateTo={dateTo}
        camera={camera}
        minQuality={minQuality}
        total={total}
        onDateFrom={setDateFrom}
        onDateTo={setDateTo}
        onCamera={setCamera}
        onMinQuality={setMinQuality}
        onFilter={handleFilter}
      />

      {/* Media type + Sort options */}
      <div className="flex flex-wrap items-center gap-2 mt-2 mb-1">
        {/* Media type filter */}
        {[
          { key: 'all' as const, label: 'Kaikki' },
          { key: 'photo' as const, label: 'Kuvat' },
          { key: 'video' as const, label: 'Videot' },
        ].map(m => (
          <button
            key={m.key}
            onClick={() => { setMediaType(m.key); setActiveFilters(f => ({ ...f, media: m.key })) }}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              mediaType === m.key ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {m.label}
          </button>
        ))}
        <span className="text-gray-700 mx-1">|</span>
        <span className="text-xs text-gray-500">Jarjesta:</span>
        {[
          { key: 'exif_date', label: 'Paivamaara' },
          { key: 'file_name', label: 'Nimi' },
          { key: 'file_path', label: 'Kansio' },
          { key: 'file_size', label: 'Koko' },
          { key: 'phash', label: 'Samankaltaisuus' },
          { key: 'created_at', label: 'Lisaysaika' },
        ].map(s => (
          <button
            key={s.key}
            onClick={() => {
              if (sortBy === s.key) {
                setSortOrder(o => o === 'desc' ? 'asc' : 'desc')
              } else {
                setSortBy(s.key)
                setSortOrder(s.key === 'file_name' || s.key === 'file_path' || s.key === 'phash' ? 'asc' : 'desc')
              }
            }}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              sortBy === s.key
                ? 'bg-gray-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {s.label} {sortBy === s.key ? (sortOrder === 'desc' ? 'v' : '^') : ''}
          </button>
        ))}
      </div>

      {/* Status toggle filters - click to show/hide */}
      <div className="flex flex-wrap items-center gap-2 mt-2 mb-2">
        <span className="text-xs text-gray-500">Nayta:</span>
        {[
          { key: 'indexed', label: 'Indeksoitu', activeColor: 'bg-gray-600 text-gray-100', },
          { key: 'kept', label: 'Sailytetyt', activeColor: 'bg-green-700 text-white' },
          { key: 'rejected', label: 'Hylatyt', activeColor: 'bg-red-800 text-red-100' },
          { key: 'pending', label: 'Odottavat', activeColor: 'bg-yellow-700 text-yellow-100' },
        ].map(f => {
          const isVisible = !excludeStatuses.has(f.key)
          return (
            <button
              key={f.key}
              onClick={() => toggleExclude(f.key)}
              className={`text-xs px-3 py-1 rounded transition-colors border ${
                isVisible
                  ? `${f.activeColor} border-transparent`
                  : 'bg-gray-900 text-gray-600 border-gray-700 line-through'
              }`}
            >
              {f.label}
            </button>
          )
        })}
      </div>

      {/* Time proximity filter with adjustable range */}
      {activeFilters.timeNear && (
        <div className="flex flex-wrap items-center gap-2 mb-2 bg-cyan-900/20 border border-cyan-800/30 rounded-lg px-3 py-2">
          <span className="text-cyan-200 text-xs">
            Samaan aikaan: {activeFilters.timeNear.slice(0, 19).replace('T', ' ')}
          </span>
          <div className="flex items-center gap-1">
            {[
              { label: '±1 min', value: 60 },
              { label: '±5 min', value: 300 },
              { label: '±30 min', value: 1800 },
              { label: '±1 h', value: 3600 },
              { label: '±1 pv', value: 86400 },
            ].map(opt => (
              <button key={opt.value}
                onClick={() => setTimeRange(opt.value)}
                className={`text-xs px-2 py-0.5 rounded transition-colors ${
                  timeRange === opt.value
                    ? 'bg-cyan-700 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}>
                {opt.label}
              </button>
            ))}
          </div>
          <button onClick={() => handleTimeNear('')} className="text-xs text-gray-500 hover:text-gray-300 ml-auto">
            Tyhjenna
          </button>
        </div>
      )}

      {/* Folder breadcrumb navigation */}
      <div className="flex flex-wrap items-center gap-1 mb-2">
        <button
          onClick={() => setShowFolderPicker(!showFolderPicker)}
          className="text-xs text-gray-500 hover:text-gray-300 mr-1"
        >
          {showFolderPicker ? 'v' : '>'} Kansiot
        </button>
        {folderFilter && (() => {
          const home = folderFilter.split('/').findIndex(p => p === 'Users') + 2
          const parts = folderFilter.split('/')
          const crumbs = parts.slice(home)
          return (
            <>
              <button onClick={() => handleFolderSelect('')} className="text-xs text-purple-400 hover:text-purple-300">~</button>
              {crumbs.map((part, i) => {
                const path = parts.slice(0, home + i + 1).join('/')
                const isLast = i === crumbs.length - 1
                return (
                  <span key={path} className="flex items-center gap-1">
                    <span className="text-gray-600 text-xs">/</span>
                    <button
                      onClick={() => handleFolderSelect(path)}
                      className={`text-xs ${isLast ? 'text-purple-300 font-medium' : 'text-purple-400 hover:text-purple-300'}`}
                    >
                      {part}
                    </button>
                  </span>
                )
              })}
              <button
                onClick={() => {
                  // Go up one level
                  const parent = folderFilter.split('/').slice(0, -1).join('/')
                  if (parent.split('/').length > home) handleFolderSelect(parent)
                  else handleFolderSelect('')
                }}
                className="text-xs text-gray-500 hover:text-gray-300 ml-2"
                title="Yla kansio"
              >
                [ylös]
              </button>
              <button
                onClick={async () => {
                  if (confirm(`Piilota kansio "${folderFilter.split('/').pop()}" ja kaikki sen kuvat indeksoinnista?`)) {
                    await excludeFolder(folderFilter)
                    handleFolderSelect('')
                    queryClient.invalidateQueries({ queryKey: ['search'] })
                    queryClient.invalidateQueries({ queryKey: ['image-folders'] })
                  }
                }}
                className="text-xs text-red-500 hover:text-red-400 ml-2"
                title="Piilota kansio indeksoinnista"
              >
                [piilota]
              </button>
            </>
          )
        })()}
      </div>
      {showFolderPicker && folders && (
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-2 mb-3 max-h-80 overflow-y-auto">
          {folders
            .filter(f => {
              if (f.depth <= 2) return true
              const parent = f.path.split('/').slice(0, -1).join('/')
              return expandedFolders.has(parent)
            })
            .map(f => {
              const isActive = folderFilter === f.path
              const isExpanded = expandedFolders.has(f.path)
              const hasChildren = folders.some(c => c.path.startsWith(f.path + '/') && c.path !== f.path)
              const folderName = f.short.split('/').pop() || f.short
              return (
                <div
                  key={f.path}
                  className={`flex items-center rounded text-xs transition-colors ${
                    isActive ? 'bg-purple-800 text-purple-100' : 'text-gray-300 hover:bg-gray-800/50'
                  }`}
                  style={{ paddingLeft: `${(f.depth - 1) * 14 + 4}px` }}
                >
                  {hasChildren ? (
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleExpand(f.path) }}
                      className="w-5 h-5 flex items-center justify-center text-gray-500 hover:text-gray-200 flex-shrink-0"
                    >
                      {isExpanded ? 'v' : '>'}
                    </button>
                  ) : (
                    <span className="w-5 h-5 flex-shrink-0" />
                  )}
                  <button
                    onClick={() => handleFolderSelect(f.path)}
                    className={`flex-1 text-left py-1 truncate ${isActive ? 'font-medium' : 'hover:text-white'}`}
                  >
                    {folderName}
                  </button>
                  <span className="text-gray-600 text-xs px-2 flex-shrink-0">
                    {f.indexed < f.count ? `${f.indexed}/${f.count}` : f.count}
                  </span>
                </div>
              )
            })}
        </div>
      )}

      {isLoading && (
        <div className="text-center py-12 text-gray-400">Ladataan...</div>
      )}
      {isError && (
        <div className="text-center py-12 text-red-400">Virhe haettaessa kuvia.</div>
      )}

      {allImages.length > 0 && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 mt-4">
            {allImages.map(img => (
              <ImageCard key={img.id} image={img} onClick={() => setSelectedImage(img)} onStatusChange={handleStatusChange} onFolderSelect={handleFolderSelect} />
            ))}
          </div>

          {/* Loaded count */}
          <div className="text-center text-xs text-gray-500 mt-4">
            {allImages.length} / {total} kuvaa
          </div>

          {/* Infinite scroll trigger */}
          <div ref={loadMoreRef} className="h-20 flex items-center justify-center">
            {isFetchingNextPage && (
              <span className="text-gray-400 text-sm animate-pulse">Ladataan lisaa...</span>
            )}
          </div>
        </>
      )}

      {allImages.length === 0 && !isLoading && data && (
        <div className="text-center py-12 text-gray-500">Ei tuloksia.</div>
      )}

      {/* Scroll to top button */}
      {showScrollTop && (
        <button
          onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}
          className="fixed bottom-6 right-6 bg-gray-800 hover:bg-gray-700 text-white w-12 h-12 rounded-full shadow-lg flex items-center justify-center transition-colors border border-gray-600 z-40"
          title="Palaa alkuun"
        >
          ^
        </button>
      )}

      {selectedImage && (
        <DetailModal
          image={selectedImage}
          onClose={() => setSelectedImage(null)}
          onStatusChange={handleStatusChange}
          onFolderSelect={handleFolderSelect}
          onTimeNear={handleTimeNear}
          onPrev={() => {
            const idx = allImages.findIndex(i => i.id === selectedImage.id)
            if (idx > 0) setSelectedImage(allImages[idx - 1])
          }}
          onNext={() => {
            const idx = allImages.findIndex(i => i.id === selectedImage.id)
            if (idx < allImages.length - 1) setSelectedImage(allImages[idx + 1])
          }}
        />
      )}
    </div>
  )
}
