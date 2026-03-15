import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { DuplicateGroup, DuplicateMember } from '../api'
import { getDuplicates, thumbUrl } from '../api'

const MATCH_TYPE_LABELS: Record<string, string> = {
  phash: 'Visuaalinen kopio',
  burst: 'Sarjakuvaus',
  'phash+burst': 'Kopio + sarjakuvaus',
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

function findBest(members: DuplicateMember[]): number {
  if (!members.length) return 0
  let bestId = members[0].image_id
  let bestScore = 0
  for (const m of members) {
    const img = m.image
    if (!img) continue
    const pixels = (img.width ?? 0) * (img.height ?? 0)
    const size = img.file_size ?? 0
    const score = pixels * 1000 + size
    if (score > bestScore) {
      bestScore = score
      bestId = m.image_id
    }
  }
  return bestId
}

export default function Duplicates() {
  const queryClient = useQueryClient()
  const [groupIndex, setGroupIndex] = useState(0)
  const [rejected, setRejected] = useState<Record<number, Set<number>>>({})

  const { data: groups = [], isLoading, isError } = useQuery({
    queryKey: ['duplicates'],
    queryFn: () => getDuplicates({ limit: 200 }),
  })

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

  if (isLoading) return <div className="text-center py-12 text-gray-400">Ladataan...</div>
  if (isError) return <div className="text-center py-12 text-red-400">Virhe haettaessa duplikaatteja.</div>
  if (groups.length === 0 || !group) return <div className="text-center py-12 text-gray-500">Ei duplikaatteja.</div>

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
          if (groupIndex < groups.length - 1) setGroupIndex(i => i + 1)
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
    if (groupIndex < groups.length - 1) setGroupIndex(i => i + 1)
  }

  // Find the best member for preview
  const bestMember = members.find(m => m.image_id === suggestedBestId)
  const bestImg = bestMember?.image

  return (
    <div className="space-y-4 max-w-4xl mx-auto p-4">
      {/* Progress */}
      <div className="flex justify-between items-center text-sm text-gray-400">
        <span>Ryhmä {groupIndex + 1} / {groups.length}</span>
        <span className="bg-gray-800 px-2 py-0.5 rounded text-xs">
          {MATCH_TYPE_LABELS[group.match_type] ?? group.match_type}
        </span>
        <span>{members.length} kuvaa</span>
      </div>

      {/* One-click actions - the main workflow */}
      <div className="bg-gray-900 rounded-lg p-3 space-y-2">
        <p className="text-xs text-gray-500 mb-2">Pikatoiminnot (valitse & vahvista yhdellä klikkauksella):</p>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={handleKeepAll}
            disabled={resolveMutation.isPending}
            className="bg-gray-700 hover:bg-gray-600 disabled:opacity-40 text-gray-200 text-sm px-4 py-2 rounded transition-colors"
          >
            Säilytä kaikki & seuraava
          </button>
          <button
            onClick={handleAutoConfirm}
            disabled={resolveMutation.isPending}
            className="bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white text-sm px-4 py-2 rounded transition-colors"
          >
            Säilytä suurin ({bestImg ? `${bestImg.file_name.slice(0, 25)}${bestImg.file_name.length > 25 ? '...' : ''} · ${(bestImg.file_size / 1024 / 1024).toFixed(1)} MB` : '?'}) & seuraava
          </button>

          {folders.length > 1 && folders.map(folder => {
            const folderCount = members.filter(m => m.image && folderOf(m.image.file_path) === folder).length
            const rejectCount = members.length - folderCount
            return (
              <button
                key={folder}
                onClick={() => handleKeepFolderConfirm(folder)}
                disabled={resolveMutation.isPending || rejectCount === 0}
                className="bg-blue-800 hover:bg-blue-700 disabled:opacity-40 text-blue-200 text-xs px-3 py-2 rounded transition-colors"
                title={folder}
              >
                Säilytä .../{shortFolder(folder).split('/').pop()} (hylkää {rejectCount})
              </button>
            )
          })}
        </div>
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
                  Suurin
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
          Edellinen
        </button>
        <button onClick={handleSkip} className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm">
          Ohita
        </button>
        {groupRejected.size > 0 && (
          <button
            onClick={handleConfirm}
            disabled={resolveMutation.isPending}
            className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-40 rounded text-sm ml-auto"
          >
            {resolveMutation.isPending ? 'Tallennetaan...' : `Vahvista (hylkää ${groupRejected.size})`}
          </button>
        )}
      </div>
    </div>
  )
}
