import { create } from 'zustand'
import en from './en.json'
import fi from './fi.json'

type Lang = 'en' | 'fi'
const translations: Record<Lang, Record<string, string>> = { en, fi }

interface I18nStore {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: string) => string
}

export const useI18n = create<I18nStore>((set, get) => ({
  lang: 'fi', // Default Finnish
  setLang: (lang: Lang) => {
    set({ lang })
    // Persist to backend
    fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ui_language: lang }),
    }).catch(() => {})
  },
  t: (key: string) => {
    const { lang } = get()
    return translations[lang]?.[key] ?? translations.en[key] ?? key
  },
}))

// Load saved language from backend on startup
fetch('/api/settings')
  .then(r => r.json())
  .then(s => {
    if (s.ui_language && (s.ui_language === 'en' || s.ui_language === 'fi')) {
      useI18n.getState().setLang(s.ui_language)
    }
  })
  .catch(() => {})
