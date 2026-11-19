import { describe, expect, it } from 'vitest'

import { isPastedPrompt } from './HandoffPanel'

const PROMPT =
  'Sei un copywriter esperto di social media. Scrivi bozze di post pronte da pubblicare a mano, basate solo sulle fonti fornite.\n\nRegole generali: ...'

describe('isPastedPrompt', () => {
  it('spots the prompt pasted back instead of the answer', () => {
    expect(isPastedPrompt(PROMPT, PROMPT)).toBe(true)
    expect(isPastedPrompt(`  ${PROMPT.replace(/\n/g, '\n\n')}  `, PROMPT)).toBe(true)
  })
  it('accepts a real answer', () => {
    expect(isPastedPrompt('{"posts": [{"platform": "instagram", "text": "Ciao"}]}', PROMPT)).toBe(false)
    expect(isPastedPrompt('anything', 'short')).toBe(false)
  })
})
