import { useSyncExternalStore } from 'react'

/**
 * Floating "AI notes" box: extra instructions added to every AI request while switched on.
 * Kept in the window's storage (text, on/off, open, position); the API client sends the text
 * with each request in the `X-TALeport-Extra` header, so the backend adds it to the prompt.
 */
export const MAX_NOTES = 1500
export const NOTES_HEADER = 'X-TALeport-Extra'
const STORAGE_KEY = 'taleport.aiNotes'

export interface AiNotesState {
  open: boolean
  enabled: boolean
  text: string
  position: { x: number; y: number } | null // null = bottom-right corner
  tab: 'chat' | 'notes'
}

const DEFAULT: AiNotesState = { open: false, enabled: true, text: '', position: null, tab: 'chat' }

function load(): AiNotesState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT
    const saved = JSON.parse(raw) as Partial<AiNotesState>
    return {
      open: saved.open === true,
      enabled: saved.enabled !== false,
      text: typeof saved.text === 'string' ? saved.text.slice(0, MAX_NOTES) : '',
      position:
        saved.position && Number.isFinite(saved.position.x) && Number.isFinite(saved.position.y)
          ? { x: saved.position.x, y: saved.position.y }
          : null,
      tab: saved.tab === 'notes' ? 'notes' : 'chat',
    }
  } catch {
    return DEFAULT
  }
}

let state: AiNotesState = load()
const listeners = new Set<() => void>()

export function updateAiNotes(change: Partial<AiNotesState>) {
  state = { ...state, ...change }
  if (change.text !== undefined) state.text = state.text.slice(0, MAX_NOTES)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // storage unavailable: the box still works for this session
  }
  listeners.forEach((listener) => listener())
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useAiNotes(): AiNotesState {
  return useSyncExternalStore(subscribe, () => state)
}

export function notesActive(notes: AiNotesState = state): boolean {
  return notes.enabled && notes.text.trim().length > 0
}

/** Headers for an API request: the notes, URL-encoded, when the box is switched on. */
export function aiNotesHeaders(): Record<string, string> {
  return notesActive() ? { [NOTES_HEADER]: encodeURIComponent(state.text.trim()) } : {}
}
