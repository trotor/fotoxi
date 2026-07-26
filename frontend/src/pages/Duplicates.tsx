import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { DuplicateGroup, DuplicateMember, BulkResolveSummary } from '../api'
import { getDuplicates, findDuplicates, bulkResolveDuplicates, thumbUrl,
         unresolveDuplicateGroup, getSettings } from '../api'
import { useI18n } from '../i18n/useTranslation'
import { useToast } from '../components/Toast'

/** Human-readable byte size */
function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(0)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${bytes} B`
}

/** Hamming distance between two hex hash strings */
function hammingDistance(a: string | null, b: string | null): number | null {
  if (!a || !b || a.length !== b.length) return null
  let dist = 0
  for (let i = 0; i < a.length; i++) {
    const xor = parseInt(a[i], 16) ^ parseInt(b[i], 16)
    // Count bits in nibble
    dist += ((xor >> 3) & 1) + ((xor >> 2) & 1) + ((xor >> 1) & 1) + (xor & 1)
  }
  return dist
}

function useMatchLabels() {
  const { t } = useI18n()
  return {
    exact: t('dup.exact_copy'),
    phash: t('dup.visual_copy'),
    burst: t('dup.burst'),
    'exact+phash': t('dup.exact_visual'),
    'phash+burst': t('dup.burst_visual'),
    'exact+phash+burst': t('dup.exact_burst_visual'),
  } as Record<string, string>
}

function folderOf(path: string | null | undefined): string {
  if (!path) return ''
  const parts = path.split('/')
  return parts.slice(0, -1).join('/')
}

function shortFolder(path: string | null | undefined): string {
  if (!path) return ''
  const parts = path.split('/').filter(Boolean)
  return parts.slice(-2).join('/')
}

/** Score path quality - prefer cloud originals over downloads/temp */
function pathScore(path: string | null): number {
  if (!path) return 0
  const p = path.toLowerCase()
  if (p.includes('/originals/')) return 30
  if (p.includes('onedrive') || p.includes('googledrive') || p.includes('icloud')) return 20
  if (p.includes('/pictures/') || p.includes('/valokuvat/')) return 15
  if (p.includes('/documents/')) return 10
  if (p.includes('/downloads/')) return 5
  return 10
}

/** Determine why this image is recommended */
function bestReason(m: DuplicateMember, members: DuplicateMember[]): string {
  const img = m.image
  if (!img) return ''
  const reasons: string[] = []
  const maxSize = Math.max(...members.map(m2 => m2.image?.file_size ?? 0))
  const maxPixels = Math.max(...members.map(m2 => (m2.image?.width ?? 0) * (m2.image?.height ?? 0)))
  if (img.file_size === maxSize && members.length > 1) reasons.push('suurin')
  if ((img.width ?? 0) * (img.height ?? 0) === maxPixels && maxPixels > 0) reasons.push('paras resoluutio')
  if (pathScore(img.file_path) >= 20) reasons.push('alkuperainen sijainti')
  return reasons.join(', ') || 'suositeltu'
}

function findBest(members: DuplicateMember[]): number {
  if (!members.length) return 0
  let bestId = members[0].image_id
  let bestScore = 0
  for (const m of members) {
    const img = m.image
    if (!img) continue
    const pixels = (img.width ?? 0) * (img.height ?? 0)
    const size = img.file_size ?? 0
    // Weighted: resolution > size > path quality
    const score = pixels * 1000 + size + pathScore(img.file_path) * 100000
    if (score > bestScore) {
      bestScore = score
      bestId = m.image_id
    }
  }
  return bestId
}

export default function Duplicates() {
  const queryClient = useQueryClient()
  const { toast, confirm } = useToast()
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: getSettings })
  const [dupPage, setDupPage] = useState(1)
  const [rejected, setRejected] = useState<Record<number, Set<number>>>({})
  const [groupIndex, setGroupIndex] = useState(0)
  const [matchTypeFilter, setMatchTypeFilter] = useState<string>('')
  const [cleanupPreview, setCleanupPreview] = useState<BulkResolveSummary | null>(null)
  const [cleanupBusy, setCleanupBusy] = useState(false)
  const [cleanupDone, setCleanupDone] = useState<string | null>(null)
  const [selectMode, setSelectMode] = useState<'keep' | 'reject'>(
    () => (localStorage.getItem('fotoxi_dupSelectMode') === 'reject' ? 'reject' : 'keep')
  )

  function changeSelectMode(mode: 'keep' | 'reject') {
    setSelectMode(mode)
    localStorage.setItem('fotoxi_dupSelectMode', mode)
  }

  const { data: dupData, isLoading, isError } = useQuery({
    queryKey: ['duplicates', dupPage, matchTypeFilter],
    queryFn: () => getDuplicates({ page: dupPage, limit: 20, match_type: matchTypeFilter || undefined }),
  })

  const groups = dupData?.groups ?? []
  const totalGroups = dupData?.total ?? 0
  const matchTypeCounts: Record<string, number> = (dupData as any)?.match_type_counts ?? {}

  const resolveMutation = useMutation({
    mutationFn: async ({ groupId, keepIds, rejectIds }: { groupId: number; keepIds: number[]; rejectIds: number[] }) => {
      const res = await fetch(`/api/duplicates/${groupId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keep: keepIds, reject: rejectIds }),
      })
      if (!res.ok) throw new Error('Resolve failed')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['duplicates'] })
    },
    onError: () => {
      toast(t('dup.resolve_failed'), { variant: 'error' })
    },
  })

  const group: DuplicateGroup | null = groups[groupIndex] ?? null
  const isBurst = !!group && group.match_type.includes('burst')
  const members = group?.members ?? []
  const groupRejected = group ? (rejected[group.id] ?? new Set<number>()) : new Set<number>()
  const keptCount = members.length - groupRejected.size

  const suggestedBestId = useMemo(() => findBest(members), [members])

  const folders = useMemo(() => {
    const set = new Set(members.map(m => m.image ? folderOf(m.image.file_path) : '').filter(Boolean))
    return Array.from(set)
  }, [members])

  const { t } = useI18n()
  const MATCH_TYPE_LABELS = useMatchLabels()

  const [scanning, setScanning] = useState(false)

  const handleFindDuplicates = async () => {
    setScanning(true)
    try {
      await findDuplicates()
      // Poll until complete
      const poll = setInterval(async () => {
        const res = await fetch('/api/indexer/status')
        const status = await res.json()
        if (!status.running) {
          clearInterval(poll)
          setScanning(false)
          queryClient.invalidateQueries({ queryKey: ['duplicates'] })
        }
      }, 2000)
    } catch {
      setScanning(false)
    }
  }

  async function handleCleanupPreview() {
    setCleanupBusy(true)
    setCleanupDone(null)
    try {
      const summary = await bulkResolveDuplicates({ dry_run: true })
      setCleanupPreview(summary)
    } catch {
      /* ignore */
    } finally {
      setCleanupBusy(false)
    }
  }

  async function handleCleanupApply() {
    setCleanupBusy(true)
    try {
      const summary = await bulkResolveDuplicates({ dry_run: false })
      setCleanupPreview(null)
      setCleanupDone(
        `${t('dup.cleanup_done')}: ${summary.rejected} ${t('dup.images')} · ${formatBytes(summary.reclaimable_bytes)}`
      )
      setGroupIndex(0)
      setDupPage(1)
      queryClient.invalidateQueries({ queryKey: ['duplicates'] })
    } catch {
      /* ignore */
    } finally {
      setCleanupBusy(false)
    }
  }

  function handleCleanupCancel() {
    setCleanupPreview(null)
  }

  const findButton = (
    <button
      onClick={handleFindDuplicates}
      disabled={scanning}
      className="px-4 py-2 rounded bg-blue-700 hover:bg-blue-600 text-white text-sm disabled:opacity-50 disabled:cursor-wait"
    >
      {scanning ? t('dup.scanning') : t('dup.find_duplicates')}
    </button>
  )

  if (isLoading) return <div className="text-center py-12 text-gray-400">{t('search.loading')}</div>
  if (isError) return <div className="text-center py-12 text-red-400">{t('common.error')}</div>
  if (groups.length === 0 || !group) return <div className="text-center py-12 text-gray-500">{findButton}<div className="mt-4">{t('dup.no_duplicates')}</div></div>

  function toggleReject(imageId: number) {
    if (!group) return
    setRejected(prev => {
      const current = new Set(prev[group.id] ?? [])
      if (current.has(imageId)) {
        current.delete(imageId)
      } else {
        if (members.length - current.size <= 1) return prev
        current.add(imageId)
      }
      return { ...prev, [group.id]: current }
    })
  }

  /** Keep-mode: clicking picks the single keeper (everything else rejected). */
  function selectKeeper(imageId: number) {
    if (!group) return
    setRejected(prev => {
      const current = prev[group.id] ?? new Set<number>()
      const keptIds = members.map(m => m.image_id).filter(id => !current.has(id))
      // Clicking the current sole keeper clears the selection.
      if (keptIds.length === 1 && keptIds[0] === imageId) {
        const next = { ...prev }
        delete next[group.id]
        return next
      }
      const others = new Set(members.map(m => m.image_id).filter(id => id !== imageId))
      return { ...prev, [group.id]: others }
    })
  }

  function handleImageClick(imageId: number) {
    if (selectMode === 'keep') selectKeeper(imageId)
    else toggleReject(imageId)
  }

  /** Shared post-resolve cleanup: clear this group's local rejection state, advance
   *  past it if it was the last on the page, and refresh the duplicates list. Called
   *  only from resolveAndNext, the single path all resolve actions (including the
   *  burst quick action) now go through. */
  function afterResolve(resolvedGroupId: number) {
    setRejected(prev => {
      const next = { ...prev }
      delete next[resolvedGroupId]
      return next
    })
    // If we're at the end of current page, reset index
    if (groupIndex >= groups.length - 1) {
      setGroupIndex(0)
    }
    queryClient.invalidateQueries({ queryKey: ['duplicates'] })
  }

  /** Resolve with given keep/reject and move to next.
   *
   *  Uses mutateAsync rather than mutate's onSuccess callback: TanStack Query v5
   *  skips mutate-scoped callbacks if the component unmounts before the mutation
   *  settles, but the mutation still lands — which would silently drop the toast
   *  and the undo affordance.
   *
   *  Any resolution that rejects at least one image offers an undo. The database
   *  does not keep the pre-resolution status, so it is captured here beforehand. */
  async function resolveAndNext(keepIds: number[], rejectIds: number[]) {
    if (!group) return
    const groupId = group.id

    const previous: Record<number, string> = {}
    members.forEach(m => {
      if (m.image?.status) previous[m.image_id] = m.image.status
    })

    try {
      await resolveMutation.mutateAsync({ groupId, keepIds, rejectIds })
    } catch {
      return // the mutation-level onError already surfaced the failure
    }
    afterResolve(groupId)

    if (rejectIds.length === 0) return // nothing rejected, nothing to undo

    const runUndo = async () => {
      try {
        await unresolveDuplicateGroup(groupId, previous)
        queryClient.invalidateQueries({ queryKey: ['duplicates'] })
      } catch {
        toast(t('dup.undo_failed'), {
          variant: 'error',
          duration: 12000,
          action: { label: t('common.undo'), onClick: runUndo },
        })
      }
    }
    toast(`${rejectIds.length} ${t('dup.images_rejected')}`, {
      duration: 12000,
      action: { label: t('common.undo'), onClick: runUndo },
    })
  }

  /** One-click: keep largest, reject rest, confirm, next */
  async function handleAutoConfirm() {
    if (!group) return
    const rejectIds = members.filter(m => m.image_id !== suggestedBestId).map(m => m.image_id)
    const keepIds = [suggestedBestId]
    await resolveAndNext(keepIds, rejectIds)
  }

  /** Burst quick action: keep the recommended frame, reject the rest. */
  async function handleBurstReduce() {
    if (!group) return
    const rejectIds = members
      .filter(m => m.image_id !== suggestedBestId)
      .map(m => m.image_id)
    if (rejectIds.length === 0) return

    if (settings?.dup_confirm_quick_actions) {
      const ok = await confirm(t('dup.confirm_reduce'), {
        confirmLabel: t('dup.reject'),
        danger: true,
      })
      if (!ok) return
    }

    await resolveAndNext([suggestedBestId], rejectIds)
  }

  /** One-click: keep images from this folder, reject rest, confirm, next */
  async function handleKeepFolderConfirm(folder: string) {
    if (!group) return
    const keepIds = members.filter(m => m.image && folderOf(m.image.file_path) === folder).map(m => m.image_id)
    const rejectIds = members.filter(m => m.image && folderOf(m.image.file_path) !== folder).map(m => m.image_id)
    if (keepIds.length === 0 || rejectIds.length === 0) return
    await resolveAndNext(keepIds, rejectIds)
  }

  /** Manual select: keep largest, show in UI (don't confirm yet) */
  function handleAutoSelect() {
    if (!group) return
    const toReject = new Set(
      members.filter(m => m.image_id !== suggestedBestId).map(m => m.image_id)
    )
    setRejected(prev => ({ ...prev, [group.id]: toReject }))
  }

  async function handleConfirm() {
    if (!group) return
    const rejectIds = Array.from(groupRejected)
    const keepIds = members.map(m => m.image_id).filter(id => !groupRejected.has(id))
    await resolveAndNext(keepIds, rejectIds)
  }

  /** Reject ALL images in this group */
  async function handleRejectAll() {
    if (!group) return
    const rejectIds = members.map(m => m.image_id)
    await resolveAndNext([], rejectIds)
  }

  /** Keep ALL images in this group and mark as resolved */
  async function handleKeepAll() {
    if (!group) return
    const keepIds = members.map(m => m.image_id)
    await resolveAndNext(keepIds, [])
  }

  function handleSkip() {
    if (!group) return
    setRejected(prev => {
      const next = { ...prev }
      delete next[group.id]
      return next
    })
    if (groupIndex < groups.length - 1) {
      setGroupIndex(i => i + 1)
    } else if ((dupPage) * 20 < totalGroups) {
      setDupPage(p => p + 1)
      setGroupIndex(0)
    }
  }

  // Find the best member for preview
  const bestMember = members.find(m => m.image_id === suggestedBestId)
  const bestImg = bestMember?.image

  return (
    <div className="space-y-4 max-w-4xl mx-auto p-4">
      {/* Actions + filter */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-500">{t('search.show')}:</span>
        <button
          onClick={() => { setMatchTypeFilter(''); setDupPage(1); setGroupIndex(0) }}
          className={`text-xs px-2 py-1 rounded transition-colors ${
            !matchTypeFilter ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          {t('search.all')} ({Object.values(matchTypeCounts).reduce((a, b) => a + b, 0) || totalGroups})
        </button>
        {Object.entries(matchTypeCounts).sort(([,a], [,b]) => b - a).map(([type, count]) => (
          <button
            key={type}
            onClick={() => { setMatchTypeFilter(type === matchTypeFilter ? '' : type); setDupPage(1); setGroupIndex(0) }}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              matchTypeFilter === type ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {MATCH_TYPE_LABELS[type] ?? type} ({count})
          </button>
        ))}
        <div className="ml-auto">{findButton}</div>
      </div>

      {/* Bulk cleanup of copy-type duplicates (keep best, reject rest) */}
      <div className="bg-gray-900/60 border border-gray-800 rounded-lg p-3">
        {cleanupDone ? (
          <div className="flex items-center gap-3">
            <span className="text-sm text-green-400">✓ {cleanupDone}</span>
            <button onClick={() => setCleanupDone(null)} className="text-xs text-gray-500 hover:text-gray-300">✕</button>
          </div>
        ) : cleanupPreview ? (
          cleanupPreview.groups === 0 ? (
            <div className="flex items-center gap-3">
              <span className="text-sm text-gray-400">{t('dup.cleanup_none')}</span>
              <button onClick={handleCleanupCancel} className="text-xs text-gray-500 hover:text-gray-300">{t('dup.cleanup_cancel')}</button>
            </div>
          ) : (
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm text-gray-200">
                {t('dup.cleanup_reject')} <span className="text-red-400 font-medium">{cleanupPreview.rejected}</span> {t('dup.images')}
                {' · '}<span className="text-gray-300">{cleanupPreview.groups}</span> {t('dup.cleanup_groups')}
                {' · '}{t('dup.cleanup_frees')} <span className="text-green-400 font-medium">{formatBytes(cleanupPreview.reclaimable_bytes)}</span>
              </span>
              <button
                onClick={handleCleanupApply}
                disabled={cleanupBusy}
                className="bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded transition-colors font-medium"
              >
                {cleanupBusy ? t('common.saving') : t('dup.cleanup_apply')}
              </button>
              <button onClick={handleCleanupCancel} disabled={cleanupBusy} className="text-xs text-gray-500 hover:text-gray-300">{t('dup.cleanup_cancel')}</button>
            </div>
          )
        ) : (
          <div className="flex items-center gap-3 flex-wrap">
            <button
              onClick={handleCleanupPreview}
              disabled={cleanupBusy}
              className="bg-blue-800 hover:bg-blue-700 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded transition-colors font-medium"
            >
              🧹 {cleanupBusy ? t('dup.cleanup_checking') : t('dup.cleanup_copies')}
            </button>
            <span className="text-xs text-gray-500">{t('dup.cleanup_hint')}</span>
          </div>
        )}
      </div>

      {/* Progress */}
      <div className="flex justify-between items-center text-sm text-gray-400">
        <span>{t('dup.group')} {(dupPage - 1) * 20 + groupIndex + 1} / {totalGroups}</span>
        <span className="bg-gray-800 px-2 py-0.5 rounded text-xs">
          {MATCH_TYPE_LABELS[group.match_type] ?? group.match_type}
        </span>
        <span>{members.length} {t('dup.images')}</span>
        {(() => {
          const bestPhash = members.find(m2 => m2.image_id === suggestedBestId)?.image?.phash
          if (!bestPhash) return null
          const dists = members
            .filter(m2 => m2.image_id !== suggestedBestId && m2.image?.phash)
            .map(m2 => hammingDistance(m2.image!.phash, bestPhash))
            .filter((d): d is number => d !== null)
          if (!dists.length) return null
          const min = Math.min(...dists)
          const max = Math.max(...dists)
          return (
            <span className="text-xs text-gray-500">
              {t('dup.phash_distance')}: {min === max ? min : `${min}-${max}`}
            </span>
          )
        })()}
      </div>

      {/* Default action - prominent. Bursts default to 'keep all' (never auto-reject frames). */}
      {isBurst ? (
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={handleKeepAll}
              disabled={resolveMutation.isPending}
              className="flex-1 min-w-[9rem] bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm px-4 py-3 rounded-lg transition-colors font-medium"
            >
              {t('dup.burst_keep_all')} ({members.length})
            </button>
            <button
              onClick={handleBurstReduce}
              disabled={resolveMutation.isPending || members.length < 2}
              className="flex-1 min-w-[9rem] bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-200 text-sm px-4 py-3 rounded-lg border border-gray-600 transition-colors font-medium"
            >
              {t('dup.keep_recommended_short')} ({t('dup.reject_count')} {members.length - 1})
            </button>
          </div>
          <p className="text-xs text-amber-400/80">{t('dup.burst_note')}</p>
        </div>
      ) : (
        <button
          onClick={handleAutoConfirm}
          disabled={resolveMutation.isPending}
          className="w-full bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm px-4 py-3 rounded-lg transition-colors font-medium"
        >
          {bestImg
            ? `${t('dup.keep_recommended')} (${bestImg.file_name.slice(0, 30)}${bestImg.file_name.length > 30 ? '...' : ''} · ${(bestImg.file_size / 1024 / 1024).toFixed(1)} MB)`
            : t('dup.keep_recommended_full')}
        </button>
      )}

      {/* Other actions */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={handleAutoSelect}
          disabled={resolveMutation.isPending}
          className="bg-green-900/40 hover:bg-green-800/60 disabled:opacity-40 text-green-300 text-xs px-3 py-1.5 rounded border border-green-700 transition-colors font-medium"
        >
          ⌾ {t('dup.select_recommended')}
        </button>
        <button
          onClick={handleKeepAll}
          disabled={resolveMutation.isPending}
          className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-300 text-xs px-3 py-1.5 rounded border border-gray-600 transition-colors"
        >
          {t('dup.keep_all')}
        </button>
        <button
          onClick={handleRejectAll}
          disabled={resolveMutation.isPending}
          className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-red-400 text-xs px-3 py-1.5 rounded border border-red-900 transition-colors"
        >
          {t('dup.reject_all')}
        </button>

        {folders.length > 1 && folders.map(folder => {
          const folderCount = members.filter(m => m.image && folderOf(m.image.file_path) === folder).length
          const rejectCount = members.length - folderCount
          return (
            <button
              key={folder}
              onClick={() => handleKeepFolderConfirm(folder)}
              disabled={resolveMutation.isPending || rejectCount === 0}
              className="bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-blue-400 text-xs px-3 py-1.5 rounded border border-blue-900 transition-colors"
              title={folder}
            >
              {t('dup.keep_folder')} .../{shortFolder(folder).split('/').pop()} ({t('dup.reject_count')} {rejectCount})
            </button>
          )
        })}
      </div>

      {/* Manual selection: click-mode toggle + preselect the recommended keeper */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-600">{t('dup.mode_label')}</span>
        <div className="inline-flex rounded overflow-hidden border border-gray-700 text-xs">
          <button
            onClick={() => changeSelectMode('keep')}
            className={`px-2 py-1 transition-colors ${
              selectMode === 'keep' ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {t('dup.mode_keep')}
          </button>
          <button
            onClick={() => changeSelectMode('reject')}
            className={`px-2 py-1 transition-colors ${
              selectMode === 'reject' ? 'bg-blue-700 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            {t('dup.mode_reject')}
          </button>
        </div>
        <span className="text-xs text-gray-600">{t('dup.mode_hint')}</span>
      </div>

      {/* Image grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {members.map((m: DuplicateMember) => {
          const img = m.image
          if (!img) return null
          const isRejected = groupRejected.has(m.image_id)
          const isSuggested = m.image_id === suggestedBestId
          const isKept = groupRejected.size > 0 && !isRejected
          const folder = shortFolder(folderOf(img.file_path))
          const isDerivative = (img.file_path || '').includes('/derivatives/') || (img.file_path || '').includes('/resources/')
          return (
            <div
              key={m.image_id}
              onClick={() => handleImageClick(m.image_id)}
              className={`relative rounded-lg overflow-hidden cursor-pointer transition-all border-2 ${
                isRejected
                  ? 'border-red-600 opacity-40 scale-95'
                  : isKept
                  ? 'border-green-500 ring-1 ring-green-500'
                  : isSuggested
                  ? 'border-green-500 hover:border-green-400'
                  : 'border-gray-700 hover:border-blue-500'
              }`}
            >
              <img
                src={thumbUrl(m.image_id)}
                alt={img.file_name}
                className="w-full aspect-square object-cover bg-gray-800"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
              {isRejected && (
                <div className="absolute inset-0 bg-red-900/40 flex items-center justify-center">
                  <span className="text-red-300 text-2xl font-bold">X</span>
                </div>
              )}
              {isSuggested && !isRejected && (
                <div className="absolute top-1 right-1 bg-green-600 text-white text-xs px-1.5 py-0.5 rounded">
                  {bestReason(m, members)}
                </div>
              )}
              {isKept && !isSuggested && (
                <div className="absolute top-1 right-1 bg-green-600 text-white text-xs px-1.5 py-0.5 rounded">
                  ✓ {t('dup.kept_badge')}
                </div>
              )}
              {isDerivative && !isRejected && (
                <div className="absolute top-1 left-1 bg-yellow-700 text-yellow-200 text-xs px-1.5 py-0.5 rounded">
                  Kopio
                </div>
              )}
              <div className="p-2 bg-gray-900 space-y-0.5">
                <p className="text-xs text-gray-300 truncate">{img.file_name}</p>
                <div className="text-xs text-gray-500">
                  {img.exif_date?.slice(0, 10) || ''}
                  {img.width && img.height ? ` · ${img.width}x${img.height}` : ''}
                </div>
                <p className="text-xs text-gray-500">
                  {img.file_size ? `${(img.file_size / 1024 / 1024).toFixed(1)} MB` : ''}
                  {img.exif_iso ? ` · ISO ${img.exif_iso}` : ''}
                </p>
                <p className={`text-xs truncate ${isDerivative ? 'text-yellow-600' : 'text-gray-600'}`} title={folderOf(img.file_path)}>
                  {folder}
                </p>
                {img.phash && (() => {
                  const bestPhash = members.find(m2 => m2.image_id === suggestedBestId)?.image?.phash
                  const dist = m.image_id !== suggestedBestId ? hammingDistance(img.phash, bestPhash ?? null) : null
                  return (
                    <p className="text-xs text-gray-700 font-mono truncate" title={`pHash: ${img.phash}`}>
                      {img.phash.slice(0, 8)}...
                      {dist !== null && (
                        <span className={`ml-1 ${dist === 0 ? 'text-red-400' : dist < 5 ? 'text-orange-400' : 'text-yellow-500'}`}>
                          d={dist}
                        </span>
                      )}
                    </p>
                  )
                })()}
              </div>
            </div>
          )
        })}
      </div>

      {/* Status */}
      {groupRejected.size > 0 && (
        <div className="text-sm text-gray-400">
          {t('dup.keeping')}: <span className="text-green-400 font-medium">{keptCount}</span> ·
          {t('dup.rejecting')}: <span className="text-red-400 font-medium">{groupRejected.size}</span>
        </div>
      )}

      {/* Navigation */}
      <div className="flex gap-3">
        <button
          onClick={() => setGroupIndex(i => Math.max(0, i - 1))}
          disabled={groupIndex === 0}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 rounded text-sm"
        >
          {t('dup.prev')}
        </button>
        <button onClick={handleSkip} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm">
          {t('dup.skip')}
        </button>
        {groupRejected.size > 0 && (
          <button
            onClick={handleConfirm}
            disabled={resolveMutation.isPending}
            className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-40 rounded text-sm ml-auto"
          >
            {resolveMutation.isPending ? t('common.saving') : `${t('dup.confirm')} (${groupRejected.size})`}
          </button>
        )}
      </div>
    </div>
  )
}
