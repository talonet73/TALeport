import { useState } from 'react'
import { useTranslation } from 'react-i18next'

const STORAGE_KEY = 'taleport.postLength'
const PRESETS = [
  { key: 'short', chars: 300 },
  { key: 'medium', chars: 800 },
  { key: 'long', chars: 1500 },
] as const
export const LENGTH_MIN = 50
export const LENGTH_MAX = 5000

function load(): number | null {
  try {
    const n = Number(localStorage.getItem(STORAGE_KEY))
    return n >= LENGTH_MIN && n <= LENGTH_MAX ? n : null
  } catch {
    return null
  }
}

/** Post length in characters (null = automatic, the platform's usual length). The last choice
 * is remembered and shared by every generation page. */
export function usePostLength(): [number | null, (n: number | null) => void] {
  const [value, setValue] = useState<number | null>(load)
  const set = (n: number | null) => {
    setValue(n)
    try {
      if (n) localStorage.setItem(STORAGE_KEY, String(n))
      else localStorage.removeItem(STORAGE_KEY)
    } catch {
      // storage unavailable: the choice lasts for this page only
    }
  }
  return [value, set]
}

/** Value to send: only a length inside the allowed range (an unfinished number is ignored). */
export const targetChars = (n: number | null) => (n && n >= LENGTH_MIN && n <= LENGTH_MAX ? n : null)

export function LengthPicker({ value, onChange }: { value: number | null; onChange: (n: number | null) => void }) {
  const { t } = useTranslation()
  const chip = (active: boolean) =>
    `rounded-full px-3 py-1.5 text-sm font-medium ${
      active ? 'bg-accent-gradient text-on-accent' : 'border border-line bg-surface-raised text-ink hover:border-accent'
    }`
  const invalid = value !== null && targetChars(value) === null
  return (
    <fieldset>
      <legend className="mb-2 font-medium text-ink">{t('generator.length.label')}</legend>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" aria-pressed={value === null} onClick={() => onChange(null)} className={chip(value === null)}>
          {t('generator.length.auto')}
        </button>
        {PRESETS.map((p) => (
          <button key={p.key} type="button" aria-pressed={value === p.chars} onClick={() => onChange(p.chars)}
            className={chip(value === p.chars)}>
            {t(`generator.length.${p.key}`, { count: p.chars })}
          </button>
        ))}
        <label className="flex items-center gap-2 text-sm text-muted">
          <input
            type="number"
            min={LENGTH_MIN}
            max={LENGTH_MAX}
            step={50}
            value={value ?? ''}
            onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
            placeholder={t('generator.length.custom')}
            aria-label={t('generator.length.custom')}
            className={`w-32 rounded-xl border bg-surface-raised px-3 py-1.5 text-ink outline-none focus:border-accent ${
              invalid ? 'border-red-400' : 'border-line'
            }`}
          />
          {t('generator.length.unit')}
        </label>
      </div>
      <p className={`mt-1 text-xs ${invalid ? 'text-red-400' : 'text-muted'}`}>
        {invalid ? t('generator.length.range', { min: LENGTH_MIN, max: LENGTH_MAX }) : t('generator.length.hint')}
      </p>
    </fieldset>
  )
}
