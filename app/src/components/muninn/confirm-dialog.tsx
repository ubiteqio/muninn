import { type ReactNode, useState } from 'react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'

interface ConfirmDialogProps {
  /** The button that opens the question. It only ever opens the dialog, never acts. */
  trigger: ReactNode
  title: string
  description: string
  confirmLabel: string
  cancelLabel: string
  closeLabel: string
  /** Paints the confirming button in Runenrot. For everything that removes something. */
  destructive?: boolean
  pending?: boolean
  onConfirm: () => void | Promise<void>
}

/**
 * Asks before something cannot be taken back. The question is a dialog rather than a second
 * button in the page: the page keeps its shape, and an accidental click lands on nothing that
 * acts. The caller reports what went wrong - the dialog closes as soon as the action returns.
 */
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel,
  cancelLabel,
  closeLabel,
  destructive = false,
  pending = false,
  onConfirm,
}: ConfirmDialogProps) {
  const [open, setOpen] = useState(false)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>

      <DialogContent closeLabel={closeLabel}>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>

        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setOpen(false)
            }}
          >
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? 'destructive' : 'default'}
            disabled={pending}
            onClick={() => {
              void (async () => {
                await onConfirm()
                setOpen(false)
              })()
            }}
          >
            {confirmLabel}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
