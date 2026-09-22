import { useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'

/**
 * The page title, for the widths where the shell has no header to put it in.
 *
 * From 768 px the shell carries the title as the page's only h1, next to a header that shows no
 * headline at all, so repeating it here would give the page two first-level headings.
 */
export function PageHeading({ title, description }: { title: string; description?: string }) {
  const isWide = useMediaQuery(WIDE_QUERY)

  if (isWide) {
    return description ? <p className="text-base text-muted-foreground">{description}</p> : null
  }

  return (
    <div>
      <h1 className="text-title font-semibold text-foreground">{title}</h1>
      {description && <p className="mt-1 text-base text-muted-foreground">{description}</p>}
    </div>
  )
}
