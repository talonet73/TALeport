import { useSyncExternalStore } from 'react'

import type { Draft, Language, Platform } from '../../api/types'

/**
 * "Chat on the post" in the floating box: the drafts of the last generation shown on screen
 * are the ones the chat corrects, and the conversation is kept while the app is open.
 */
export interface ChatTarget {
  id: number
  platform: Platform
  language: Language
  label: string
}

export interface ChatMessage {
  role: 'user' | 'app'
  text: string
  error?: boolean
}

interface State {
  targets: ChatTarget[]
  selected: number[]
  messages: ChatMessage[]
}

let state: State = { targets: [], selected: [], messages: [] }
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

/** Called by the generation results: a new batch becomes the subject of the chat. */
export function setChatDrafts(drafts: Draft[]) {
  const ids = drafts.map((d) => d.id)
  const same = ids.length === state.targets.length && ids.every((id, i) => id === state.targets[i]?.id)
  if (same) return
  emit({
    targets: drafts.map((d) => ({
      id: d.id,
      platform: d.platform,
      language: d.language,
      label: d.content.hook || d.content.title || d.text.slice(0, 60),
    })),
    selected: ids,
    messages: [],
  })
}

export function toggleChatTarget(id: number) {
  const selected = state.selected.includes(id) ? state.selected.filter((x) => x !== id) : [...state.selected, id]
  emit({ selected })
}

export function addChatMessage(message: ChatMessage) {
  emit({ messages: [...state.messages, message].slice(-30) })
}
