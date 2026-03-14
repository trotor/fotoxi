import type { DuplicateMember } from '../api'
import { thumbUrl } from '../api'

interface ImageCompareProps {
  memberA: DuplicateMember
  memberB: DuplicateMember
  onKeep: (imageId: number) => void
  onReject: (imageId: number) => void
}

function formatBytes(b: number): string {
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / (1024 * 1024)).toFixed(1)} MB`
}

function MemberCard({
  member,
  onKeep,
  onReject,
}: {
  member: DuplicateMember
  onKeep: () => void
  onReject: () => void
}) {
  const { image, is_best, user_choice } = member
  const kept = user_choice === 'keep'
  const rejected = user_choice === 'reject'

  return (
    <div
      className={`rounded-lg overflow-hidden border-2 transition-colors ${
        kept
          ? 'border-green-500'
          : rejected
          ? 'border-red-700 opacity-50'
          : 'border-gray-700'
      }`}
    >
      <img
        src={thumbUrl(image.id)}
        alt={image.file_name}
        className="w-full aspect-square object-cover bg-gray-800"
      />
      <div className="p-3 bg-gray-900 space-y-2">
        <p className="text-sm font-medium text-gray-200 truncate" title={image.file_name}>
          {image.file_name}
        </p>
        <div className="text-xs text-gray-400 space-y-0.5">
          {image.exif_date && <p>{image.exif_date.slice(0, 10)}</p>}
          <p>{formatBytes(image.file_size)}</p>
          {image.width != null && image.height != null && (
            <p>
              {image.width} × {image.height} px
            </p>
          )}
          {image.exif_aperture != null && <p>f/{image.exif_aperture}</p>}
          {image.exif_iso != null && <p>ISO {image.exif_iso}</p>}
          {image.exif_exposure && <p>{image.exif_exposure}s</p>}
        </div>
        {(is_best || image.ai_quality_score != null) && (
          <div
            className={`text-xs px-2 py-1 rounded ${
              is_best ? 'bg-green-900/50 text-green-300' : 'bg-gray-800 text-gray-400'
            }`}
          >
            {is_best && <span className="font-medium">Suositus: paras</span>}
            {image.ai_quality_score != null && (
              <span className={is_best ? ' ml-1' : ''}>
                Laatu: {image.ai_quality_score.toFixed(1)}
              </span>
            )}
          </div>
        )}
        <div className="flex gap-2 pt-1">
          <button
            onClick={onKeep}
            disabled={kept}
            className="flex-1 bg-green-700 hover:bg-green-600 disabled:bg-green-900 disabled:opacity-60 text-white text-xs py-1.5 rounded transition-colors"
          >
            Säilytä
          </button>
          <button
            onClick={onReject}
            disabled={rejected}
            className="flex-1 bg-red-800 hover:bg-red-700 disabled:bg-red-950 disabled:opacity-60 text-white text-xs py-1.5 rounded transition-colors"
          >
            Hylkää
          </button>
        </div>
      </div>
    </div>
  )
}

export default function ImageCompare({ memberA, memberB, onKeep, onReject }: ImageCompareProps) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <MemberCard
        member={memberA}
        onKeep={() => onKeep(memberA.image_id)}
        onReject={() => onReject(memberA.image_id)}
      />
      <MemberCard
        member={memberB}
        onKeep={() => onKeep(memberB.image_id)}
        onReject={() => onReject(memberB.image_id)}
      />
    </div>
  )
}
