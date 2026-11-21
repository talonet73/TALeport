import { useSyncExternalStore } from 'react'

import type { Draft, Handoff } from '../../api/types'

/**
 * "Chat on the post" in the floating box. The author picks ONE post from a dropdown (the
 * posts of the last generation first, then the recent drafts) and the chat rewrites it.
 * The conversation is kept while the app is open.
 */
export interface ChatMessage {
  role: 'user' | 'app'
  text: string
  error?: boolean
}

export interface ChatPending {
  draftId: number
  handoff: Handoff
  request: string
}

interface State {
  /** Ids of the last generation shown on screen, in display order. */
  batch: number[]
  /** Post chosen in the dropdown (null: the first available one). */
  selectedId: number | null
  messages: ChatMessage[]
  pending: ChatPending | null
  busy: boolean
}

let state: State = { batch: [], selectedId: null, messages: [], pending: null, busy: false }
const listeners = new Set<() => void>()

function emit(next: Partial<State>) {
  state = { ...state, ...next }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function usePostChat(): State {
  return useSyncExternalStore(subscribe, () => state)
}

export function getPostChat(): State {
  return state
}

/** Called by the generation results: a new batch goes on top and its first post is selected. */
export function setChatDrafts(drafts: Draft[]) {
  const ids = drafts.map((d) => d.id)
  const same = ids.length === state.batch.length && ids.every((id, i) => id === state.batch[i])
  if (same) return
  emit({ batch: ids, selectedId: ids[0] ?? state.selectedId, pending: null })
}

export function selectChatDraft(id: number) {
  emit({ selectedId: id, pending: state.pending?.draftId === id ? state.pending : null })
}

export function setChatPending(pending: ChatPending | null) {
  emit({ pending })
}

export function setChatBusy(busy: boolean) {
  emit({ busy })
}

export function addChatMessage(message: ChatMessage) {
  emit({ messages: [...state.messages, message].slice(-30) })
}

/** Short title used in the dropdown: hook, title or the first characters of the text. */
export function draftTitle(draft: Pick<Draft, 'content' | 'text'>, max = 60): string {
  const raw = (draft.content?.hook || draft.content?.title || draft.text || '').replace(/\s+/g, ' ').trim()
  return raw.length > max ? `${raw.slice(0, max - 1)}…` : raw
}

/** Batch posts first (in their order), then the other recent drafts, without duplicates. */
export function orderChatDrafts(batch: number[], recent: Draft[], batchDrafts: Draft[] = []): Draft[] {
  const byId = new Map<number, Draft>()
  for (const d of [...batchDrafts, ...recent]) if (!byId.has(d.id)) byId.set(d.id, d)
  const first = batch.map((id) => byId.get(id)).filter((d): d is Draft => !!d)
  const rest = recent.filter((d) => !batch.includes(d.id))
  return [...first, ...rest]
}

/** The post the chat works on: the chosen one if still available, else the first. */
export function effectiveChatDraft(options: Draft[], selectedId: number | null): Draft | null {
  return options.find((d) => d.id === selectedId) ?? options[0] ?? null
}
