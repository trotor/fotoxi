import { useState, useRef, useEffect } from 'react'
import { BrowserRouter, NavLink, Routes, Route, Navigate } from 'react-router-dom'
import { useI18n } from './i18n/useTranslation'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Search from './pages/Search'
import Duplicates from './pages/Duplicates'
import Indexing from './pages/Indexing'
import Settings from './pages/Settings'
import Stats from './pages/Stats'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
})

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `px-4 py-2 rounded text-sm font-medium transition-colors ${
    isActive
      ? 'bg-gray-700 text-white'
      : 'text-gray-400 hover:text-white hover:bg-gray-800'
  }`

function LangToggle() {
  const { lang, setLang } = useI18n()
  return (
    <button
      onClick={() => setLang(lang === 'fi' ? 'en' : 'fi')}
      className="ml-auto text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
      title={lang === 'fi' ? 'Switch to English' : 'Vaihda suomeksi'}
    >
      {lang === 'fi' ? '🇫🇮 FI' : '🇬🇧 EN'}
    </button>
  )
}

function HelpButton() {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="w-7 h-7 rounded-full bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white text-sm font-bold transition-colors flex items-center justify-center"
        title={t('help.title')}
      >
        ?
      </button>
      {open && (
        <div className="absolute right-0 top-10 w-72 bg-gray-800 border border-gray-600 rounded-lg shadow-xl z-50 p-4">
          <h3 className="text-white font-semibold text-sm mb-3">{t('help.title')}</h3>

          <div className="space-y-2 mb-4">
            <a href="https://trotor.github.io/fotoxi/" target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300">
              <span>📖</span> {t('help.docs')}
            </a>
            <a href="https://github.com/trotor/fotoxi" target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm text-blue-400 hover:text-blue-300">
              <span>💻</span> {t('help.github')}
            </a>
          </div>

          <h4 className="text-gray-400 text-xs font-semibold uppercase mb-2">{t('help.shortcuts_title')}</h4>
          <div className="space-y-1 text-xs text-gray-300">
            <div className="flex justify-between"><span>{t('help.shortcut_keep')}</span><kbd className="bg-gray-700 px-1.5 py-0.5 rounded text-gray-400">Enter</kbd></div>
            <div className="flex justify-between"><span>{t('help.shortcut_reject')}</span><kbd className="bg-gray-700 px-1.5 py-0.5 rounded text-gray-400">Backspace</kbd></div>
            <div className="flex justify-between"><span>{t('help.shortcut_nav')}</span><kbd className="bg-gray-700 px-1.5 py-0.5 rounded text-gray-400">← →</kbd></div>
            <div className="flex justify-between"><span>{t('help.shortcut_close')}</span><kbd className="bg-gray-700 px-1.5 py-0.5 rounded text-gray-400">Esc</kbd></div>
          </div>

          <div className="mt-3 pt-3 border-t border-gray-700 text-xs text-gray-500">
            {t('help.version')} 0.2.0
          </div>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const { t } = useI18n()
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-950 text-gray-100">
          <nav className="bg-gray-900 border-b border-gray-700 px-4 py-3">
            <div className="max-w-7xl mx-auto flex items-center gap-2">
              <img src="/favicon.svg" alt="Fotoxi" className="w-7 h-7" />
              <div className="mr-4">
                <span className="text-white font-bold text-lg">Fotoxi</span>
                <span className="text-gray-600 text-xs ml-1">v0.2.0</span>
              </div>
              <NavLink to="/search" className={navLinkClass}>{t('nav.search')}</NavLink>
              <NavLink to="/duplicates" className={navLinkClass}>{t('nav.duplicates')}</NavLink>
              <NavLink to="/indexing" className={navLinkClass}>{t('nav.indexing')}</NavLink>
              <NavLink to="/stats" className={navLinkClass}>{t('nav.stats')}</NavLink>
              <NavLink to="/settings" className={navLinkClass}>{t('nav.settings')}</NavLink>
              <LangToggle />
              <HelpButton />
            </div>
          </nav>
          <main className="max-w-7xl mx-auto px-4 py-6">
            <Routes>
              <Route path="/" element={<Navigate to="/search" replace />} />
              <Route path="/search" element={<Search />} />
              <Route path="/duplicates" element={<Duplicates />} />
              <Route path="/indexing" element={<Indexing />} />
              <Route path="/stats" element={<Stats />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
