import { BrowserRouter, NavLink, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Search from './pages/Search'
import Duplicates from './pages/Duplicates'
import Indexing from './pages/Indexing'
import Settings from './pages/Settings'

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

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-950 text-gray-100">
          <nav className="bg-gray-900 border-b border-gray-700 px-4 py-3">
            <div className="max-w-7xl mx-auto flex items-center gap-2">
              <img src="/favicon.svg" alt="Fotoxi" className="w-7 h-7" />
              <span className="text-white font-bold text-lg mr-4">Fotoxi</span>
              <NavLink to="/search" className={navLinkClass}>Haku</NavLink>
              <NavLink to="/duplicates" className={navLinkClass}>Duplikaatit</NavLink>
              <NavLink to="/indexing" className={navLinkClass}>Indeksointi</NavLink>
              <NavLink to="/settings" className={navLinkClass}>Asetukset</NavLink>
            </div>
          </nav>
          <main className="max-w-7xl mx-auto px-4 py-6">
            <Routes>
              <Route path="/" element={<Navigate to="/search" replace />} />
              <Route path="/search" element={<Search />} />
              <Route path="/duplicates" element={<Duplicates />} />
              <Route path="/indexing" element={<Indexing />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
