import { type ComponentProps, type ReactNode, useId } from 'react'

import { Input } from '@/components/ui/input'

/** A labelled input. Labels are always visible: a placeholder alone is not a label. */
export function Field({
  label,
  hint,
  info,
  ...props
}: {
  label: string
  hint?: string
  /** Room beside the label for the longer story, usually an {@link InfoHint}. */
  info?: ReactNode | undefined
} & ComponentProps<typeof Input>) {
  const id = useId()
  const hintId = `${id}-hint`

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-1">
        <label htmlFor={id} className="block text-sm font-medium text-muted-foreground">
          {label}
        </label>
        {info}
      </div>
      <Input id={id} aria-describedby={hint ? hintId : undefined} {...props} />
      {hint && (
        <p id={hintId} className="text-xs-plus text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}
