interface ProgressBarProps {
  value: number
  max: number
}

export default function ProgressBar({ value, max }: ProgressBarProps) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div className="w-full bg-gray-800 rounded-full h-3 overflow-hidden">
      <div
        className="h-full bg-gradient-to-r from-green-500 to-blue-500 transition-all duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}
