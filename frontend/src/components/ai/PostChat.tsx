import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Send } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aiPost, useDrafts, useSettings } from '../../api/hooks'
import type { AiMode, Draft } from '../../api/types'
import { useErrorMessage } from '../useErrorMessage'
import { HandoffPanel } from './HandoffPanel'
import {
  addChatMessage,
  draftTitle,
  effectiveChatDraft,
  getPostChat,
  orderChatDrafts,
  selectChatDraft,
  setChatBusy,
  setChatPending,
  usePostChat,
} from './postChatStore'

const MAX_REQUEST = 1500

/** Posts the chat can work on and the one currently chosen. */
export function useChatDrafts() {
  const chat = usePostChat()
  const { data: recent } = useDrafts(30)
  const options = orderChatDrafts(chat.batch, recent ?? [])
  return { options, current: effectiveChatDraft(options, chat.selectedId) }
}

function scrollToDraft(id: number) {
  // The card re-renders with the new text first; then it is brought into view and flashed.
  window.setTimeout(() => {
    const card = document.getElementById(`draft-${id}`)
    if (!card) return
    card.scrollIntoView({ behavior: 'smooth', block: 'center' })
    card.classList.add('ring-2', 'ring-accent')
    window.setTimeout(() => card.classList.remove('ring-2', 'ring-accent'), 2000)
  }, 400)
}

/** Rewrites the chosen post with a request; shared by the chat and the fixed instructions. */
export function useReviseDraft() {
  const { t } = useTranslation()
  const { data: settings } = useSettings()
  const queryClient = useQueryClient()
  const errorMessage = useErrorMessage()

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['drafts'] }),
      queryClient.invalidateQueries({ queryKey: ['generation'] }),
    ])
  }

  const revise = async (draft: Draft | null, request: string, mode?: AiMode, echo = true) => {
    request = request.trim()
    if (!draft || !request || getPostChat().busy) return false
    if (echo) addChatMessage({ role: 'user', text: request })
    setChatPending(null)
    setChatBusy(true)
    try {
      const envelope = await aiPost<never>(`/drafts/${draft.id}/revise`, {
        request,
        mode: mode ?? settings?.default_ai ?? 'chat',
      })
      if (envelope.handoff) {
        setChatPending({ draftId: draft.id, handoff: envelope.handoff, request })
        addChatMessage({ role: 'app', text: t('aiNotes.chat.handoff') })
        return true
      }
      await refresh()
      addChatMessage({ role: 'app', text: t('aiNotes.chat.done', { title: draftTitle(draft, 40) }) })
      scrollToDraft(draft.id)
      return true
    } catch (err) {
      addChatMessage({ role: 'app', text: errorMessage(err), error: true })
      return false
    } finally {
      setChatBusy(false)
    }
  }

  const submitPasted = async (answer: string) => {
    const pending = getPostChat().pending
    if (!pending) return
    await aiPost<never>(`/drafts/${pending.draftId}/revise/parse`, { text: answer })
    await refresh()
    setChatPending(null)
    addChatMessage({ role: 'app', text: t('aiNotes.chat.doneShort') })
    scrollToDraft(pending.draftId)
  }

  return { revise, submitPasted }
}

function when(iso: string) {
  const date = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

/** Dropdown "Post to edit": the posts of the last generation first, then the recent ones. */
export function PostPicker({ options, current }: { options: Draft[]; current: Draft | null }) {
  const { t } = useTranslation()
  if (!options.length) {
    return <p className="rounded-xl bg-surface-raised p-3 text-sm text-muted">{t('aiNotes.chat.empty')}</p>
  }
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted">{t('aiNotes.chat.targets')}</span>
      <select
        value={current?.id ?? ''}
        onChange={(event) => selectChatDraft(Number(event.target.value))}
        className="w-full min-w-0 rounded-lg border border-line bg-surface-raised px-2 py-1.5 text-sm text-ink outline-none focus:border-accent"
      >
        {options.map((draft) => (
          <option key={draft.id} value={draft.id}>
            {t(`platforms.${draft.platform}`)} · {draft.language.toUpperCase()} — {draftTitle(draft, 48) || `#${draft.id}`} · {when(draft.created_at)}
          </option>
        ))}
      </select>
    </label>
  )
}

/**
 * Chat on the post: the author picks a post, writes a correction and presses Send; the post
 * is rewritten in place (the old text is replaced) by the selected AI.
 */
export function PostChat() {
  const { t } = useTranslation()
  const chat = usePostChat()
  const { options, current } = useChatDrafts()
  const { revise, submitPasted } = useReviseDraft()
  const [text, setText] = useState('')
  const [pasteError, setPasteError] = useState<unknown>(null)
  const log = useRef<HTMLDivElement>(null)

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight })
  }, [chat.messages.length])

  const send = async () => {
    const request = text.trim()
    if (!request || !current) return
    setText('')
    const ok = await revise(current, request)
    if (!ok) setText(request)
  }

  const pending = chat.pending
  const pendingDraft = pending ? options.find((d) => d.id === pending.draftId) ?? current : null

  return (
    <div className="flex flex-col gap-3">
      <PostPicker options={options} current={current} />

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

      {pending && (
        <div className="rounded-xl border border-line p-2">
          <HandoffPanel
            handoff={pending.handoff}
            fallback={null}
            error={pasteError}
            onSubmit={(answer) => {
              setPasteError(null)
              submitPasted(answer).catch(setPasteError)
            }}
            onRetry={(m) => void revise(pendingDraft, pending.request, m, false)}
          />
        </div>
      )}

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
          disabled={!text.trim() || chat.busy || !current}
          onClick={() => void send()}
          className="flex items-center justify-center gap-2 rounded-full bg-accent-gradient px-4 py-2 font-semibold text-on-accent disabled:opacity-50"
        >
          {chat.busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Send className="size-4" aria-hidden />}
          {chat.busy ? t('aiNotes.chat.working') : t('aiNotes.chat.send')}
        </button>
        <p className="text-xs text-muted">{t('aiNotes.chat.hint')}</p>
      </div>
    </div>
  )
}
