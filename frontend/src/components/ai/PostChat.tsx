import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Send } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aiPost, useSettings } from '../../api/hooks'
import type { AiMode, Handoff } from '../../api/types'
import { useErrorMessage } from '../useErrorMessage'
import { HandoffPanel } from './HandoffPanel'
import { addChatMessage, toggleChatTarget, usePostChat } from './postChatStore'

const MAX_REQUEST = 1500

/**
 * Chat on the post: the author writes a correction and presses Send; the drafts of the last
 * generation (the selected ones) are rewritten in place by the selected AI.
 */
export function PostChat() {
  const { t } = useTranslation()
  const { data: settings } = useSettings()
  const queryClient = useQueryClient()
  const errorMessage = useErrorMessage()
  const chat = usePostChat()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<{ draftId: number; handoff: Handoff; request: string } | null>(null)
  const [pasteError, setPasteError] = useState<unknown>(null)
  const log = useRef<HTMLDivElement>(null)

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight })
  }, [chat.messages.length])

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['drafts'] })
    void queryClient.invalidateQueries({ queryKey: ['generation'] })
  }

  const send = async (request = text.trim(), mode: AiMode = settings?.default_ai ?? 'chat', echo = true) => {
    const ids = chat.selected.filter((id) => chat.targets.some((target) => target.id === id))
    if (!request || !ids.length || busy) return
    if (echo) addChatMessage({ role: 'user', text: request })
    setText('')
    setPending(null)
    setBusy(true)
    let done = 0
    try {
      for (const id of ids) {
        const envelope = await aiPost<never>(`/drafts/${id}/revise`, { request, mode })
        if (envelope.handoff) {
          // With "Open in chat" the posts are corrected one at a time.
          setPending({ draftId: id, handoff: envelope.handoff, request })
          addChatMessage({ role: 'app', text: t('aiNotes.chat.handoff') })
          break
        }
        done++
      }
      if (done) {
        refresh()
        addChatMessage({ role: 'app', text: t('aiNotes.chat.done', { count: done }) })
      }
    } catch (err) {
      if (done) refresh()
      addChatMessage({ role: 'app', text: errorMessage(err), error: true })
    } finally {
      setBusy(false)
    }
  }

  const submitPasted = async (answer: string) => {
    if (!pending) return
    setPasteError(null)
    try {
      await aiPost<never>(`/drafts/${pending.draftId}/revise/parse`, { text: answer })
      refresh()
      setPending(null)
      addChatMessage({ role: 'app', text: t('aiNotes.chat.done', { count: 1 }) })
    } catch (err) {
      setPasteError(err)
    }
  }

  if (chat.targets.length === 0) {
    return <p className="rounded-xl bg-surface-raised p-3 text-sm text-muted">{t('aiNotes.chat.empty')}</p>
  }

  return (
    <div className="flex flex-col gap-3">
      <div>
        <span className="mb-1.5 block text-xs font-medium text-muted">{t('aiNotes.chat.targets')}</span>
        <div className="flex flex-wrap gap-1.5">
          {chat.targets.map((target) => {
            const active = chat.selected.includes(target.id)
            return (
              <button
                key={target.id}
                type="button"
                aria-pressed={active}
                title={target.label}
                onClick={() => toggleChatTarget(target.id)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  active ? 'bg-accent-gradient text-on-accent' : 'border border-line bg-surface-raised text-muted'
                }`}
              >
                {t(`platforms.${target.platform}`)} · {target.language.toUpperCase()}
              </button>
            )
          })}
        </div>
      </div>

      {chat.messages.length > 0 && (
        <div ref={log} className="flex max-h-48 flex-col gap-2 overflow-y-auto pr-1" aria-live="polite">
          {chat.messages.map((message, i) => (
            <p
              key={i}
              className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${
                message.role === 'user'
                  ? 'self-end bg-accent-gradient text-on-accent'
                  : message.error
                    ? 'self-start bg-red-500/15 text-red-300'
                    : 'self-start bg-surface-raised text-ink'
              }`}
            >
              {message.text}
            </p>
          ))}
        </div>
      )}

      {pending ? (
        <div className="rounded-xl border border-line p-2">
          <HandoffPanel
            handoff={pending.handoff}
            fallback={null}
            error={pasteError}
            onSubmit={(answer) => void submitPasted(answer)}
            onRetry={(m) => void send(pending.request, m, false)}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_REQUEST))}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            rows={3}
            placeholder={t('aiNotes.chat.placeholder')}
            aria-label={t('aiNotes.chat.label')}
            className="resize-y rounded-xl border border-line bg-surface-raised px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          />
          <button
            type="button"
            disabled={!text.trim() || busy || chat.selected.length === 0}
            onClick={() => void send()}
            className="flex items-center justify-center gap-2 rounded-full bg-accent-gradient px-4 py-2 font-semibold text-on-accent disabled:opacity-50"
          >
            {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}
            {busy ? t('aiNotes.chat.working') : t('aiNotes.chat.send')}
          </button>
          <p className="text-xs text-muted">{t('aiNotes.chat.hint')}</p>
        </div>
      )}
    </div>
  )
}
