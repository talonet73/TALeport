import { useQueryClient } from '@tanstack/react-query'
import {
  BookOpen,
  Captions,
  Eye,
  FileText,
  FileUp,
  Film,
  Globe,
  Loader2,
  MessagesSquare,
  RotateCcw,
  Search,
  StickyNote,
  Trash2,
  CirclePlay,
} from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { readAsBase64 } from '../../api/files'
import { aiPost, openExternal } from '../../api/hooks'
import {
  type ResearchProject,
  type ResearchSource,
  type SourceKind,
  researchApi,
  researchKey,
  useResearchAction,
} from '../../api/research'
import { HandoffPanel } from '../../components/ai/HandoffPanel'
import { useAiFlow } from '../../components/ai/useAiFlow'
import { Modal } from '../../components/Modal'
import { useErrorMessage } from '../../components/useErrorMessage'
import { fieldClass, linkButton, primaryButton, secondaryButton } from './styles'

const ICONS: Record<SourceKind, typeof BookOpen> = {
  wikipedia: BookOpen,
  reddit: MessagesSquare,
  youtube: CirclePlay,
  video: Film,
  document: FileText,
  text: StickyNote,
  web: Globe,
}

const minutes = (seconds?: number) =>
  seconds ? `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}` : ''

export function SourcesStep({ project }: { project: ResearchProject }) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [links, setLinks] = useState('')
  const [pasting, setPasting] = useState(false)
  const [pasteTitle, setPasteTitle] = useState('')
  const [pasteText, setPasteText] = useState('')
  const [viewing, setViewing] = useState<ResearchSource | null>(null)
  const id = project.id

  const collect = useResearchAction(id, () => researchApi.collect(id))
  const addVideos = useResearchAction(id, (urls: string[]) => researchApi.addVideos(id, urls))
  const addDocument = useResearchAction(id, async (file: File) =>
    researchApi.addDocument(id, file.name, await readAsBase64(file)),
  )
  const addText = useResearchAction(id, () => researchApi.addText(id, pasteTitle, pasteText))
  const remove = useResearchAction(id, (sourceId: number) => researchApi.deleteSource(sourceId))
  const transcribe = useResearchAction(id, (sourceId: number) => researchApi.transcribe(sourceId))
  const retry = useResearchAction(id, (sourceId: number) => researchApi.retry(sourceId))
  const web = useAiFlow<never>({
    start: () => aiPost(`/research/${id}/web`, {}),
    parse: (text) => aiPost(`/research/${id}/web/parse`, { text }),
    onDone: (envelope) => queryClient.setQueryData(researchKey(id), envelope.project),
  })

  const error = collect.error ?? addVideos.error ?? addDocument.error ?? addText.error ?? transcribe.error
  const ready = project.sources.filter((s) => s.kind !== 'youtube' || s.status !== 'found')
  const suggestions = project.sources.filter((s) => s.kind === 'youtube' && s.status === 'found')

  const sendLinks = () => {
    const urls = links.split(/\s+/).map((u) => u.trim()).filter(Boolean)
    if (urls.length) addVideos.mutate(urls, { onSuccess: () => setLinks('') })
  }

  return (
    <div className="space-y-5">
      {/* Automatic search from the plan */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!project.plan || project.collecting || collect.isPending}
          onClick={() => collect.mutate(undefined)}
          className={primaryButton}
        >
          {project.collecting ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Search className="size-5" aria-hidden />}
          {project.collecting ? t('research.sources.collecting') : t('research.sources.collect')}
        </button>
        <button
          type="button"
          disabled={web.busy}
          onClick={() => void web.run('chat')}
          className={secondaryButton}
          title={t('research.sources.webHint')}
        >
          <Globe className="size-4" aria-hidden />
          {t('research.sources.web')}
        </button>
        {!project.plan && <span className="text-sm text-muted">{t('research.sources.needPlan')}</span>}
      </div>
      {web.phase === 'handoff' && web.handoff && (
        <div className="rounded-2xl border border-line bg-surface-raised p-4">
          <p className="mb-3 text-sm text-muted">{t('research.sources.webExplain')}</p>
          <HandoffPanel handoff={web.handoff} fallback={null} error={web.error} onSubmit={web.submitPasted} />
        </div>
      )}

      {/* Video links */}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2 rounded-2xl border border-line bg-surface-raised p-4">
          <span className="flex items-center gap-2 font-semibold text-ink">
            <Captions className="size-5 text-accent-text" aria-hidden />
            {t('research.sources.videos')}
          </span>
          <textarea
            value={links}
            onChange={(e) => setLinks(e.target.value)}
            rows={3}
            placeholder={t('research.sources.videosPlaceholder')}
            className={fieldClass}
          />
          <button type="button" disabled={!links.trim() || addVideos.isPending} onClick={sendLinks} className={primaryButton}>
            {addVideos.isPending ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Film className="size-5" aria-hidden />}
            {t('research.sources.transcribe')}
          </button>
          <p className="text-xs text-muted">{t('research.sources.videosHint')}</p>
        </div>

        {/* Documents and pasted text */}
        <div className="space-y-2 rounded-2xl border border-line bg-surface-raised p-4">
          <span className="flex items-center gap-2 font-semibold text-ink">
            <FileText className="size-5 text-accent-text" aria-hidden />
            {t('research.sources.yours')}
          </span>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => fileInput.current?.click()} className={secondaryButton}>
              {addDocument.isPending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <FileUp className="size-4" aria-hidden />}
              {t('research.sources.document')}
            </button>
            <button type="button" onClick={() => setPasting(!pasting)} className={secondaryButton}>
              <StickyNote className="size-4" aria-hidden />
              {t('research.sources.paste')}
            </button>
          </div>
          <input
            ref={fileInput}
            type="file"
            multiple
            accept=".pdf,.docx,.pptx,.txt,.md"
            className="hidden"
            onChange={(e) => {
              for (const file of Array.from(e.target.files ?? [])) addDocument.mutate(file)
              e.target.value = ''
            }}
          />
          {pasting && (
            <div className="space-y-2">
              <input value={pasteTitle} onChange={(e) => setPasteTitle(e.target.value)}
                placeholder={t('research.sources.pasteTitle')} className={fieldClass} />
              <textarea value={pasteText} onChange={(e) => setPasteText(e.target.value)} rows={4}
                placeholder={t('research.sources.pastePlaceholder')} className={fieldClass} />
              <button
                type="button"
                disabled={pasteText.trim().length < 100 || addText.isPending}
                onClick={() => addText.mutate(undefined, { onSuccess: () => { setPasteText(''); setPasteTitle(''); setPasting(false) } })}
                className={primaryButton}
              >
                {t('research.sources.add')}
              </button>
            </div>
          )}
          <p className="text-xs text-muted">{t('research.sources.yoursHint')}</p>
        </div>
      </div>
      {error && <p className="text-red-400">{errorMessage(error)}</p>}

      {/* Collected material */}
      {ready.length > 0 && (
        <ul className="divide-y divide-line rounded-2xl border border-line">
          {ready.map((s) => (
            <SourceRow
              key={s.id}
              source={s}
              onView={async () => setViewing(await researchApi.source(s.id))}
              onDelete={() => remove.mutate(s.id)}
              onRetry={() => retry.mutate(s.id)}
            />
          ))}
        </ul>
      )}
      {ready.length === 0 && <p className="text-muted">{t('research.sources.empty')}</p>}

      {suggestions.length > 0 && (
        <div className="space-y-2">
          <h3 className="flex items-center gap-2 font-semibold text-ink">
            <CirclePlay className="size-5 text-red-400" aria-hidden />
            {t('research.sources.suggestions')}
          </h3>
          <ul className="space-y-2">
            {suggestions.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-surface-raised px-3 py-2">
                <button type="button" onClick={() => openExternal(s.url)} className="min-w-0 flex-1 text-left">
                  <span className="block truncate font-medium text-ink hover:underline">{s.title}</span>
                  <span className="text-xs text-muted">
                    {[s.author, minutes(s.meta.duration)].filter(Boolean).join(' · ')}
                  </span>
                </button>
                <button type="button" onClick={() => transcribe.mutate(s.id)} className={linkButton}>
                  {t('research.sources.transcribeOne')}
                </button>
                <button type="button" onClick={() => remove.mutate(s.id)} aria-label={t('common.delete')}
                  className="text-muted hover:text-red-400">
                  <Trash2 className="size-4" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {viewing && <SourceDialog source={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}

function SourceRow({
  source,
  onView,
  onDelete,
  onRetry,
}: {
  source: ResearchSource
  onView: () => void
  onDelete: () => void
  onRetry: () => void
}) {
  const { t } = useTranslation()
  const errorMessage = useErrorMessage()
  const Icon = ICONS[source.kind]
  const working = source.status === 'queued' || source.status === 'processing'
  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3">
      <Icon className="size-5 shrink-0 text-accent-text" aria-hidden />
      <div className="min-w-0 flex-1">
        <span className="block truncate font-medium text-ink">{source.title || source.url}</span>
        <span className="block text-xs text-muted">
          {t(`research.kinds.${source.kind}`)}
          {source.kind === 'wikipedia' && source.language ? ` ${source.language.toUpperCase()}` : ''}
          {source.author ? ` · ${source.author}` : ''}
          {source.meta.duration ? ` · ${minutes(source.meta.duration)}` : ''}
          {source.status === 'ready' && source.digest ? ` · ${t('research.sources.summarized')}` : ''}
        </span>
        {working && (
          <span className="mt-1 flex items-center gap-1.5 text-sm text-accent-text" role="status">
            <Loader2 className="size-4 animate-spin" aria-hidden />
            {source.status === 'queued' ? t('research.step.queued') : t(`research.step.${source.step ?? 'download'}`)}
          </span>
        )}
        {source.status === 'error' && (
          <span className="mt-1 block text-sm text-red-400">{errorMessage({ code: source.error_code })}</span>
        )}
      </div>
      {source.status === 'ready' && (
        <button type="button" onClick={onView} className={`${linkButton} flex items-center gap-1`}>
          <Eye className="size-4" aria-hidden />
          {t('research.sources.view')}
        </button>
      )}
      {source.status === 'error' && source.kind === 'video' && (
        <button type="button" onClick={onRetry} className={`${linkButton} flex items-center gap-1`}>
          <RotateCcw className="size-4" aria-hidden />
          {t('research.sources.retry')}
        </button>
      )}
      {source.url && (
        <button type="button" onClick={() => openExternal(source.url)} className={linkButton}>
          {t('research.sources.open')}
        </button>
      )}
      <button type="button" onClick={onDelete} aria-label={t('common.delete')} className="text-muted hover:text-red-400">
        <Trash2 className="size-4" aria-hidden />
      </button>
    </li>
  )
}

function SourceDialog({ source, onClose }: { source: ResearchSource; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <Modal title={source.title || t(`research.kinds.${source.kind}`)} onClose={onClose} wide>
      <div className="max-h-[70vh] space-y-4 overflow-y-auto">
        {source.digest && (
          <div className="rounded-xl bg-surface-raised p-4">
            <h3 className="mb-2 font-semibold text-ink">{t('research.sources.digest')}</h3>
            {source.digest.summary && <p className="mb-2 text-ink">{source.digest.summary}</p>}
            <ul className="list-disc space-y-1 pl-5 text-ink">
              {source.digest.points.map((p, i) => (
                <li key={i}>
                  {p.time && <span className="mr-1 font-mono text-xs text-accent-text">[{p.time}]</span>}
                  {p.text}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div>
          <h3 className="mb-2 font-semibold text-ink">
            {source.kind === 'video' ? t('research.sources.transcript') : t('research.sources.text')}
          </h3>
          <pre className="whitespace-pre-wrap font-sans text-sm text-muted">{source.content}</pre>
        </div>
      </div>
    </Modal>
  )
}
