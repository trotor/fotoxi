import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { DuplicateGroup, DuplicateMember } from '../api'
import { getDuplicates, thumbUrl } from '../api'
import { useI18n } from '../i18n/useTranslation'

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
  return { phash: t('dup.visual_copy'), burst: t('dup.burst'), 'phash+burst': t('dup.burst_visual') } as Record<string, string>
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
  const [dupPage, setDupPage] = useState(1)
  const [rejected, setRejected] = useState<Record<number, Set<number>>>({})
  const [groupIndex, setGroupIndex] = useState(0)

  const { data: dupData, isLoading, isError } = useQuery({
    queryKey: ['duplicates', dupPage],
    queryFn: () => getDuplicates({ page: dupPage, limit: 20 }),
  })

  const groups = dupData?.groups ?? []
  const totalGroups = dupData?.total ?? 0

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
  })

  const group: DuplicateGroup | null = groups[groupIndex] ?? null
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

  if (isLoading) return <div className="text-center py-12 text-gray-400">{t('search.loading')}</div>
  if (isError) return <div className="text-center py-12 text-red-400">Error</div>
  if (groups.length === 0 || !group) return <div className="text-center py-12 text-gray-500">{t('dup.no_duplicates')}</div>

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

  /** Resolve with given keep/reject and move to next */
  function resolveAndNext(keepIds: number[], rejectIds: number[]) {
    if (!group) return
    resolveMutation.mutate(
      { groupId: group.id, keepIds, rejectIds },
      {
        onSuccess: () => {
          setRejected(prev => {
            const next = { ...prev }
            delete next[group.id]
            return next
          })
          // If we're at the end of current page, reset index
          if (groupIndex >= groups.length - 1) {
            setGroupIndex(0)
          }
          queryClient.invalidateQueries({ queryKey: ['duplicates'] })
        },
      }
    )
  }

  /** One-click: keep largest, reject rest, confirm, next */
  function handleAutoConfirm() {
    if (!group) return
    const rejectIds = members.filter(m => m.image_id !== suggestedBestId).map(m => m.image_id)
    const keepIds = [suggestedBestId]
    resolveAndNext(keepIds, rejectIds)
  }

  /** One-click: keep images from this folder, reject rest, confirm, next */
  function handleKeepFolderConfirm(folder: string) {
    if (!group) return
    const keepIds = members.filter(m => m.image && folderOf(m.image.file_path) === folder).map(m => m.image_id)
    const rejectIds = members.filter(m => m.image && folderOf(m.image.file_path) !== folder).map(m => m.image_id)
    if (keepIds.length === 0 || rejectIds.length === 0) return
    resolveAndNext(keepIds, rejectIds)
  }

  /** Manual select: keep largest, show in UI (don't confirm yet) */
  function handleAutoSelect() {
    if (!group) return
    const toReject = new Set(
      members.filter(m => m.image_id !== suggestedBestId).map(m => m.image_id)
    )
    setRejected(prev => ({ ...prev, [group.id]: toReject }))
  }

  function handleConfirm() {
    if (!group) return
    const rejectIds = Array.from(groupRejected)
    const keepIds = members.map(m => m.image_id).filter(id => !groupRejected.has(id))
    resolveAndNext(keepIds, rejectIds)
  }

  /** Reject ALL images in this group */
  function handleRejectAll() {
    if (!group) return
    const rejectIds = members.map(m => m.image_id)
    resolveAndNext([], rejectIds)
  }

  /** Keep ALL images in this group and mark as resolved */
  function handleKeepAll() {
    if (!group) return
    const keepIds = members.map(m => m.image_id)
    resolveAndNext(keepIds, [])
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
              pHash etäisyys: {min === max ? min : `${min}-${max}`}
            </span>
          )
        })()}
      </div>

      {/* Default action - prominent */}
      <button
        onClick={handleAutoConfirm}
        disabled={resolveMutation.isPending}
        className="w-full bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm px-4 py-3 rounded-lg transition-colors font-medium"
      >
        {bestImg
          ? `${t('dup.keep_recommended')} (${bestImg.file_name.slice(0, 30)}${bestImg.file_name.length > 30 ? '...' : ''} · ${(bestImg.file_size / 1024 / 1024).toFixed(1)} MB)`
          : t('dup.keep_recommended_full')}
      </button>

      {/* Other actions */}
      <div className="flex flex-wrap gap-2">
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
              Säilytä .../{shortFolder(folder).split('/').pop()} (hylkää {rejectCount})
            </button>
          )
        })}
      </div>

      {/* Manual mode hint */}
      <div className="flex items-center gap-2">
        <p className="text-xs text-gray-600">
          Tai valitse manuaalisesti klikkaamalla kuvia:
        </p>
        <button
          onClick={handleAutoSelect}
          className="text-xs text-blue-400 hover:text-blue-300"
        >
          Esivalitse suurin
        </button>
      </div>

      {/* Image grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {members.map((m: DuplicateMember) => {
          const img = m.image
          if (!img) return null
          const isRejected = groupRejected.has(m.image_id)
          const isSuggested = m.image_id === suggestedBestId
          const folder = shortFolder(folderOf(img.file_path))
          const isDerivative = (img.file_path || '').includes('/derivatives/') || (img.file_path || '').includes('/resources/')
          return (
            <div
              key={m.image_id}
              onClick={() => toggleReject(m.image_id)}
              className={`relative rounded-lg overflow-hidden cursor-pointer transition-all border-2 ${
                isRejected
                  ? 'border-red-600 opacity-40 scale-95'
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
          Säilytetään: <span className="text-green-400 font-medium">{keptCount}</span> ·
          Hylätään: <span className="text-red-400 font-medium">{groupRejected.size}</span>
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
