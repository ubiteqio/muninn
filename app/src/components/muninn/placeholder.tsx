import type { CSSProperties, ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { SectionHeading } from '@/components/muninn/section-heading'
import { cn } from '@/lib/utils'

/**
 * A quiet block that stands where something is still being fetched, in the shape it will have.
 * The page then keeps its layout instead of pushing content around as the answers arrive.
 * A sheen travels over it, so it reads as "on its way" rather than as empty furniture.
 */
export function Placeholder({
  className,
  style,
}: {
  className?: string | undefined
  /** For the sizes the real element carries inline, such as a thumbnail of a given edge. */
  style?: CSSProperties | undefined
}) {
  return (
    <div
      aria-hidden="true"
      className={cn('placeholder rounded-md bg-secondary/70', className)}
      style={style}
    />
  )
}

/**
 * The box the placeholders stand in: the outline of the section that is coming, so the page
 * already has its shape while the answers are on their way.
 */
export function PlaceholderBox({
  className,
  children,
}: {
  className?: string | undefined
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'rounded-xl border border-hairline/10 bg-card/60 p-3 shadow-[0_1px_2px_rgba(0,0,0,0.03)]',
        className,
      )}
    >
      {children}
    </div>
  )
}

/**
 * The shapes of something that is still being fetched, with a word for whoever cannot see them.
 *
 * Sections that already stand on the page - the start screen, an album - put this in place of
 * their content and set aria-busy on themselves. A section that does not exist yet uses
 * LoadingSection below, which brings its own heading.
 */
export function LoadingBody({
  className,
  boxed = true,
  label,
  children,
}: {
  className?: string | undefined
  /** Off where the shapes are the layout themselves: a row of pictures needs no frame. */
  boxed?: boolean
  /** A word of its own where "Wird geladen" is not what is happening: a search is searching. */
  label?: string | undefined
  children: ReactNode
}) {
  const { t } = useTranslation()

  return (
    <>
      <span className="sr-only">{label ?? t('common.loading')}</span>
      {boxed ? (
        <PlaceholderBox className={className}>{children}</PlaceholderBox>
      ) : (
        <div className={className}>{children}</div>
      )}
    </>
  )
}

/**
 * A whole section on its way: the heading it will carry and the shapes of what is coming, so
 * that every screen waits in the same way and nothing below it moves when the answer lands.
 */
export function LoadingSection({
  title,
  className,
  headingClassName,
  boxed = true,
  boxClassName,
  children,
}: {
  /** Names the section for a screen reader, and stands as its heading. */
  title: string
  className?: string | undefined
  headingClassName?: string | undefined
  boxed?: boolean
  boxClassName?: string | undefined
  children: ReactNode
}) {
  return (
    <section aria-busy="true" aria-label={title} className={className}>
      <SectionHeading title={title} className={headingClassName} />
      <LoadingBody boxed={boxed} className={cn('mt-3', boxClassName)}>
        {children}
      </LoadingBody>
    </section>
  )
}
