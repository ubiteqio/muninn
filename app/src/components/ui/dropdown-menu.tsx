import * as DropdownMenuPrimitive from '@radix-ui/react-dropdown-menu'
import * as React from 'react'

import { DialogContainer } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const DropdownMenu = DropdownMenuPrimitive.Root
const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger

const DropdownMenuContent = React.forwardRef<
  React.ComponentRef<typeof DropdownMenuPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Content>
>(({ className, sideOffset = 6, ...props }, ref) => {
  // Inside the viewer the menu belongs in its element: the gallery lies above the whole page,
  // and a menu attached to the body would open behind the picture.
  const container = React.useContext(DialogContainer)
  return (
    <DropdownMenuPrimitive.Portal container={container}>
      <DropdownMenuPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        className={cn(
          // The menu takes the focus when it opens; the item under the finger or the keys shows
          // where one is, so neither the menu nor its items draw the app-wide focus ring.
          'min-w-[180px] overflow-hidden rounded-lg border border-hairline/10 bg-card p-1 text-card-foreground shadow-xl focus-visible:ring-0 focus-visible:ring-offset-0 data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in',
          container ? 'z-[1700]' : 'z-50',
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  )
})
DropdownMenuContent.displayName = DropdownMenuPrimitive.Content.displayName

const DropdownMenuItem = React.forwardRef<
  React.ComponentRef<typeof DropdownMenuPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof DropdownMenuPrimitive.Item>
>(({ className, ...props }, ref) => (
  <DropdownMenuPrimitive.Item
    ref={ref}
    className={cn(
      'flex cursor-pointer select-none items-center gap-3 rounded-md px-3 py-2.5 text-base text-foreground outline-none transition-colors focus:bg-secondary focus-visible:ring-0 focus-visible:ring-offset-0 data-[disabled]:pointer-events-none data-[disabled]:opacity-50',
      className,
    )}
    {...props}
  />
))
DropdownMenuItem.displayName = DropdownMenuPrimitive.Item.displayName

export { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger }
