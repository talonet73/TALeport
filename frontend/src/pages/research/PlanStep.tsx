import { Loader2, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'

import { aiPost, useSettings } from '../../api/hooks'
import {
  type ResearchPlan,
  type ResearchProject,
  researchApi,
  researchKey,
  useResearchAction,
} from '../../api/research'
import { HandoffPanel } from '../../components/ai/HandoffPanel'
import { useAiFlow } from '../../components/ai/useAiFlow'
import { TagInput } from '../../components/TagInput'
import { useErrorMessage } from '../../components/useErrorMessage'
import { useQueryClient } from '@tanstack/react-query'
import { primaryButton, secondaryButton } from './styles'

const EMPTY: ResearchPlan = {
  title: '',
  questions: [],
  keywords: {},
  wikipedia: {},
  reddit_queries: [],
  youtube_queries: [],
  content_types: [],
}

export function PlanStep({ project }: { project: ResearchProject }) {
  const { t } = useTranslation()
  const { data: settings } = useSettings()
  const queryClient = useQueryClient()
  const errorMessage = useErrorMessage()
  const [params, setParams] = useSearchParams()
  const [draft, setDraft] = useState<ResearchPlan>(project.plan ?? EMPTY)
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    if (!dirty) setDraft(project.plan ?? EMPTY)
  }, [project.plan, dirty])

  const flow = useAiFlow<never>({
    start: (m) => aiPost(`/research/${project.id}/plan`, { mode: m }),
    parse: (text) => aiPost(`/research/${project.id}/plan/parse`, { text }),
    onDone: (envelope) => {
      queryClient.setQueryData(researchKey(project.id), envelope.project)
      setDirty(false)
    },
  })
  const save = useResearchAction(project.id, (plan: ResearchPlan) => researchApi.update(project.id, { plan }))

  // A new research starts by planning the search right away.
  const started = useRef(false)
  useEffect(() => {
    if (params.get('start') && !project.plan && settings && !started.current) {
      started.current = true
      setParams({}, { replace: true })
      void flow.run(settings.default_ai)
    }
  }, [params, project.plan, settings, flow, setParams])

  const set = <K extends keyof ResearchPlan>(key: K, value: ResearchPlan[K]) => {
    setDraft({ ...draft, [key]: value })
    setDirty(true)
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={flow.busy}
          onClick={() => void flow.run(settings?.default_ai ?? 'chat')}
          className={project.plan ? secondaryButton : primaryButton}
        >
          {flow.busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Sparkles className="size-5" aria-hidden />}
          {project.plan ? t('research.plan.again') : t('research.plan.make')}
        </button>
        {flow.busy && <span className="text-sm text-muted">{t('ai.working')}</span>}
      </div>
      {flow.error !== null && <p className="text-red-400">{errorMessage(flow.error)}</p>}

      {project.plan && (
        <div className="space-y-4">
          <Field label={t('research.plan.questions')}>
            <TagInput values={draft.questions} onChange={(v) => set('questions', v)}
              placeholder={t('research.plan.add')} label={t('research.plan.questions')} />
          </Field>
          {project.languages.map((lang) => (
            <div key={lang} className="grid gap-4 md:grid-cols-2">
              <Field label={`${t('research.plan.keywords')} · ${t(`languages.${lang}`)}`}>
                <TagInput values={draft.keywords[lang] ?? []}
                  onChange={(v) => set('keywords', { ...draft.keywords, [lang]: v })}
                  placeholder={t('research.plan.add')} label={t('research.plan.keywords')} />
              </Field>
              <Field label={`${t('research.plan.wikipedia')} · ${t(`languages.${lang}`)}`}>
                <TagInput values={draft.wikipedia[lang] ?? []}
                  onChange={(v) => set('wikipedia', { ...draft.wikipedia, [lang]: v })}
                  placeholder={t('research.plan.add')} label={t('research.plan.wikipedia')} />
              </Field>
            </div>
          ))}
          <div className="grid gap-4 md:grid-cols-2">
            <Field label={t('research.plan.reddit')}>
              <TagInput values={draft.reddit_queries} onChange={(v) => set('reddit_queries', v)}
                placeholder={t('research.plan.add')} label={t('research.plan.reddit')} />
            </Field>
            <Field label={t('research.plan.youtube')}>
              <TagInput values={draft.youtube_queries} onChange={(v) => set('youtube_queries', v)}
                placeholder={t('research.plan.add')} label={t('research.plan.youtube')} />
            </Field>
          </div>
          {dirty && (
            <div className="flex items-center gap-3">
              <button
                type="button"
                disabled={save.isPending}
                onClick={() => save.mutate(draft, { onSuccess: () => setDirty(false) })}
                className={primaryButton}
              >
                {t('research.plan.save')}
              </button>
              <button type="button" onClick={() => setDirty(false)} className={secondaryButton}>
                {t('common.cancel')}
              </button>
            </div>
          )}
          {save.error && <p className="text-red-400">{errorMessage(save.error)}</p>}
        </div>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-sm font-medium text-ink">{label}</span>
      {children}
    </div>
  )
}
