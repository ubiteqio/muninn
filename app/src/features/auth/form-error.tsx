import { Symbol } from '@/components/muninn/symbol'

/** Failures are shown in Runenrot, next to the form rather than in a dialog. */
export function FormError({ message }: { message: string | null }) {
  if (!message) return null

  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/[0.12] px-3 py-2 text-base text-foreground"
    >
      <Symbol name="error" size={18} className="mt-px shrink-0 text-destructive" />
      {message}
    </p>
  )
}
