const BASE = '/api'

export interface ImageData {
  id: number
  file_path: string
  file_name: string
  file_size: number
  width: number | null
  height: number | null
  format: string | null
  exif_date: string | null
  exif_camera_make: string | null
  exif_camera_model: string | null
  exif_gps_lat: number | null
  exif_gps_lon: number | null
  exif_focal_length: number | null
  exif_aperture: number | null
  exif_iso: number | null
  exif_exposure: string | null
  phash: string | null
  ai_description: string | null
  ai_tags: string[]
  ai_quality_score: number | null
  ai_model: string | null
  status: string
  source_type: string
  indexed_at: string | null
}

export interface SearchResponse {
  images: ImageData[]
  total: number
  page: number
  limit: number
}

export interface DuplicateMember {
  image_id: number
  is_best: boolean
  user_choice: string | null
  image: ImageData
}

export interface DuplicateGroup {
  id: number
  match_type: string
  created_at: string | null
  members: DuplicateMember[]
}

export interface DbSummary {
  total: number
  pending: number
  indexed: number
  kept: number
  rejected: number
  error: number
  missing: number
  videos: number
  videos_pending: number
  videos_indexed: number
  ai_done: number
  ai_missing: number
  formats: Record<string, number>
}

export interface IndexerStatus {
  running: boolean
  phase: string
  total: number
  processed: number
  errors: number
  speed: number
  current_file: string
  current_file_path?: string
  current_image_id?: number
  current_source_dir?: string
  completed_source_dirs?: string[]
  recent_log?: string[]
  ai_total?: number
  ai_processed?: number
  ai_speed?: number
  ai_current_file?: string
  db_summary?: DbSummary
}

export interface AppSettings {
  ollama_model: string
  ollama_url: string
  ai_language: string
  ai_quality_enabled: boolean
  phash_threshold: number
  source_dirs: string[]
}

export async function searchImages(params: {
  q?: string
  date_from?: string
  date_to?: string
  camera?: string
  min_quality?: number
  status?: string
  exclude?: string
  folder?: string
  media?: string
  time_near?: string
  time_range?: number
  sort?: string
  order?: string
  page?: number
  limit?: number
}): Promise<SearchResponse> {
  const query = new URLSearchParams()
  if (params.q) query.set('q', params.q)
  if (params.date_from) query.set('date_from', params.date_from)
  if (params.date_to) query.set('date_to', params.date_to)
  if (params.camera) query.set('camera', params.camera)
  if (params.min_quality != null) query.set('min_quality', String(params.min_quality))
  if (params.status) query.set('status', params.status)
  if (params.exclude) query.set('exclude', params.exclude)
  if (params.folder) query.set('folder', params.folder)
  if (params.media) query.set('media', params.media)
  if (params.time_near) query.set('time_near', params.time_near)
  if (params.time_range) query.set('time_range', String(params.time_range))
  if (params.sort) query.set('sort', params.sort)
  if (params.order) query.set('order', params.order)
  if (params.page != null) query.set('page', String(params.page))
  if (params.limit != null) query.set('limit', String(params.limit))
  const res = await fetch(`${BASE}/images?${query}`)
  if (!res.ok) throw new Error(`Search failed: ${res.status}`)
  return res.json()
}

export async function getImageDetail(id: number): Promise<ImageData> {
  const res = await fetch(`${BASE}/images/${id}`)
  if (!res.ok) throw new Error(`Image fetch failed: ${res.status}`)
  return res.json()
}

export function thumbUrl(id: number): string {
  return `${BASE}/images/${id}/thumb`
}

export async function updateImageStatus(id: number, status: string): Promise<void> {
  const res = await fetch(`${BASE}/images/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  })
  if (!res.ok) throw new Error(`Status update failed: ${res.status}`)
}

export function fullUrl(id: number): string {
  return `${BASE}/images/${id}/full`
}

export async function getDuplicates(params?: { page?: number; limit?: number }): Promise<DuplicateGroup[]> {
  const query = new URLSearchParams()
  if (params?.page != null) query.set('page', String(params.page))
  if (params?.limit != null) query.set('limit', String(params.limit))
  const res = await fetch(`${BASE}/duplicates?${query}`)
  if (!res.ok) throw new Error(`Duplicates fetch failed: ${res.status}`)
  return res.json()
}

export async function resolveDuplicate(groupId: number, keepId: number, rejectIds: number[]): Promise<void> {
  const res = await fetch(`${BASE}/duplicates/${groupId}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keep_id: keepId, reject_ids: rejectIds }),
  })
  if (!res.ok) throw new Error(`Resolve failed: ${res.status}`)
}

export async function getIndexerStatus(): Promise<IndexerStatus> {
  const res = await fetch(`${BASE}/indexer/status`)
  if (!res.ok) throw new Error(`Status fetch failed: ${res.status}`)
  return res.json()
}

export async function startIndexer(): Promise<void> {
  const res = await fetch(`${BASE}/indexer/start`, { method: 'POST' })
  if (!res.ok) throw new Error(`Start failed: ${res.status}`)
}

export async function processOnly(): Promise<void> {
  const res = await fetch(`${BASE}/indexer/process`, { method: 'POST' })
  if (!res.ok) throw new Error(`Process failed: ${res.status}`)
}

export async function stopIndexer(): Promise<void> {
  const res = await fetch(`${BASE}/indexer/stop`, { method: 'POST' })
  if (!res.ok) throw new Error(`Stop failed: ${res.status}`)
}

export async function getSettings(): Promise<AppSettings> {
  const res = await fetch(`${BASE}/settings`)
  if (!res.ok) throw new Error(`Settings fetch failed: ${res.status}`)
  return res.json()
}

export async function updateSettings(settings: Partial<AppSettings>): Promise<AppSettings> {
  const res = await fetch(`${BASE}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  })
  if (!res.ok) throw new Error(`Settings update failed: ${res.status}`)
  return res.json()
}

export interface CloudFolder {
  label: string
  path: string
}

export async function getCloudFolders(): Promise<CloudFolder[]> {
  const res = await fetch(`${BASE}/cloud-folders`)
  if (!res.ok) throw new Error(`Cloud folders fetch failed: ${res.status}`)
  return res.json()
}

export interface FolderInfo {
  path: string
  short: string
  count: number
  indexed: number
  depth: number
}

export async function getImageFolders(): Promise<FolderInfo[]> {
  const res = await fetch(`${BASE}/folders`)
  if (!res.ok) throw new Error(`Folders fetch failed: ${res.status}`)
  return res.json()
}

export interface StatsData {
  status_counts: Record<string, number>
  total: number
  gps_count: number
  date_min: string | null
  date_max: string | null
  cameras: { model: string; count: number }[]
  total_size_bytes: number
  years: { year: string; count: number }[]
  duplicate_groups: number
  duplicate_images: number
}

export async function getStats(): Promise<StatsData> {
  const res = await fetch(`${BASE}/stats`)
  if (!res.ok) throw new Error(`Stats failed: ${res.status}`)
  return res.json()
}

export async function excludeFolder(path: string): Promise<{ excluded: string; rejected_count: number }> {
  const res = await fetch(`${BASE}/folders/exclude`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) throw new Error(`Exclude failed: ${res.status}`)
  return res.json()
}

export interface BrowseResult {
  current: string
  parent: string
  dirs: { name: string; path: string }[]
}

export async function browseDirectory(path: string = '~'): Promise<BrowseResult> {
  const res = await fetch(`${BASE}/browse?path=${encodeURIComponent(path)}`)
  if (!res.ok) throw new Error(`Browse failed: ${res.status}`)
  return res.json()
}
