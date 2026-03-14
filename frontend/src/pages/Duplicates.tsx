import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { DuplicateGroup } from '../api'
import { getDuplicates, resolveDuplicate, thumbUrl } from '../api'
import ImageCompare from '../components/ImageCompare'

const MATCH_TYPE_LABELS: Record<string, string> = {
  phash: 'Visuaalinen kopio',
  exact: 'Tarkka kopio',
  filename: 'Sama tiedostonimi',
}

export default function Duplicates() {
  const queryClient = useQueryClient()
  const [groupIndex, setGroupIndex] = useState(0)
  const [pairIndex, setPairIndex] = useState(0)
  const [choices, setChoices] = useState<Record<number, Record<number, string>>>({})

  const { data: groups = [], isLoading, isError } = useQuery({
    queryKey: ['duplicates'],
    queryFn: () => getDuplicates({ limit: 100 }),
  })

  const resolveMutation = useMutation({
    mutationFn: ({ groupId, keepId, rejectIds }: { groupId: number; keepId: number; rejectIds: number[] }) =>
      resolveDuplicate(groupId, keepId, rejectIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['duplicates'] })
      setGroupIndex(i => Math.min(i + 1, groups.length - 1))
      setPairIndex(0)
    },
  })

  const resolved = Object.keys(choices).length
  const total = groups.length

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Ladataan...</div>
  }
  if (isError) {
    return <div className="text-center py-12 text-red-400">Virhe haettaessa duplikaatteja.</div>
  }
  if (groups.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        Ei duplikaatteja löydetty.
      </div>
    )
  }

  const group: DuplicateGroup = groups[groupIndex]
  const members = group.members
  const groupChoices = choices[group.id] ?? {}

  // Build a patched members list with user_choice from local state
  const patchedMembers = members.map(m => ({
    ...m,
    user_choice: groupChoices[m.image_id] ?? m.user_choice,
  }))

  // Pick the two members to compare
  const compareA = patchedMembers[pairIndex]
  const compareB = patchedMembers[pairIndex === 0 ? 1 : 0]

  function handleKeep(imageId: number) {
    const rejectIds = members
      .map(m => m.image_id)
      .filter(id => id !== imageId)
    setChoices(prev => ({
      ...prev,
      [group.id]: {
        [imageId]: 'keep',
        ...Object.fromEntries(rejectIds.map(id => [id, 'reject'])),
      },
    }))
  }

  function handleReject(imageId: number) {
    setChoices(prev => ({
      ...prev,
      [group.id]: {
        ...(prev[group.id] ?? {}),
        [imageId]: 'reject',
      },
    }))
  }

  function handleConfirm() {
    const gc = choices[group.id]
    if (!gc) return
    const keepId = Number(Object.entries(gc).find(([, v]) => v === 'keep')?.[0])
    const rejectIds = Object.entries(gc)
      .filter(([, v]) => v === 'reject')
      .map(([k]) => Number(k))
    if (!keepId) return
    resolveMutation.mutate({ groupId: group.id, keepId, rejectIds })
  }

  const hasChoice = !!choices[group.id]

  return (
    <div className="space-y-4">
      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-gray-400">
          <span>Käsitelty {resolved} / {total}</span>
          <span>{total > 0 ? Math.round((resolved / total) * 100) : 0}%</span>
        </div>
        <div className="w-full bg-gray-800 rounded-full h-2">
          <div
            className="bg-gradient-to-r from-green-500 to-blue-500 h-2 rounded-full transition-all"
            style={{ width: `${total > 0 ? (resolved / total) * 100 : 0}%` }}
          />
        </div>
      </div>

      {/* Group info */}
      <div className="flex items-center gap-4 text-sm text-gray-400">
        <span>Ryhmä {groupIndex + 1} / {total}</span>
        <span className="bg-gray-800 px-2 py-0.5 rounded text-xs">
          {MATCH_TYPE_LABELS[group.match_type] ?? group.match_type}
        </span>
        <span>{members.length} kuvaa</span>
      </div>

      {/* Image compare */}
      <ImageCompare
        memberA={compareA}
        memberB={compareB}
        onKeep={handleKeep}
        onReject={handleReject}
      />

      {/* Thumbnail strip for 3+ images */}
      {members.length > 2 && (
        <div className="flex gap-2 overflow-x-auto py-2">
          {patchedMembers.map((m, idx) => (
            <button
              key={m.image_id}
              onClick={() => setPairIndex(idx)}
              className={`flex-shrink-0 w-16 h-16 rounded overflow-hidden border-2 transition-colors ${
                idx === pairIndex ? 'border-blue-500' : 'border-gray-700 hover:border-gray-500'
              }`}
            >
              <img
                src={thumbUrl(m.image_id)}
                alt=""
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      )}

      {/* Navigation */}
      <div className="flex gap-3 pt-2">
        <button
          onClick={() => { setGroupIndex(i => Math.max(0, i - 1)); setPairIndex(0) }}
          disabled={groupIndex === 0}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed rounded text-sm transition-colors"
        >
          Edellinen
        </button>
        <button
          onClick={() => { setGroupIndex(i => Math.min(total - 1, i + 1)); setPairIndex(0) }}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded text-sm transition-colors"
        >
          Ohita
        </button>
        <button
          onClick={handleConfirm}
          disabled={!hasChoice || resolveMutation.isPending}
          className="px-4 py-2 bg-green-700 hover:bg-green-600 disabled:opacity-40 disabled:cursor-not-allowed rounded text-sm transition-colors ml-auto"
        >
          {resolveMutation.isPending ? 'Tallennetaan...' : 'Vahvista & Seuraava'}
        </button>
      </div>

      {resolveMutation.isError && (
        <p className="text-red-400 text-sm">Virhe tallennettaessa.</p>
      )}
    </div>
  )
}
