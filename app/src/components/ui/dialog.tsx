import * as DialogPrimitive from '@radix-ui/react-dialog'
import * as React from 'react'

import { Symbol } from '@/components/muninn/symbol'
import { cn } from '@/lib/utils'

const Dialog = DialogPrimitive.Root
const DialogTrigger = DialogPrimitive.Trigger
const DialogClose = DialogPrimitive.Close

/**
 * Where dialogs open. By default at the end of the page; inside the full screen viewer, in the
 * viewer itself: it lies above everything else and pulls the focus back into itself, so a dialog
 * outside it could be neither seen nor typed in.
 */
const DialogContainer = React.createContext<HTMLElement | null>(null)

const DialogContent = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { closeLabel: string }
>(({ className, children, closeLabel, ...props }, ref) => {
  const container = React.useContext(DialogContainer)
  // In the viewer: above its info panel (z 1600) and the buttons beside it.
  const layer = container ? 'z-[1700]' : 'z-50'
  return (
    <DialogPrimitive.Portal container={container}>
      <DialogPrimitive.Overlay
        className={cn(
          'fixed inset-0 bg-background/80 backdrop-blur-chip data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in',
          layer,
        )}
      />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          'fixed left-1/2 top-1/2 w-[calc(100vw-40px)] max-w-[440px] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-hairline/[0.07] bg-card p-6',
          'data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in',
          layer,
          className,
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close
          className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-md text-muted-foreground transition hover:bg-secondary hover:text-foreground"
          aria-label={closeLabel}
        >
          <Symbol name="close" size={20} />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
})
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogTitle = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn('text-lg font-semibold text-foreground', className)}
    {...props}
  />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef<
  React.ComponentRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn('mt-1.5 text-base text-muted-foreground', className)}
    {...props}
  />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export {
  Dialog,
  DialogClose,
  DialogContainer,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
}
