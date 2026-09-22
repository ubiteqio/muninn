import { describe, expect, it } from 'vitest'

import { cn } from '@/lib/utils'

describe('cn', () => {
  it('keeps our own text sizes beside a colour', () => {
    expect(cn('text-xs-plus', 'text-muted-foreground')).toBe('text-xs-plus text-muted-foreground')
    expect(cn('text-3xs text-foreground')).toBe('text-3xs text-foreground')
  })

  it('still lets a later size win over an earlier one', () => {
    expect(cn('text-xs-plus', 'text-title')).toBe('text-title')
  })
})
