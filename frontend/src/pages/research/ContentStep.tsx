import { useQueryClient } from '@tanstack/react-query'
import { ClipboardCopy, FileDown, Loader2, Newspaper, PenLine } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, jsonBody } from '../../api/client'
import { aiPost, copyToClipboard, useSettings } from '../../api/hooks'
import { articleAsMarkdown, type ResearchProject, researchApi, researchKey } from '../../api/research'
import type { Language, Platform } from '../../api/types'
import { useVoices } from '../../api/voices'
import { AiNotesHint } from '../../components/ai/AiNotesPanel'
import { HandoffPanel } from '../../components/ai/HandoffPanel'
import { useAiFlow } from '../../components/ai/useAiFlow'
import { GenerationResults } from '../../components/drafts/GenerationPanel'
import { LanguagePicker, PlatformPicker } from '../../components/drafts/Pickers'
import { useErrorMessage } from '../../components/useErrorMessage'
import { VoiceSelect } from '../../components/voices/VoiceSelect'
import { fieldClass, primaryButton, secondaryButton } from './styles'

type Tab = 'posts' | 'article'

export function ContentStep({ project }: { project: ResearchProject }) {
  const { t } = useTranslation()
  const [tab, setTab] = useState<Tab>('posts')

  if (!project.dossier) return <p className="text-muted">{t('research.content.needDossier')}</p>

  return (
    <div className="space-y-4">
      <div className="inline-flex rounded-full border border-line bg-surface-raised p-1" role="tablist">
        {(['posts', 'article'] as const).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 rounded-full px-4 py-2 font-medium ${
              tab === key ? 'bg-accent-gradient text-on-accent' : 'text-ink'
            }`}
          >
            {key === 'posts' ? <PenLine className="size-4" aria-hidden /> : <Newspaper className="size-4" aria-hidden />}
            {t(`research.content.${key}`)}
          </button>
        ))}
      </div>
      {tab === 'posts' ? <PostsFromDossier project={project} /> : <ArticleFromDossier project={project} />}
    </div>
  )
}

function PostsFromDossier({ project }: { project: ResearchProject }) {
  const { t } = useTranslation()
  const { data: settings } = useSettings()
  const errorMessage = useErrorMessage()
  const [platforms, setPlatforms] = useState<Platform[]>(['instagram'])
  const [languages, setLanguages] = useState<Language[]>([project.languages[0] ?? 'it'])
  const [count, setCount] = useState(3)
  const [voice, setVoice] = useState('')
  const [batchId, setBatchId] = useState<string | null>(null)

  const request = async () => {
    const dossier = await researchApi.dossierText(project.id)
    return {
      content: dossier.text,
      title: dossier.title,
      count,
      platforms,
      language: languages[0],
      topic_id: null,
      voice_id: voice ? Number(voice) : null,
    }
  }
  const flow = useAiFlow<never>({
    start: async (m) => aiPost('/generator/long', { ...(await request()), mode: m }),
    parse: async (text) => aiPost('/generator/long/parse', { ...(await request()), text }),
    onDone: (envelope) => setBatchId(envelope.batch_id ?? null),
  })

  return (
    <div className="space-y-4">
      <PlatformPicker value={platforms} onChange={setPlatforms} />
      <div className="grid gap-4 md:grid-cols-3">
        <LanguagePicker value={languages} onChange={setLanguages} single />
        <label className="flex flex-col gap-2">
          <span className="font-medium text-ink">{t('research.content.count')}</span>
          <select value={count} onChange={(e) => setCount(Number(e.target.value))} className={fieldClass}>
            {[1, 2, 3, 4, 5, 6, 7].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <VoiceSelect value={voice} onChange={setVoice} defaultLabel={t('research.content.defaultTone')} />
      </div>
      {flow.phase === 'handoff' && flow.handoff ? (
        <HandoffPanel handoff={flow.handoff} fallback={flow.fallback} error={flow.error}
          onSubmit={flow.submitPasted} onRetry={(m) => void flow.run(m)} />
      ) : (
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            disabled={!platforms.length || flow.busy}
            onClick={() => void flow.run(settings?.default_ai ?? 'chat')}
            className={primaryButton}
          >
            {flow.busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <PenLine className="size-5" aria-hidden />}
            {t('research.content.makePosts', { count: count * platforms.length })}
          </button>
          <AiNotesHint />
        </div>
      )}
      {flow.error !== null && flow.phase !== 'handoff' && <p className="text-red-400">{errorMessage(flow.error)}</p>}
      {batchId && <GenerationResults batchId={batchId} />}
    </div>
  )
}

function ArticleFromDossier({ project }: { project: ResearchProject }) {
  const { t } = useTranslation()
  const { data: settings } = useSettings()
  const { data: voices = [] } = useVoices()
  const queryClient = useQueryClient()
  const errorMessage = useErrorMessage()
  const [language, setLanguage] = useState<Language>(project.article?.language ?? project.languages[0] ?? 'it')
  const [length, setLength] = useState<'short' | 'medium' | 'long'>('medium')
  const [voice, setVoice] = useState('')
  const [notice, setNotice] = useState('')
  const [exportError, setExportError] = useState<unknown>(null)
  const tone = voices.find((v) => String(v.id) === voice)?.guide ?? ''

  const flow = useAiFlow<never>({
    start: (m) => aiPost(`/research/${project.id}/article`, { language, length, tone, mode: m }),
    parse: (text) => aiPost(`/research/${project.id}/article/parse`, { text, language }),
    onDone: (envelope) => queryClient.setQueryData(researchKey(project.id), envelope.project),
  })
  const article = project.article

  const copy = async () => {
    if (!article) return
    await copyToClipboard(articleAsMarkdown(article, project.dossier))
    setNotice(t('research.article.copied'))
  }
  const word = async () => {
    setExportError(null)
    try {
      const file = await researchApi.articleDocx(project.id)
      await api<void>('/exports/open', { method: 'POST', body: jsonBody({ name: file.name, folder: false }) })
      setNotice(t('research.article.saved', { name: file.name }))
    } catch (err) {
      setExportError(err)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <LanguagePicker value={[language]} onChange={(v) => v[0] && setLanguage(v[0])} single label={t('research.article.language')} />
        <label className="flex flex-col gap-2">
          <span className="font-medium text-ink">{t('research.article.length')}</span>
          <select value={length} onChange={(e) => setLength(e.target.value as typeof length)} className={fieldClass}>
            {(['short', 'medium', 'long'] as const).map((key) => (
              <option key={key} value={key}>
                {t(`research.article.lengths.${key}`)}
              </option>
            ))}
          </select>
        </label>
        <VoiceSelect value={voice} onChange={setVoice} defaultLabel={t('research.content.defaultTone')} />
      </div>
      {flow.phase === 'handoff' && flow.handoff ? (
        <HandoffPanel handoff={flow.handoff} fallback={flow.fallback} error={flow.error}
          onSubmit={flow.submitPasted} onRetry={(m) => void flow.run(m)} />
      ) : (
        <div className="flex flex-wrap items-center gap-4">
          <button
            type="button"
            disabled={flow.busy}
            onClick={() => void flow.run(settings?.default_ai ?? 'chat')}
            className={article ? secondaryButton : primaryButton}
          >
            {flow.busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Newspaper className="size-5" aria-hidden />}
            {article ? t('research.article.again') : t('research.article.make')}
          </button>
          <AiNotesHint />
        </div>
      )}
      {flow.error !== null && flow.phase !== 'handoff' && <p className="text-red-400">{errorMessage(flow.error)}</p>}

      {article && (
        <article className="space-y-4 rounded-2xl bg-surface-raised p-5 md:p-7">
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void copy()} className={secondaryButton}>
              <ClipboardCopy className="size-4" aria-hidden />
              {t('research.article.copy')}
            </button>
            <button type="button" onClick={() => void word()} className={secondaryButton}>
              <FileDown className="size-4" aria-hidden />
              {t('research.article.word')}
            </button>
            {notice && <span className="self-center text-sm text-emerald-400">{notice}</span>}
          </div>
          {exportError !== null && <p className="text-red-400">{errorMessage(exportError)}</p>}
          <h2 className="text-2xl font-bold text-ink">{article.title}</h2>
          {article.subtitle && <p className="text-lg text-muted italic">{article.subtitle}</p>}
          {article.intro.split('\n\n').map((p, i) => (
            <p key={`i${i}`} className="leading-relaxed text-ink">{p}</p>
          ))}
          {article.sections.map((section, i) => (
            <section key={i} className="space-y-2">
              {section.heading && <h3 className="text-xl font-semibold text-ink">{section.heading}</h3>}
              {section.paragraphs.map((p, j) => (
                <p key={j} className="leading-relaxed text-ink">{p}</p>
              ))}
            </section>
          ))}
          {article.conclusion.split('\n\n').map((p, i) => (
            <p key={`c${i}`} className="leading-relaxed text-ink">{p}</p>
          ))}
        </article>
      )}
    </div>
  )
}
