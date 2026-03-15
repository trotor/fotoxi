import { useEffect, useState } from 'react'
import { browseDirectory, type BrowseResult } from '../api'

interface FolderBrowserProps {
  onSelect: (path: string) => void
  onCancel: () => void
}

export default function FolderBrowser({ onSelect, onCancel }: FolderBrowserProps) {
  const [data, setData] = useState<BrowseResult | null>(null)
  const [loading, setLoading] = useState(true)

  const navigate = (path: string) => {
    setLoading(true)
    browseDirectory(path)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(() => { navigate('~') }, [])

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={onCancel}>
      <div className="bg-gray-900 rounded-xl w-full max-w-lg mx-4 max-h-[70vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="p-4 border-b border-gray-700">
          <h3 className="font-bold text-sm mb-2">Valitse kansio</h3>
          <p className="text-xs text-gray-400 font-mono truncate">{data?.current ?? '...'}</p>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {loading && <p className="text-gray-500 text-sm p-2">Ladataan...</p>}

          {!loading && data && (
            <>
              {data.current !== data.parent && (
                <button
                  onClick={() => navigate(data.parent)}
                  className="w-full text-left px-3 py-2 rounded hover:bg-gray-800 text-sm text-blue-400 flex items-center gap-2"
                >
                  <span>{'<-'}</span> ..
                </button>
              )}
              {data.dirs.map(dir => (
                <button
                  key={dir.path}
                  onClick={() => navigate(dir.path)}
                  className="w-full text-left px-3 py-2 rounded hover:bg-gray-800 text-sm text-gray-200 flex items-center gap-2"
                >
                  <span className="text-yellow-500">D</span>
                  {dir.name}
                </button>
              ))}
              {data.dirs.length === 0 && (
                <p className="text-gray-500 text-sm p-2">Tyhjä kansio</p>
              )}
            </>
          )}
        </div>

        <div className="p-3 border-t border-gray-700 flex gap-2">
          <button onClick={onCancel} className="flex-1 py-2 bg-gray-700 hover:bg-gray-600 rounded text-sm">
            Peruuta
          </button>
          <button
            onClick={() => data && onSelect(data.current)}
            className="flex-1 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm"
          >
            Valitse tämä kansio
          </button>
        </div>
      </div>
    </div>
  )
}
