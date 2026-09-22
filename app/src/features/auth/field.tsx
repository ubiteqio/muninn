import { type ComponentProps, useId } from 'react'

import { Input } from '@/components/ui/input'

/** A labelled input. Labels are always visible: a placeholder alone is not a label. */
export function Field({
  label,
  hint,
  ...props
}: { label: string; hint?: string } & ComponentProps<typeof Input>) {
  const id = useId()
  const hintId = `${id}-hint`

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-muted-foreground">
        {label}
      </label>
      <Input id={id} aria-describedby={hint ? hintId : undefined} {...props} />
      {hint && (
        <p id={hintId} className="text-xs-plus text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}
