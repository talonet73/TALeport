import { useQueryClient } from '@tanstack/react-query'
import { Loader2, Send, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { aiPost, useSettings } from '../../api/hooks'
import { HandoffPanel } from '../ai/HandoffPanel'
import { useAiFlow } from '../ai/useAiFlow'
import { useErrorMessage } from '../useErrorMessage'

const QUICK = ['shorter', 'longer', 'ironic', 'question', 'emoji', 'noHashtags'] as const
const MAX_REQUEST = 1500

/**
 * "Edit with AI" on one draft: the author writes what to change (or picks a quick request),
 * the selected AI rewrites that post in place. Works with "Open in chat" too.
 */
export function ReviseBox({ draftId, onClose }: { draftId: number; onClose: () => void }) {
  const { t } = useTranslation()
  const { data: settings } = useSettings()
  const queryClient = useQueryClient()
  const errorMessage = useErrorMessage()
  const [request, setRequest] = useState('')
  const [done, setDone] = useState(false)
  const pending = useRef('') // the request being sent (state would lag one render behind)

  const flow = useAiFlow<never>({
    start: (m) => aiPost(`/drafts/${draftId}/revise`, { request: pending.current, mode: m }),
    parse: (text) => aiPost(`/drafts/${draftId}/revise/parse`, { text }),
    onDone: () => {
      void queryClient.invalidateQueries({ queryKey: ['drafts'] })
      void queryClient.invalidateQueries({ queryKey: ['generation'] })
      setRequest('')
      setDone(true)
      flow.reset()
    },
  })

  const send = (text = request) => {
    if (!text.trim() || flow.busy) return
    setRequest(text)
    setDone(false)
    pending.current = text.trim()
    void flow.run(settings?.default_ai ?? 'chat')
  }

  return (
    <div className="mt-3 rounded-xl border border-accent/40 bg-surface-raised p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-semibold text-ink">{t('drafts.revise.title')}</span>
        <button type="button" onClick={onClose} aria-label={t('common.close')} className="rounded-full p-1 text-muted hover:text-ink">
          <X className="size-4" aria-hidden />
        </button>
      </div>

      {flow.phase === 'handoff' && flow.handoff ? (
        <HandoffPanel
          handoff={flow.handoff}
          fallback={flow.fallback}
          error={flow.error}
          onSubmit={flow.submitPasted}
          onRetry={(m) => void flow.run(m)}
        />
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {QUICK.map((key) => (
              <button
                key={key}
                type="button"
                disabled={flow.busy}
                onClick={() => send(t(`drafts.revise.quick.${key}`))}
                className="rounded-full border border-line bg-surface px-3 py-1 text-sm text-ink hover:border-accent disabled:opacity-50"
              >
                {t(`drafts.revise.quick.${key}`)}
              </button>
            ))}
          </div>
          <div className="flex items-end gap-2">
            <textarea
              value={request}
              onChange={(e) => setRequest(e.target.value.slice(0, MAX_REQUEST))}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
              rows={2}
              placeholder={t('drafts.revise.placeholder')}
              aria-label={t('drafts.revise.title')}
              className="min-h-11 flex-1 resize-y rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
            />
            <button
              type="button"
              disabled={!request.trim() || flow.busy}
              onClick={() => send()}
              aria-label={t('drafts.revise.send')}
              title={t('drafts.revise.send')}
              className="grid size-11 place-items-center rounded-full bg-accent-gradient text-on-accent disabled:opacity-50"
            >
              {flow.busy ? <Loader2 className="size-5 animate-spin" aria-hidden /> : <Send className="size-5" aria-hidden />}
            </button>
          </div>
          <p className="mt-2 text-xs text-muted" role="status">
            {flow.busy ? t('ai.working') : done ? t('drafts.revise.done') : t('drafts.revise.hint')}
          </p>
          {flow.error !== null && <p className="mt-1 text-sm text-red-400">{errorMessage(flow.error)}</p>}
        </>
      )}
    </div>
  )
}
