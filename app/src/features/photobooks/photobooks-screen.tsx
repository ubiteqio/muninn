import { Link, useNavigate } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { PageColumn } from '@/components/layout/page-column'
import { PageHeading } from '@/components/layout/page-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Badge } from '@/components/ui/badge'
import { CollectionFrame } from '@/features/albums/collection-frame'
import { BookReader } from '@/features/photobooks/book-reader'
import {
  type Photobook,
  usePhotobook,
  usePhotobooks,
  usePhotobookUpdates,
} from '@/features/photobooks/use-photobooks'

/** How many covers stand there while the first answer is on its way. */
const LOADING_CARDS = 6

/**
 * Fotobücher: the shelf, and a book when one is open.
 *
 * A book is made in the admin area and built by a worker; what stands here is what came of it.
 * Opening one leaves the app behind entirely - the reader is the whole screen - and Escape or
 * the cross brings the shelf back.
 */
export function PhotobooksScreen({ bookId }: { bookId?: string | undefined }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const shelf = usePhotobooks()
  usePhotobookUpdates()

  if (bookId !== undefined) {
    return (
      <OpenBook
        bookId={bookId}
        onLeave={() => {
          void navigate({ to: '/photobooks' })
        }}
      />
    )
  }

  const books = shelf.data?.items ?? []

  return (
    <AppShell title={t('photobooks.title')} active="albums">
      <PageColumn className="space-y-5">
        <PageHeading title={t('photobooks.title')} description={t('photobooks.description')} />

        {shelf.isPending ? (
          <Shelf>
            {Array.from({ length: LOADING_CARDS }, (_, at) => (
              <BookCardLoading key={at} />
            ))}
          </Shelf>
        ) : books.length === 0 ? (
          <p className="rounded-xl border border-hairline/10 bg-secondary/40 px-4 py-8 text-center text-muted-foreground">
            {t('photobooks.none')}
          </p>
        ) : (
          <Shelf>
            {books.map((book) => (
              <BookCard key={book.id} book={book} />
            ))}
          </Shelf>
        )}
      </PageColumn>
    </AppShell>
  )
}

function Shelf({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {children}
    </div>
  )
}

function BookCard({ book }: { book: Photobook }) {
  const { t } = useTranslation()
  const ready = book.state === 'ready'
  const note = ready
    ? [book.subtitle, t('photobooks.pages', { count: book.pages })].filter(Boolean).join(' · ')
    : book.state === 'failed'
      ? t('photobooks.failed')
      : t('photobooks.building')

  const card = (
    <CollectionFrame title={book.title} note={note}>
      {book.cover ? (
        <img
          src={book.cover}
          alt=""
          loading="lazy"
          decoding="async"
          className="size-full object-cover"
        />
      ) : (
        <span className="flex size-full items-center justify-center text-muted-foreground">
          <Symbol name="menu_book" size={34} />
        </span>
      )}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,0,0,0.34),rgba(0,0,0,0.1)_55%,transparent_75%)] opacity-90 transition-opacity duration-200 group-hover:opacity-60"
      />
      {/* The mark of the thing: a book, centred, the way a Smart carries its kind. */}
      <span className="pointer-events-none absolute inset-0 flex items-center justify-center">
        <span className="flex size-[58px] items-center justify-center rounded-full border border-white/30 bg-black/35 text-white backdrop-blur-[2px]">
          <Symbol name="menu_book" size={28} />
        </span>
      </span>
      {ready && book.media > 0 ? (
        <Badge variant="count" className="absolute right-1.5 bottom-1.5">
          {book.media}
        </Badge>
      ) : null}
    </CollectionFrame>
  )

  if (!ready) return <div className="group block opacity-60">{card}</div>
  return (
    <Link
      to="/photobooks/$bookId"
      params={{ bookId: book.id }}
      aria-label={t('photobooks.open', { title: book.title })}
      className="group block text-left"
    >
      {card}
    </Link>
  )
}

function BookCardLoading() {
  return (
    <div className="rounded-xl border border-hairline/10 bg-secondary/45 p-1.5">
      <div className="aspect-square w-full animate-pulse rounded-lg bg-secondary/60" />
      <div className="mt-2 h-4 w-2/3 animate-pulse rounded bg-secondary/60" />
      <div className="mt-1.5 mb-1 h-3 w-1/2 animate-pulse rounded bg-secondary/40" />
    </div>
  )
}

function OpenBook({ bookId, onLeave }: { bookId: string; onLeave: () => void }) {
  const { t } = useTranslation()
  const book = usePhotobook(bookId)

  if (book.isPending) {
    return (
      <div className="flex h-dvh items-center justify-center bg-[#1b1a17] text-[#e8e0cf]">
        {t('common.loading')}
      </div>
    )
  }
  if (book.isError || book.data.leaves.length === 0) {
    return (
      <div className="flex h-dvh flex-col items-center justify-center gap-4 bg-[#1b1a17] text-[#e8e0cf]">
        <p>{t('photobooks.notReadable')}</p>
        <button type="button" onClick={onLeave} className="underline">
          {t('photobooks.close')}
        </button>
      </div>
    )
  }

  return (
    <BookReader
      pages={book.data.leaves}
      title={book.data.title}
      onLeave={onLeave}
    />
  )
}
