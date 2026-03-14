import { useState, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ImageData } from '../api'
import { searchImages, thumbUrl, fullUrl } from '../api'
import FilterBar from '../components/FilterBar'

const PAGE_SIZE = 40

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

function DetailModal({ image, onClose }: { image: ImageData; onClose: () => void }) {
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
            ✕
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
                <span className="text-gray-500">Päivämäärä</span>
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
                <span className="text-gray-500">Polttoväli</span>
                <span className="text-gray-200">{image.exif_focal_length} mm</span>
              </>
            )}
            {image.width != null && image.height != null && (
              <>
                <span className="text-gray-500">Koko</span>
                <span className="text-gray-200">
                  {image.width} × {image.height} px
                </span>
              </>
            )}
            <span className="text-gray-500">Tiedostokoko</span>
            <span className="text-gray-200">{formatBytes(image.file_size)}</span>
            {image.ai_quality_score != null && (
              <>
                <span className="text-gray-500">Laatu</span>
                <span className="text-gray-200">{image.ai_quality_score.toFixed(1)} / 10</span>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function ImageCard({ image, onClick }: { image: ImageData; onClick: () => void }) {
  return (
    <div
      className="relative aspect-square bg-gray-800 rounded overflow-hidden cursor-pointer group"
      onClick={onClick}
    >
      <img
        src={thumbUrl(image.id)}
        alt={image.file_name}
        className="w-full h-full object-cover"
        loading="lazy"
      />
      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/70 transition-colors flex flex-col justify-end p-2 opacity-0 group-hover:opacity-100">
        {image.ai_description && (
          <p className="text-white text-xs line-clamp-2 mb-1">{image.ai_description}</p>
        )}
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
  const [page, setPage] = useState(1)
  const [activeFilters, setActiveFilters] = useState({
    dateFrom: '',
    dateTo: '',
    camera: '',
    minQuality: '',
  })
  const [selectedImage, setSelectedImage] = useState<ImageData | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['search', submittedQuery, activeFilters, page],
    queryFn: () =>
      searchImages({
        q: submittedQuery || undefined,
        date_from: activeFilters.dateFrom || undefined,
        date_to: activeFilters.dateTo || undefined,
        camera: activeFilters.camera || undefined,
        min_quality: activeFilters.minQuality ? Number(activeFilters.minQuality) : undefined,
        page,
        limit: PAGE_SIZE,
      }),
  })

  const handleSearch = useCallback(() => {
    setSubmittedQuery(query)
    setPage(1)
  }, [query])

  const handleFilter = useCallback(() => {
    setActiveFilters({ dateFrom, dateTo, camera, minQuality })
    setPage(1)
  }, [dateFrom, dateTo, camera, minQuality])

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 1

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
        total={data?.total ?? 0}
        onDateFrom={setDateFrom}
        onDateTo={setDateTo}
        onCamera={setCamera}
        onMinQuality={setMinQuality}
        onFilter={handleFilter}
      />

      {isLoading && (
        <div className="text-center py-12 text-gray-400">Ladataan...</div>
      )}
      {isError && (
        <div className="text-center py-12 text-red-400">Virhe haettaessa kuvia.</div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2 mt-4">
            {data.images.map(img => (
              <ImageCard key={img.id} image={img} onClick={() => setSelectedImage(img)} />
            ))}
          </div>

          {data.images.length === 0 && !isLoading && (
            <div className="text-center py-12 text-gray-500">Ei tuloksia.</div>
          )}

          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-4 mt-6">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed rounded text-sm transition-colors"
              >
                Edellinen
              </button>
              <span className="text-gray-400 text-sm">
                {page} / {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed rounded text-sm transition-colors"
              >
                Seuraava
              </button>
            </div>
          )}
        </>
      )}

      {selectedImage && (
        <DetailModal image={selectedImage} onClose={() => setSelectedImage(null)} />
      )}
    </div>
  )
}
