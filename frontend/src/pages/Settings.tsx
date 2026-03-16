import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import type { AppSettings } from '../api'
import { getSettings, updateSettings } from '../api'
import { useI18n } from '../i18n/useTranslation'

export default function Settings() {
  const { t } = useI18n()
  const { data, isLoading, isError } = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
  })

  const [form, setForm] = useState<Partial<AppSettings>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (data) {
      setForm({
        ollama_model: data.ollama_model,
        ollama_url: data.ollama_url,
        ai_language: data.ai_language,
        ai_quality_enabled: data.ai_quality_enabled,
        phash_threshold: data.phash_threshold,
      })
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: (values: Partial<AppSettings>) => updateSettings(values),
    onSuccess: () => {
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  function handleSave() {
    mutation.mutate(form)
  }

  const inputClass =
    'w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-blue-500'

  if (isLoading) return <div className="text-center py-12 text-gray-400">{t('search.loading')}</div>
  if (isError) return <div className="text-center py-12 text-red-400">Error</div>

  return (
    <div className="max-w-lg space-y-6">
      <h1 className="text-xl font-semibold text-gray-100">{t('nav.settings')}</h1>

      <div className="bg-gray-900 rounded-lg p-5 space-y-5">
        <h2 className="text-sm font-medium text-gray-300 uppercase tracking-wider">Ollama</h2>

        <div className="space-y-1.5">
          <label className="text-sm text-gray-400">{t('settings.model')}</label>
          <input
            type="text"
            value={form.ollama_model ?? ''}
            onChange={e => setForm(f => ({ ...f, ollama_model: e.target.value }))}
            placeholder="llava:7b, moondream"
            className={inputClass}
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-sm text-gray-400">Ollama URL</label>
          <input
            type="text"
            value={form.ollama_url ?? ''}
            onChange={e => setForm(f => ({ ...f, ollama_url: e.target.value }))}
            placeholder="http://localhost:11434"
            className={inputClass}
          />
        </div>
      </div>

      <div className="bg-gray-900 rounded-lg p-5 space-y-5">
        <h2 className="text-sm font-medium text-gray-300 uppercase tracking-wider">AI</h2>

        <div className="space-y-1.5">
          <label className="text-sm text-gray-400">{t('settings.language')}</label>
          <select
            value={form.ai_language ?? 'fi'}
            onChange={e => setForm(f => ({ ...f, ai_language: e.target.value }))}
            className={inputClass}
          >
            <option value="fi">Suomi</option>
            <option value="en">English</option>
          </select>
        </div>

        <div className="flex items-start gap-3">
          <input
            type="checkbox"
            id="quality"
            checked={form.ai_quality_enabled ?? false}
            onChange={e => setForm(f => ({ ...f, ai_quality_enabled: e.target.checked }))}
            className="mt-0.5 w-4 h-4 rounded border-gray-600 bg-gray-800 accent-blue-500 cursor-pointer"
          />
          <div>
            <label htmlFor="quality" className="text-sm text-gray-300 cursor-pointer">
              {t('settings.quality')}
            </label>
            <p className="text-xs text-gray-500 mt-0.5">
              {t('settings.quality_desc')}
            </p>
          </div>
        </div>
      </div>

      <div className="bg-gray-900 rounded-lg p-5 space-y-4">
        <h2 className="text-sm font-medium text-gray-300 uppercase tracking-wider">{t('nav.duplicates')}</h2>

        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <label className="text-gray-400">{t('settings.threshold')}</label>
            <span className="text-gray-300">{form.phash_threshold ?? 10}</span>
          </div>
          <input
            type="range"
            min="1"
            max="20"
            step="1"
            value={form.phash_threshold ?? 10}
            onChange={e => setForm(f => ({ ...f, phash_threshold: Number(e.target.value) }))}
            className="w-full accent-blue-500"
          />
          <div className="flex justify-between text-xs text-gray-500">
            <span>{t('settings.strict')} (1)</span>
            <span>{t('settings.loose')} (20)</span>
          </div>
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={mutation.isPending}
        className={`w-full py-2.5 rounded font-medium text-sm transition-colors ${
          saved
            ? 'bg-green-600 text-white'
            : mutation.isPending
            ? 'bg-gray-700 text-gray-400 cursor-not-allowed'
            : 'bg-blue-600 hover:bg-blue-700 text-white'
        }`}
      >
        {saved ? t('settings.saved') : t('settings.save')}
      </button>
    </div>
  )
}
