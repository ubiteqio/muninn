import * as PopoverPrimitive from '@radix-ui/react-popover'
import * as React from 'react'

import { DialogContainer } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

const Popover = PopoverPrimitive.Root
const PopoverTrigger = PopoverPrimitive.Trigger

const PopoverContent = React.forwardRef<
  React.ComponentRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = 'start', sideOffset = 8, ...props }, ref) => {
  // The same rule as the menu: inside the viewer a bubble on the body would open behind the
  // picture, so it goes into the element the viewer hands down.
  const container = React.useContext(DialogContainer)
  return (
    <PopoverPrimitive.Portal container={container}>
      <PopoverPrimitive.Content
        ref={ref}
        align={align}
        sideOffset={sideOffset}
        collisionPadding={12}
        className={cn(
          'w-[min(340px,calc(100vw-24px))] rounded-lg border border-hairline/10 bg-card p-3.5 text-base leading-relaxed text-card-foreground shadow-xl outline-none data-[state=closed]:animate-fade-out data-[state=open]:animate-fade-in',
          container ? 'z-[1700]' : 'z-50',
          className,
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  )
})
PopoverContent.displayName = PopoverPrimitive.Content.displayName

export { Popover, PopoverContent, PopoverTrigger }
