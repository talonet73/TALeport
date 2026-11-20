import { Loader2, Search, Telescope, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams } from 'react-router'

import { researchApi, useResearchList } from '../../api/research'
import { LANGUAGES, type Language } from '../../api/types'
import { Card } from '../../components/Card'
import { useErrorMessage } from '../../components/useErrorMessage'
import { ResearchProjectView } from './ResearchProjectView'
import { fieldClass, primaryButton } from './styles'

/** "Research": from a goal written by the author to a dossier, posts and an article. */
export function ResearchPage() {
  const { id } = useParams()
  return id ? <ResearchProjectView id={Number(id)} /> : <ResearchHome />
}

function ResearchHome() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const errorMessage = useErrorMessage()
  const { data: projects = [], refetch } = useResearchList()
  const [goal, setGoal] = useState('')
  const [languages, setLanguages] = useState<Language[]>(() => {
    const ui = (i18n.language as Language) ?? 'it'
    return ui === 'en' ? ['en'] : [ui, 'en']
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      const project = await researchApi.create(goal.trim(), languages)
      navigate(`/research/${project.id}?start=1`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (projectId: number) => {
    if (!window.confirm(t('research.deleteConfirm'))) return
    await researchApi.remove(projectId)
    void refetch()
  }

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <h1 className="flex items-center gap-3 text-3xl font-bold text-ink">
          <Telescope className="size-8 text-accent-text" aria-hidden />
          {t('nav.research')}
        </h1>
        <p className="mt-1 max-w-prose text-muted">{t('research.subtitle')}</p>
      </div>

      <Card>
        <div className="space-y-4">
          <label className="flex flex-col gap-2">
            <span className="font-semibold text-ink">{t('research.goalLabel')}</span>
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={4}
              maxLength={4000}
              placeholder={t('research.goalPlaceholder')}
              className={fieldClass}
            />
          </label>
          <fieldset>
            <legend className="mb-2 font-medium text-ink">{t('research.languages')}</legend>
            <div className="flex flex-wrap gap-2">
              {LANGUAGES.map((lang) => {
                const active = languages.includes(lang)
                return (
                  <button
                    key={lang}
                    type="button"
                    aria-pressed={active}
                    onClick={() =>
                      setLanguages(active ? languages.filter((l) => l !== lang) : [...languages, lang])
                    }
                    className={`rounded-full px-4 py-2 font-medium ${
                      active ? 'bg-accent-gradient text-on-accent' : 'border border-line bg-surface-raised text-ink'
                    }`}
                  >
                    {t(`languages.${lang}`)}
                  </button>
                )
              })}
            </div>
          </fieldset>
          {error !== null && <p className="text-red-400">{errorMessage(error)}</p>}
          <button
            type="button"
            disabled={busy || goal.trim().length < 15 || languages.length === 0}
            onClick={() => void create()}
            className={primaryButton}
          >
            {busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Search className="size-5" aria-hidden />}
            {t('research.start')}
          </button>
          <p className="text-sm text-muted">{t('research.startHint')}</p>
        </div>
      </Card>

      {projects.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xl font-semibold text-ink">{t('research.saved')}</h2>
          {projects.map((p) => (
            <div key={p.id} className="flex items-center gap-3 rounded-2xl border border-line bg-surface p-4">
              <Link to={`/research/${p.id}`} className="min-w-0 flex-1">
                <span className="block truncate font-semibold text-ink">{p.title}</span>
                <span className="block truncate text-sm text-muted">
                  {t('research.sourcesCount', { count: p.sources })}
                  {p.has_dossier ? ` · ${t('research.hasDossier')}` : ''} ·{' '}
                  {new Date(p.updated_at).toLocaleDateString(i18n.language)}
                </span>
              </Link>
              <button
                type="button"
                onClick={() => void remove(p.id)}
                aria-label={t('common.delete')}
                className="rounded-full p-2 text-muted hover:text-red-400"
              >
                <Trash2 className="size-4" aria-hidden />
              </button>
            </div>
          ))}
        </section>
      )}
    </div>
  )
}
