import { describe, expect, it } from 'vitest'

import type { Draft } from '../../api/types'
import { draftTitle, effectiveChatDraft, orderChatDrafts } from './postChatStore'

const d = (id: number, hook = '', text = 'testo del post'): Draft =>
  ({ id, content: { hook }, text, platform: 'instagram', language: 'it' }) as unknown as Draft

describe('post chat', () => {
  it('puts the last generation first, then the other recent drafts', () => {
    const recent = [d(5), d(4), d(3), d(2)]
    expect(orderChatDrafts([3, 4], recent).map((x) => x.id)).toEqual([3, 4, 5, 2])
  })

  it('works without a current generation (after a restart)', () => {
    const options = orderChatDrafts([], [d(9), d(8)])
    expect(effectiveChatDraft(options, null)?.id).toBe(9)
    expect(effectiveChatDraft(options, 8)?.id).toBe(8)
    expect(effectiveChatDraft(options, 42)?.id).toBe(9)
    expect(effectiveChatDraft([], null)).toBeNull()
  })

  it('titles a post by hook, else by its first characters', () => {
    expect(draftTitle(d(1, 'Forza Roma'))).toBe('Forza Roma')
    expect(draftTitle(d(1, '', 'a'.repeat(80)), 20)).toHaveLength(20)
  })
})
