import { ArrowLeft, Check, Loader2, Pencil } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'

import { researchApi, useResearch, useResearchAction } from '../../api/research'
import { ContentStep } from './ContentStep'
import { DossierStep } from './DossierStep'
import { PlanStep } from './PlanStep'
import { SourcesStep } from './SourcesStep'
import { fieldClass } from './styles'

export function Step({
  number,
  title,
  hint,
  done,
  children,
}: {
  number: number
  title: string
  hint: string
  done: boolean
  children: ReactNode
}) {
  return (
    <section className="rounded-3xl border border-line bg-surface p-5 shadow-card md:p-6">
      <header className="mb-4 flex items-start gap-3">
        <span
          className={`grid size-9 shrink-0 place-items-center rounded-full font-bold ${
            done ? 'bg-emerald-500 text-white' : 'bg-accent-gradient text-on-accent'
          }`}
        >
          {done ? <Check className="size-5" aria-hidden /> : number}
        </span>
        <div>
          <h2 className="text-xl font-semibold text-ink">{title}</h2>
          <p className="max-w-prose text-sm text-muted">{hint}</p>
        </div>
      </header>
      {children}
    </section>
  )
}

export function ResearchProjectView({ id }: { id: number }) {
  const { t } = useTranslation()
  const { data: project, isLoading } = useResearch(id)
  const [editingGoal, setEditingGoal] = useState(false)
  const [goal, setGoal] = useState('')
  const save = useResearchAction(id, (changes: { goal?: string; title?: string }) =>
    researchApi.update(id, changes),
  )

  if (isLoading || !project) {
    return <Loader2 className="size-8 animate-spin text-muted" aria-label={t('common.loading')} />
  }
  const ready = project.sources.filter((s) => s.status === 'ready').length

  return (
    <div className="max-w-5xl space-y-6">
      <div>
        <Link to="/research" className="mb-2 inline-flex items-center gap-1 text-sm text-accent-text hover:underline">
          <ArrowLeft className="size-4" aria-hidden />
          {t('research.back')}
        </Link>
        <h1 className="text-3xl font-bold text-ink">{project.title}</h1>
        {editingGoal ? (
          <div className="mt-2 space-y-2">
            <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} className={fieldClass} />
            <button
              type="button"
              onClick={() => save.mutate({ goal }, { onSuccess: () => setEditingGoal(false) })}
              className="rounded-full bg-accent-gradient px-4 py-1.5 font-semibold text-on-accent"
            >
              {t('common.save')}
            </button>
          </div>
        ) : (
          <p className="mt-1 flex max-w-prose items-start gap-2 text-muted">
            <span className="whitespace-pre-wrap">{project.goal}</span>
            <button
              type="button"
              onClick={() => {
                setGoal(project.goal)
                setEditingGoal(true)
              }}
              aria-label={t('research.editGoal')}
              title={t('research.editGoal')}
              className="mt-0.5 shrink-0 text-accent-text"
            >
              <Pencil className="size-4" aria-hidden />
            </button>
          </p>
        )}
      </div>

      <Step number={1} title={t('research.plan.title')} hint={t('research.plan.hint')} done={!!project.plan}>
        <PlanStep project={project} />
      </Step>
      <Step
        number={2}
        title={t('research.sources.title')}
        hint={t('research.sources.hint')}
        done={ready > 0}
      >
        <SourcesStep project={project} />
      </Step>
      <Step number={3} title={t('research.dossier.title')} hint={t('research.dossier.hint')} done={!!project.dossier}>
        <DossierStep project={project} />
      </Step>
      <Step number={4} title={t('research.content.title')} hint={t('research.content.hint')} done={!!project.article}>
        <ContentStep project={project} />
      </Step>
    </div>
  )
}
