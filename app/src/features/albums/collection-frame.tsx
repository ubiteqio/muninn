import type { ReactNode } from 'react'

/**
 * Something that holds pictures, as a card: the cover inset in a frame, the name inside it.
 *
 * An album, a month, a year and a photograph all looked the same - a square with a rounded
 * corner and a badge - and only the line of text underneath told them apart, which a search
 * result does not have. Framing makes them different things rather than different sizes: a
 * photograph is an image, edge to edge, and everything framed is an object that holds images.
 *
 * The name belongs inside the frame for the same reason. Under the card it was a caption; in
 * the card it is what the object is called.
 *
 * The frame is a shade darker than the page, not lighter: a mat behind a photograph rather
 * than a white card laid on parchment. White drew the eye to the frame, which is the one
 * thing in it nobody came to look at.
 */
export function CollectionFrame({
  title,
  note,
  children,
}: {
  title: string
  /** The line under the name: how many pictures, or which folder it lies in. */
  note: string
  children: ReactNode
}) {
  return (
    <div className="rounded-xl border border-hairline/10 bg-secondary/45 p-1.5 transition group-hover:border-primary/40 group-hover:bg-secondary/80">
      <div className="relative aspect-square w-full overflow-hidden rounded-lg bg-secondary/60">
        {children}
      </div>
      <p className="mt-2 truncate px-1 text-base font-semibold text-foreground">{title}</p>
      <p className="mb-1 truncate px-1 text-xs-plus text-muted-foreground">{note}</p>
    </div>
  )
}
