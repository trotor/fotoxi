import { useState, useCallback, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { getMapClusters, searchImages, thumbUrl, geocodeSearch } from '../api'
import type { MapCluster, GeocodeSuggestion } from '../api'
import { useI18n } from '../i18n/useTranslation'

const PAGE_SIZE = 40

function MapEvents({ onBoundsChange, onMapClick }: {
  onBoundsChange: (bounds: { south: number; north: number; west: number; east: number }, zoom: number) => void
  onMapClick: (lat: number, lon: number) => void
}) {
  const map = useMapEvents({
    moveend: () => {
      const b = map.getBounds()
      onBoundsChange({
        south: b.getSouth(),
        north: b.getNorth(),
        west: b.getWest(),
        east: b.getEast(),
      }, map.getZoom())
    },
    click: (e) => {
      onMapClick(e.latlng.lat, e.latlng.lng)
    },
  })

  // Fire initial bounds
  useEffect(() => {
    const b = map.getBounds()
    onBoundsChange({
      south: b.getSouth(),
      north: b.getNorth(),
      west: b.getWest(),
      east: b.getEast(),
    }, map.getZoom())
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return null
}

function FlyTo({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap()
  useEffect(() => {
    map.flyTo(center, zoom, { duration: 1 })
  }, [center[0], center[1], zoom]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

function clusterColor(count: number): string {
  if (count >= 100) return '#ef4444'
  if (count >= 20) return '#f59e0b'
  if (count >= 5) return '#3b82f6'
  return '#22c55e'
}

function clusterRadius(count: number): number {
  return Math.min(8 + Math.log2(count + 1) * 4, 30)
}

/** Legend explaining cluster colour buckets (matches clusterColor) and size. */
function MapLegend() {
  const { t } = useI18n()
  const items = [
    { color: '#ef4444', label: '100+' },
    { color: '#f59e0b', label: '20–99' },
    { color: '#3b82f6', label: '5–19' },
    { color: '#22c55e', label: '1–4' },
  ]
  return (
    <div className="absolute bottom-4 left-4 z-[1000] bg-gray-900/90 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-300 shadow-lg pointer-events-none">
      <div className="font-medium text-gray-400 mb-1">{t('map.legend_title')}</div>
      <div className="space-y-1">
        {items.map(it => (
          <div key={it.label} className="flex items-center gap-2">
            <span className="inline-block w-3 h-3 rounded-full" style={{ background: it.color }} />
            <span>{it.label}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 text-[10px] text-gray-500">{t('map.legend_size')}</div>
    </div>
  )
}

export default function MapPage() {
  const { t } = useI18n()
  const navigate = useNavigate()

  const [bounds, setBounds] = useState<{ south: number; north: number; west: number; east: number } | null>(null)
  const [zoom, setZoom] = useState(6)
  const [selectedLocation, setSelectedLocation] = useState<{ lat: number; lon: number } | null>(null)
  const [selectedRadius, setSelectedRadius] = useState(5)
  const [selectedLabel, setSelectedLabel] = useState<string | null>(null)
  const [includeInherited, setIncludeInherited] = useState(true)
  const [flyTarget, setFlyTarget] = useState<{ center: [number, number]; zoom: number } | null>(null)

  // Place search
  const [placeQuery, setPlaceQuery] = useState('')
  const [placeSuggestions, setPlaceSuggestions] = useState<GeocodeSuggestion[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  const handlePlaceInput = useCallback((value: string) => {
    setPlaceQuery(value)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (value.length < 2) {
      setPlaceSuggestions([])
      setShowSuggestions(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      const results = await geocodeSearch(value)
      setPlaceSuggestions(results)
      setShowSuggestions(results.length > 0)
    }, 400)
  }, [])

  const selectPlace = useCallback((place: GeocodeSuggestion) => {
    setSelectedLocation({ lat: place.lat, lon: place.lon })
    setSelectedRadius(place.radius_km)
    setSelectedLabel(place.display_name.split(',').slice(0, 2).join(','))
    setFlyTarget({ center: [place.lat, place.lon], zoom: place.radius_km < 2 ? 14 : place.radius_km < 10 ? 12 : 10 })
    setPlaceQuery('')
    setPlaceSuggestions([])
    setShowSuggestions(false)
  }, [])

  // Cluster data
  const { data: clusters } = useQuery({
    queryKey: ['map-clusters', zoom, bounds, includeInherited],
    queryFn: () => getMapClusters({
      zoom,
      ...bounds!,
      include_inherited: includeInherited,
    }),
    enabled: !!bounds,
    staleTime: 30000,
  })

  // Images for selected location
  const {
    data: imageData,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['map-images', selectedLocation, selectedRadius],
    queryFn: ({ pageParam = 1 }) => searchImages({
      lat: selectedLocation!.lat,
      lon: selectedLocation!.lon,
      radius: selectedRadius,
      sort: 'exif_date',
      order: 'desc',
      page: pageParam,
      limit: PAGE_SIZE,
    }),
    enabled: !!selectedLocation,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((sum, p) => sum + p.images.length, 0)
      return loaded < lastPage.total ? allPages.length + 1 : undefined
    },
    initialPageParam: 1,
  })

  const images = imageData?.pages.flatMap(p => p.images) ?? []
  const totalImages = imageData?.pages[0]?.total ?? 0

  const handleBoundsChange = useCallback((b: typeof bounds, z: number) => {
    setBounds(b)
    setZoom(z)
  }, [])

  // Auto-radius based on zoom level: matches backend cluster precision
  const zoomToRadius = useCallback((z: number): number => {
    if (z <= 7) return 60    // precision 0 → ~111km clusters
    if (z <= 10) return 10   // precision 1 → ~11km clusters
    if (z <= 13) return 1    // precision 2 → ~1.1km clusters
    if (z <= 16) return 0.2  // precision 3 → ~110m clusters
    return 0.05              // precision 4
  }, [])

  const handleMapClick = useCallback((lat: number, lon: number) => {
    setSelectedLocation({ lat, lon })
    setSelectedLabel(null)
    setSelectedRadius(zoomToRadius(zoom))
  }, [zoom, zoomToRadius])

  const handleClusterClick = useCallback((cluster: MapCluster) => {
    setSelectedLocation({ lat: cluster.lat, lon: cluster.lon })
    setSelectedLabel(cluster.location_name)
    setSelectedRadius(zoomToRadius(zoom))
  }, [zoom, zoomToRadius])

  const handleClusterDblClick = useCallback((cluster: MapCluster) => {
    // Zoom in to break up the cluster
    setFlyTarget({ center: [cluster.lat, cluster.lon], zoom: Math.min(zoom + 3, 18) })
  }, [zoom])

  // Load more ref
  const loadMoreRef = useRef<HTMLDivElement>(null)
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

  return (
    <div className="flex flex-col h-[calc(100vh-48px)]">
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2 bg-gray-900 border-b border-gray-800 flex-shrink-0">
        {/* Place search */}
        <div className="relative flex-1 max-w-sm">
          <input
            type="text"
            value={placeQuery}
            onChange={e => handlePlaceInput(e.target.value)}
            onFocus={() => placeSuggestions.length > 0 && setShowSuggestions(true)}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
            placeholder={t('search.place_placeholder')}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-green-600"
          />
          {showSuggestions && (
            <div className="absolute z-[1000] top-full left-0 right-0 mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-xl overflow-hidden">
              {placeSuggestions.map((place, i) => {
                const parts = place.display_name.split(',')
                const main = parts.slice(0, 2).join(',')
                const secondary = parts.slice(2, 4).join(',')
                return (
                  <button
                    key={i}
                    onMouseDown={e => e.preventDefault()}
                    onClick={() => selectPlace(place)}
                    className="w-full text-left px-3 py-2 hover:bg-gray-700 transition-colors border-b border-gray-700/50 last:border-0"
                  >
                    <div className="text-sm text-gray-100">{main}</div>
                    <div className="text-xs text-gray-500">{secondary}</div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Radius selector */}
        <div className="flex items-center gap-1">
          {[
            { label: '1km', value: 1 },
            { label: '5km', value: 5 },
            { label: '20km', value: 20 },
            { label: '50km', value: 50 },
          ].map(opt => (
            <button key={opt.value}
              onClick={() => setSelectedRadius(opt.value)}
              className={`text-xs px-2 py-1 rounded transition-colors ${
                selectedRadius === opt.value
                  ? 'bg-green-700 text-white'
                  : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}>
              {opt.label}
            </button>
          ))}
        </div>

        {/* Include inherited toggle */}
        <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={includeInherited}
            onChange={e => setIncludeInherited(e.target.checked)}
            className="rounded border-gray-600"
          />
          {t('map.include_inherited')}
        </label>

        {/* Selected location label */}
        {selectedLocation && (
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-xs text-green-300">
              📍 {selectedLabel || `${selectedLocation.lat.toFixed(3)}, ${selectedLocation.lon.toFixed(3)}`}
            </span>
            <span className="text-xs text-gray-500">{totalImages} {t('search.images')}</span>
            <button
              onClick={() => navigate(`/search?lat=${selectedLocation.lat}&lon=${selectedLocation.lon}&radius=${selectedRadius}`)}
              className="text-xs px-2 py-0.5 rounded bg-blue-700 hover:bg-blue-600 text-white"
            >
              {t('map.open_in_search')}
            </button>
            <button onClick={() => { setSelectedLocation(null); setSelectedLabel(null) }}
              className="text-xs text-gray-500 hover:text-gray-300">✕</button>
          </div>
        )}
      </div>

      {/* Map + Gallery split */}
      <div className="flex flex-1 min-h-0">
        {/* Map */}
        <div className={`relative ${selectedLocation ? 'w-1/2' : 'w-full'} transition-all duration-300`}>
          <MapLegend />
          <MapContainer
            center={[63.0, 27.0]}
            zoom={6}
            doubleClickZoom={false}
            className="h-full w-full"
            style={{ background: '#1a1a2e' }}
          >
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            />
            <MapEvents onBoundsChange={handleBoundsChange} onMapClick={handleMapClick} />
            {flyTarget && <FlyTo center={flyTarget.center} zoom={flyTarget.zoom} />}

            {(clusters ?? []).map((cluster, i) => (
              <CircleMarker
                key={`${cluster.lat}-${cluster.lon}-${i}`}
                center={[cluster.lat, cluster.lon]}
                radius={clusterRadius(cluster.count)}
                fillColor={clusterColor(cluster.count)}
                fillOpacity={0.8}
                color="white"
                weight={1}
                eventHandlers={{
                  click: (e) => {
                    e.originalEvent.stopPropagation()
                    handleClusterClick(cluster)
                  },
                  dblclick: (e) => {
                    e.originalEvent.stopPropagation()
                    e.originalEvent.preventDefault()
                    handleClusterDblClick(cluster)
                  },
                }}
              >
                <Tooltip direction="top" offset={[0, -clusterRadius(cluster.count)]} permanent={cluster.count >= 5}>
                  <span style={{ fontSize: '11px', fontWeight: 'bold' }}>{cluster.count}</span>
                </Tooltip>
                <Popup>
                  <div className="text-center">
                    <img src={thumbUrl(cluster.sample_id)} alt="" className="w-24 h-24 object-cover rounded mb-1" />
                    <div className="font-medium">{cluster.location_name || `${cluster.lat.toFixed(3)}, ${cluster.lon.toFixed(3)}`}</div>
                    <div className="text-gray-500">{cluster.count} {t('search.images')}</div>
                  </div>
                </Popup>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>

        {/* Image gallery */}
        {selectedLocation && (
          <div className="w-1/2 overflow-y-auto bg-gray-950 border-l border-gray-800 p-2">
            {images.length === 0 ? (
              <div className="text-center py-12 text-gray-500">{t('search.no_results')}</div>
            ) : (
              <>
                <div className="grid grid-cols-3 gap-1">
                  {images.map(img => (
                    <div key={img.id} className="relative aspect-square bg-gray-800 rounded overflow-hidden group cursor-pointer hover:scale-105 transition-transform">
                      <img
                        src={thumbUrl(img.id)}
                        alt={img.file_name}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-end">
                        <div className="p-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <div className="text-xs text-white truncate">{img.file_name}</div>
                          {img.exif_date && (
                            <div className="text-xs text-gray-300">{img.exif_date.slice(0, 10)}</div>
                          )}
                          {img.location_name && (
                            <div className="text-xs text-green-300">{img.location_name.split(',')[0]}</div>
                          )}
                        </div>
                      </div>
                      {img.gps_inherited && (
                        <span className="absolute top-1 right-1 bg-yellow-600/80 text-xs px-1 rounded" title="GPS inherited">~📍</span>
                      )}
                    </div>
                  ))}
                </div>
                <div ref={loadMoreRef} className="h-10" />
                {isFetchingNextPage && (
                  <div className="text-center py-4 text-gray-500">{t('search.loading')}</div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
