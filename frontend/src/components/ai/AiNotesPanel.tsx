import { GripHorizontal, NotebookPen, X } from 'lucide-react'
import { type PointerEvent as ReactPointerEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { useSettings, useUpdateSettings } from '../../api/hooks'
import { AI_MODES, type AiMode } from '../../api/types'
import { Toggle } from '../Toggle'
import { MAX_NOTES, notesActive, updateAiNotes, useAiNotes } from './aiNotes'

const WIDTH = 380
const MARGIN = 16
const VISIBLE = 64 // the header always stays reachable when dragged near an edge

function clamp(x: number, y: number) {
  return {
    x: Math.min(Math.max(x, VISIBLE - WIDTH), window.innerWidth - VISIBLE),
    y: Math.min(Math.max(y, 0), window.innerHeight - 48),
  }
}

/**
 * Floating, draggable box with extra instructions for the AI. While switched on, its text is
 * added to every AI request (posts, references, long content, video analysis, questions),
 * whichever AI is selected, "Open in chat" included.
 */
export function AiNotesPanel() {
  const { t } = useTranslation()
  const notes = useAiNotes()
  const { data: settings } = useSettings()
  const update = useUpdateSettings()
  const panel = useRef<HTMLDivElement>(null)
  const drag = useRef<{ dx: number; dy: number } | null>(null)
  const [, forceLayout] = useState(0)

  // Keep the box on screen when the window gets smaller.
  useEffect(() => {
    const onResize = () => {
      if (notes.position) updateAiNotes({ position: clamp(notes.position.x, notes.position.y) })
      else forceLayout((n) => n + 1)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [notes.position])

  if (!notes.open) return null

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest('button')) return
    const box = panel.current?.getBoundingClientRect()
    if (!box) return
    drag.current = { dx: event.clientX - box.left, dy: event.clientY - box.top }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const moveDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag.current) return
    updateAiNotes({ position: clamp(event.clientX - drag.current.dx, event.clientY - drag.current.dy) })
  }
  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    drag.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
  }

  const place = notes.position
    ? { left: notes.position.x, top: notes.position.y }
    : { right: MARGIN + 8, bottom: MARGIN + 8 }
  const active = notesActive(notes)

  return (
    <div
      ref={panel}
      role="dialog"
      aria-label={t('aiNotes.title')}
      style={{ ...place, width: WIDTH }}
      className="fixed z-50 flex max-h-[80vh] flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl"
    >
      <div
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        title={t('aiNotes.drag')}
        className="flex cursor-grab touch-none items-center gap-2 border-b border-line bg-surface-raised px-4 py-2.5 select-none active:cursor-grabbing"
      >
        <GripHorizontal className="size-4 text-muted" aria-hidden />
        <NotebookPen className="size-4 text-accent" aria-hidden />
        <span className="flex-1 font-semibold text-ink">{t('aiNotes.title')}</span>
        <button
          type="button"
          onClick={() => updateAiNotes({ open: false })}
          aria-label={t('aiNotes.close')}
          title={t('aiNotes.close')}
          className="grid size-7 place-items-center rounded-full text-muted hover:bg-surface hover:text-ink"
        >
          <X className="size-4" aria-hidden />
        </button>
      </div>

      <div className="flex flex-col gap-3 overflow-y-auto p-4">
        <label className="flex items-center justify-between gap-3 text-sm">
          <span className="text-muted">{t('aiNotes.sentTo')}</span>
          <select
            value={settings?.default_ai ?? 'chat'}
            onChange={(event) => update.mutate({ default_ai: event.target.value as AiMode })}
            className="min-w-0 rounded-lg border border-line bg-surface-raised px-2 py-1 font-semibold text-ink outline-none focus:border-accent"
          >
            {AI_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {t(`ai.${mode}`)}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-ink">{t('aiNotes.enabled')}</span>
          <Toggle checked={notes.enabled} onChange={(enabled) => updateAiNotes({ enabled })} label={t('aiNotes.enabled')} />
        </div>

        <textarea
          value={notes.text}
          onChange={(event) => updateAiNotes({ text: event.target.value })}
          maxLength={MAX_NOTES}
          rows={8}
          autoFocus={!notes.text}
          placeholder={t('aiNotes.placeholder')}
          aria-label={t('aiNotes.title')}
          className="min-h-32 resize-y rounded-xl border border-line bg-surface-raised px-3 py-2 text-sm text-ink outline-none focus:border-accent"
        />

        <div className="flex items-center justify-between gap-3 text-xs">
          <span className={active ? 'font-medium text-emerald-400' : 'text-muted'} role="status">
            {active ? t('aiNotes.statusOn') : notes.text.trim() ? t('aiNotes.statusPaused') : t('aiNotes.statusEmpty')}
          </span>
          <span className="flex items-center gap-3 text-muted">
            {notes.text.length}/{MAX_NOTES}
            {notes.text && (
              <button type="button" onClick={() => updateAiNotes({ text: '' })} className="font-medium text-accent hover:underline">
                {t('aiNotes.clear')}
              </button>
            )}
          </span>
        </div>
        <p className="text-xs text-muted">{t('aiNotes.help')}</p>
      </div>
    </div>
  )
}

/** Round button in the top bar that shows or hides the box; a dot marks active notes. */
export function AiNotesButton() {
  const { t } = useTranslation()
  const notes = useAiNotes()
  const active = notesActive(notes)
  return (
    <button
      type="button"
      onClick={() => updateAiNotes({ open: !notes.open })}
      aria-pressed={notes.open}
      aria-label={t('aiNotes.button')}
      title={active ? t('aiNotes.buttonActive') : t('aiNotes.button')}
      className={`relative grid size-11 place-items-center rounded-full border shadow-card hover:bg-surface-raised ${
        notes.open ? 'border-accent bg-surface-raised text-accent' : 'border-line bg-surface text-ink'
      }`}
    >
      <NotebookPen className="size-5" aria-hidden />
      {active && <span className="absolute top-1.5 right-1.5 size-2.5 rounded-full bg-emerald-400 ring-2 ring-surface" aria-hidden />}
    </button>
  )
}

/** Line next to a "Generate" button: shows whether extra instructions will be used. */
export function AiNotesHint() {
  const { t } = useTranslation()
  const notes = useAiNotes()
  const active = notesActive(notes)
  return (
    <button
      type="button"
      onClick={() => updateAiNotes({ open: true })}
      className={`flex items-center gap-1.5 text-sm hover:underline ${active ? 'text-emerald-400' : 'text-muted'}`}
    >
      <NotebookPen className="size-4" aria-hidden />
      {active ? t('aiNotes.hintActive') : t('aiNotes.hintAdd')}
    </button>
  )
}
