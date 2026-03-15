import { useState, useCallback, useEffect, useRef } from 'react'
import { useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ImageData } from '../api'
import { searchImages, thumbUrl, fullUrl, updateImageStatus, getImageFolders } from '../api'
import FilterBar from '../components/FilterBar'

const PAGE_SIZE = 40

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

function DetailModal({ image, onClose, onStatusChange }: { image: ImageData; onClose: () => void; onStatusChange: (id: number, status: string) => void }) {
  const isRejected = image.status === 'rejected'
  return (
    <div
      className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 rounded-lg max-w-3xl w-full max-h-[90vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="relative">
          <img
            src={fullUrl(image.id)}
            alt={image.file_name}
            className="w-full max-h-96 object-contain bg-black rounded-t-lg"
          />
          <button
            onClick={onClose}
            className="absolute top-2 right-2 bg-black/60 text-white rounded-full w-8 h-8 flex items-center justify-center hover:bg-black/80"
          >
            X
          </button>
        </div>
        <div className="p-4 space-y-4">
          <h2 className="text-lg font-semibold text-white">{image.file_name}</h2>
          {image.ai_description && (
            <p className="text-gray-300 text-sm">{image.ai_description}</p>
          )}
          {image.ai_tags && image.ai_tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {image.ai_tags.map(tag => (
                <span
                  key={tag}
                  className="bg-blue-900/60 text-blue-300 text-xs px-2 py-0.5 rounded-full"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
            {image.exif_date && (
              <>
                <span className="text-gray-500">Paivamaara</span>
                <span className="text-gray-200">{image.exif_date}</span>
              </>
            )}
            {(image.exif_camera_make || image.exif_camera_model) && (
              <>
                <span className="text-gray-500">Kamera</span>
                <span className="text-gray-200">
                  {[image.exif_camera_make, image.exif_camera_model].filter(Boolean).join(' ')}
                </span>
              </>
            )}
            {image.exif_aperture != null && (
              <>
                <span className="text-gray-500">Aukko</span>
                <span className="text-gray-200">f/{image.exif_aperture}</span>
              </>
            )}
            {image.exif_iso != null && (
              <>
                <span className="text-gray-500">ISO</span>
                <span className="text-gray-200">{image.exif_iso}</span>
              </>
            )}
            {image.exif_exposure && (
              <>
                <span className="text-gray-500">Valotusaika</span>
                <span className="text-gray-200">{image.exif_exposure}</span>
              </>
            )}
            {image.exif_focal_length != null && (
              <>
                <span className="text-gray-500">Polttovali</span>
                <span className="text-gray-200">{image.exif_focal_length} mm</span>
              </>
            )}
            {image.width != null && image.height != null && (
              <>
                <span className="text-gray-500">Koko</span>
                <span className="text-gray-200">
                  {image.width} x {image.height} px
                </span>
              </>
            )}
            <span className="text-gray-500">Tiedostokoko</span>
            <span className="text-gray-200">{formatBytes(image.file_size)}</span>
            {image.file_path && (
              <>
                <span className="text-gray-500">Sijainti</span>
                <span className="text-gray-400 text-xs break-all">
                  {image.file_path.split('/').slice(-4).join('/')}
                </span>
              </>
            )}
            {image.ai_quality_score != null && (
              <>
                <span className="text-gray-500">Laatu</span>
                <span className="text-gray-200">{image.ai_quality_score.toFixed(1)} / 10</span>
              </>
            )}
          </div>
          {/* Status actions */}
          <div className="flex gap-2 pt-2 border-t border-gray-800">
            {!isRejected ? (
              <button
                onClick={() => { onStatusChange(image.id, 'rejected'); onClose() }}
                className="bg-red-800 hover:bg-red-700 text-red-100 text-sm px-4 py-2 rounded transition-colors"
              >
                Merkitse havitettavaksi
              </button>
            ) : (
              <button
                onClick={() => { onStatusChange(image.id, 'indexed'); onClose() }}
                className="bg-green-700 hover:bg-green-600 text-white text-sm px-4 py-2 rounded transition-colors"
              >
                Palauta
              </button>
            )}
            {image.status !== 'kept' && !isRejected && (
              <button
                onClick={() => { onStatusChange(image.id, 'kept'); onClose() }}
                className="bg-green-800 hover:bg-green-700 text-green-100 text-sm px-4 py-2 rounded transition-colors"
              >
                Merkitse sailytettavaksi
              </button>
            )}
          </div>
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

function ImageCard({ image, onClick, onStatusChange }: { image: ImageData; onClick: () => void; onStatusChange: (id: number, status: string) => void }) {
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
        <div className={`absolute top-1 left-1 ${badge.bg} ${badge.text} text-xs px-1.5 py-0.5 rounded`}>
          {badge.label}
        </div>
      )}
      {/* Quick reject/restore button - always visible on hover, large enough to click */}
      <button
        onClick={(e) => { e.stopPropagation(); onStatusChange(image.id, isRejected ? 'indexed' : 'rejected') }}
        className={`absolute top-1 right-1 w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold opacity-0 group-hover:opacity-100 transition-all shadow-lg ${
          isRejected
            ? 'bg-green-500 hover:bg-green-400 text-white hover:scale-110'
            : 'bg-red-600 hover:bg-red-500 text-white hover:scale-110'
        }`}
        title={isRejected ? 'Palauta' : 'Havita'}
      >
        {isRejected ? '+' : 'x'}
      </button>
      {/* Info overlay - only bottom part */}
      <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent p-2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
        {image.exif_date && (
          <p className="text-gray-300 text-xs">{image.exif_date.slice(0, 10)}</p>
        )}
        {(image.exif_camera_make || image.exif_camera_model) && (
          <p className="text-gray-400 text-xs truncate">
            {[image.exif_camera_make, image.exif_camera_model].filter(Boolean).join(' ')}
          </p>
        )}
      </div>
    </div>
  )
}

export default function Search() {
  const [query, setQuery] = useState('')
  const [submittedQuery, setSubmittedQuery] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [camera, setCamera] = useState('')
  const [minQuality, setMinQuality] = useState('')
  const [excludeStatuses, setExcludeStatuses] = useState<Set<string>>(new Set(['rejected', 'pending']))
  const [folderFilter, setFolderFilter] = useState('')
  const [showFolderPicker, setShowFolderPicker] = useState(false)
  const [activeFilters, setActiveFilters] = useState({
    dateFrom: '',
    dateTo: '',
    camera: '',
    minQuality: '',
    exclude: 'rejected,pending',
    folder: '',
  })
  const [selectedImage, setSelectedImage] = useState<ImageData | null>(null)
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
    queryKey: ['search', submittedQuery, activeFilters],
    queryFn: ({ pageParam = 1 }) =>
      searchImages({
        q: submittedQuery || undefined,
        date_from: activeFilters.dateFrom || undefined,
        date_to: activeFilters.dateTo || undefined,
        camera: activeFilters.camera || undefined,
        min_quality: activeFilters.minQuality ? Number(activeFilters.minQuality) : undefined,
        exclude: activeFilters.exclude || undefined,
        folder: activeFilters.folder || undefined,
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
    setActiveFilters({ dateFrom, dateTo, camera, minQuality, exclude: Array.from(excludeStatuses).join(','), folder: folderFilter })
  }, [dateFrom, dateTo, camera, minQuality, excludeStatuses, folderFilter])

  const { data: folders } = useQuery({
    queryKey: ['image-folders'],
    queryFn: getImageFolders,
  })

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

      {/* Folder filter */}
      <div className="flex items-center gap-2 mb-2">
        <button
          onClick={() => setShowFolderPicker(!showFolderPicker)}
          className={`text-xs px-3 py-1 rounded border transition-colors ${
            folderFilter
              ? 'bg-purple-800 text-purple-100 border-purple-600'
              : 'bg-gray-800 text-gray-400 border-gray-700 hover:border-gray-500'
          }`}
        >
          {folderFilter ? `Kansio: .../${folderFilter.split('/').slice(-2).join('/')}` : 'Valitse kansio'}
        </button>
        {folderFilter && (
          <button
            onClick={() => handleFolderSelect('')}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Tyhjenna
          </button>
        )}
      </div>
      {showFolderPicker && folders && (
        <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 mb-3 max-h-64 overflow-y-auto">
          {folders
            .filter(f => f.depth <= 4)
            .map(f => (
              <button
                key={f.path}
                onClick={() => handleFolderSelect(f.path)}
                className={`block w-full text-left px-2 py-1 rounded text-xs transition-colors ${
                  folderFilter === f.path
                    ? 'bg-purple-800 text-purple-100'
                    : 'text-gray-300 hover:bg-gray-800'
                }`}
                style={{ paddingLeft: `${(f.depth - 1) * 16 + 8}px` }}
              >
                <span className="text-gray-500">{f.depth > 1 ? '/' : ''}</span>
                {f.short.split('/').pop()}
                <span className="text-gray-600 ml-2">({f.count})</span>
              </button>
            ))}
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
              <ImageCard key={img.id} image={img} onClick={() => setSelectedImage(img)} onStatusChange={handleStatusChange} />
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
        <DetailModal image={selectedImage} onClose={() => setSelectedImage(null)} onStatusChange={handleStatusChange} />
      )}
    </div>
  )
}
