import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  Dialog,
  DialogContainer,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'

function Open() {
  return (
    <Dialog open>
      <DialogContent closeLabel="Schließen">
        <DialogTitle>Wer ist das?</DialogTitle>
        <DialogDescription>Ein Name</DialogDescription>
      </DialogContent>
    </Dialog>
  )
}

describe('Dialog', () => {
  it('opens at the end of the page', () => {
    render(<Open />)

    expect(screen.getByRole('dialog').parentElement).toBe(document.body)
  })

  it('opens inside the full screen viewer, above its panel, when it is given one', () => {
    const viewer = document.createElement('div')
    document.body.append(viewer)

    render(
      <DialogContainer.Provider value={viewer}>
        <Open />
      </DialogContainer.Provider>,
    )

    const dialog = screen.getByRole('dialog')
    expect(viewer.contains(dialog)).toBe(true)
    expect(dialog.className).toContain('z-[1700]')
    viewer.remove()
  })
})
