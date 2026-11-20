import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Sparkles, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aiPost, openExternal, useSettings } from '../../api/hooks'
import {
  DOSSIER_SECTIONS,
  type Dossier,
  type ResearchProject,
  researchApi,
  researchKey,
  useResearchAction,
} from '../../api/research'
import { HandoffPanel } from '../../components/ai/HandoffPanel'
import { useAiFlow } from '../../components/ai/useAiFlow'
import { Toggle } from '../../components/Toggle'
import { useErrorMessage } from '../../components/useErrorMessage'
import { primaryButton, secondaryButton } from './styles'

type Section = (typeof DOSSIER_SECTIONS)[number] | 'ai_knowledge'

export function DossierStep({ project }: { project: ResearchProject }) {
  const { t } = useTranslation()
  const { data: settings } = useSettings()
  const queryClient = useQueryClient()
  const errorMessage = useErrorMessage()
  const [aiKnowledge, setAiKnowledge] = useState(false)
  const id = project.id
  const ready = project.sources.filter((s) => s.status === 'ready').length
  const working = project.sources.some((s) => s.status === 'queued' || s.status === 'processing')

  const flow = useAiFlow<never>({
    start: (m) => aiPost(`/research/${id}/dossier`, { mode: m, ai_knowledge: aiKnowledge }),
    parse: (text) => aiPost(`/research/${id}/dossier/parse`, { text }),
    onDone: (envelope) => queryClient.setQueryData(researchKey(id), envelope.project),
  })
  const save = useResearchAction(id, (dossier: Dossier) => researchApi.update(id, { dossier }))

  const removeItem = (section: Section, index: number) => {
    if (!project.dossier) return
    const next = { ...project.dossier, [section]: project.dossier[section].filter((_, i) => i !== index) }
    save.mutate(next)
  }

  if (flow.phase === 'handoff' && flow.handoff) {
    return (
      <HandoffPanel
        handoff={flow.handoff}
        fallback={flow.fallback}
        error={flow.error}
        onSubmit={flow.submitPasted}
        onRetry={(m) => void flow.run(m)}
      />
    )
  }

  const dossier = project.dossier
  const sourceOf = (n: number) => dossier?.sources.find((s) => s.n === n)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          disabled={!ready || flow.busy}
          onClick={() => void flow.run(settings?.default_ai ?? 'chat')}
          className={dossier ? secondaryButton : primaryButton}
        >
          {flow.busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Sparkles className="size-5" aria-hidden />}
          {dossier ? t('research.dossier.again') : t('research.dossier.make', { count: ready })}
        </button>
        <label className="flex items-center gap-2 text-sm text-ink">
          <Toggle checked={aiKnowledge} onChange={setAiKnowledge} label={t('research.dossier.aiKnowledge')} />
          {t('research.dossier.aiKnowledge')}
        </label>
      </div>
      {flow.busy && <p className="text-sm text-muted">{t('research.dossier.working')}</p>}
      {working && !flow.busy && <p className="text-sm text-muted">{t('research.dossier.waitVideos')}</p>}
      {!ready && <p className="text-sm text-muted">{t('research.dossier.needSources')}</p>}
      {(flow.error ?? save.error) && <p className="text-red-400">{errorMessage(flow.error ?? save.error)}</p>}

      {dossier && (
        <div className="space-y-4">
          {dossier.summary && <p className="max-w-prose text-ink">{dossier.summary}</p>}
          {[...DOSSIER_SECTIONS, 'ai_knowledge' as const].map((section) =>
            dossier[section].length === 0 ? null : (
              <div
                key={section}
                className={`rounded-2xl p-4 ${
                  section === 'ai_knowledge' ? 'border border-dashed border-amber-400/60' : 'bg-surface-raised'
                }`}
              >
                <h3 className="mb-2 font-semibold text-ink">{t(`research.sections.${section}`)}</h3>
                {section === 'ai_knowledge' && (
                  <p className="mb-2 text-xs text-amber-300">{t('research.dossier.aiKnowledgeNote')}</p>
                )}
                <ul className="space-y-2">
                  {dossier[section].map((item, index) => (
                    <li key={index} className="group flex items-start gap-2 text-ink">
                      <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                      <span className="flex-1">
                        {item.text}
                        {item.sources.map((n) => {
                          const source = sourceOf(n)
                          return (
                            <button
                              key={n}
                              type="button"
                              title={source?.title}
                              onClick={() => source?.url && openExternal(source.url)}
                              className="ml-1 rounded bg-surface px-1.5 text-xs font-semibold text-accent-text"
                            >
                              {n}
                            </button>
                          )
                        })}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeItem(section, index)}
                        aria-label={t('research.dossier.removeItem')}
                        title={t('research.dossier.removeItem')}
                        className="text-muted opacity-0 group-hover:opacity-100 hover:text-red-400 focus:opacity-100"
                      >
                        <X className="size-4" aria-hidden />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ),
          )}
          {dossier.gaps.length > 0 && (
            <div className="text-sm text-muted">
              <span className="font-medium">{t('research.dossier.gaps')}</span> {dossier.gaps.join(' · ')}
            </div>
          )}
          <details className="text-sm text-muted">
            <summary className="cursor-pointer">{t('research.dossier.sourcesList', { count: dossier.sources.length })}</summary>
            <ol className="mt-2 space-y-1">
              {dossier.sources.map((s) => (
                <li key={s.n}>
                  [{s.n}] {s.title}
                  {s.url && (
                    <button type="button" onClick={() => openExternal(s.url)} className="ml-2 text-accent-text hover:underline">
                      {t('research.sources.open')}
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </details>
        </div>
      )}
    </div>
  )
}
