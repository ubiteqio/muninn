import { type ComponentProps, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { AdminArea } from '@/features/admin/admin-area'
import { AlbumPicker } from '@/features/admin/album-picker'
import { Field } from '@/features/auth/field'
import {
  type Photobook,
  useMakePhotobooks,
  usePhotobooks,
  usePhotobookUpdates,
  usePublishedAlbums,
  useRebuildPhotobook,
  useRemovePhotobook,
} from '@/features/photobooks/use-photobooks'

const SIZES = ['small', 'medium', 'large'] as const

/**
 * Fotobücher in the admin area: making them, and taking them off the shelf.
 *
 * An album becomes a book here and nowhere else. The two numbers decide how big it is - a share
 * of the album, and a ceiling above it - because a folder of 4500 holidays would otherwise make
 * a book nobody finishes. The building itself happens in the worker, so this page hands over
 * and the shelf fills by itself a few minutes later.
 */
export function PhotobooksPage() {
  const { t } = useTranslation()
  const albums = usePublishedAlbums()
  const shelf = usePhotobooks()
  const make = useMakePhotobooks()
  usePhotobookUpdates()

  const [chosen, setChosen] = useState<string[]>([])
  const [size, setSize] = useState<(typeof SIZES)[number]>('medium')
  const [maxMedia, setMaxMedia] = useState('150')
  const [count, setCount] = useState('1')
  const [title, setTitle] = useState('')

  const books = shelf.data?.items ?? []

  return (
    <AdminArea section="photobooks">
      <div className="space-y-5">
        <Card className="p-5">
          <h2 className="text-lg font-semibold text-foreground">{t('admin.photobooks.title')}</h2>
          <p className="mt-1.5 text-base text-muted-foreground">
            {t('admin.photobooks.description')}
          </p>

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <span className="text-xs-plus font-medium">{t('admin.photobooks.album')}</span>
              <div className="mt-1.5">
                <AlbumPicker chosen={chosen} onChange={setChosen} />
              </div>
              <Chosen
                chosen={chosen}
                onChange={setChosen}
                albums={albums.data ?? []}
              />
              <span className="mt-1 block text-2xs text-muted-foreground">
                {t('admin.photobooks.albumHint')}
              </span>
            </div>

            <Choice
              label={t('admin.photobooks.size')}
              hint={t('admin.photobooks.sizeHint')}
              value={size}
              onChange={(event) => {
                setSize(event.target.value as (typeof SIZES)[number])
              }}
            >
              {SIZES.map((one) => (
                <option key={one} value={one}>
                  {t(`admin.photobooks.${one}`)}
                </option>
              ))}
            </Choice>

            <Field
              label={t('admin.photobooks.maxMedia')}
              hint={t('admin.photobooks.maxMediaHint')}
              type="number"
              inputMode="numeric"
              min={4}
              max={400}
              value={maxMedia}
              onChange={(event) => {
                setMaxMedia(event.target.value)
              }}
            />

            <Field
              label={t('admin.photobooks.count')}
              hint={t('admin.photobooks.countHint')}
              type="number"
              inputMode="numeric"
              min={1}
              max={20}
              value={count}
              onChange={(event) => {
                setCount(event.target.value)
              }}
            />

            <Field
              label={t('admin.photobooks.bookTitle')}
              hint={t('admin.photobooks.titleHint')}
              value={title}
              onChange={(event) => {
                setTitle(event.target.value)
              }}
            />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Button
              type="button"
              disabled={chosen.length === 0 || make.isPending}
              onClick={() => {
                make.mutate({
                  album_ids: chosen,
                  size,
                  style: 'scrapbook',
                  max_media: Number(maxMedia),
                  count: Number(count),
                  title,
                })
              }}
            >
              <Symbol name="menu_book" size={20} />
              {t(make.isPending ? 'admin.photobooks.making' : 'admin.photobooks.make')}
            </Button>
            {chosen.length === 0 && (
              <span className="text-xs-plus text-muted-foreground">
                {t('admin.photobooks.needsAlbum')}
              </span>
            )}
            {make.isSuccess && (
              <span className="text-xs-plus text-muted-foreground">
                {t('admin.photobooks.made', { count: make.data.items.length })}
              </span>
            )}
          </div>
        </Card>

        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-foreground">
            {t('admin.photobooks.existing')}
          </h2>
          {books.length === 0 ? (
            <Card className="p-5 text-base text-muted-foreground">
              {t('admin.photobooks.nothing')}
            </Card>
          ) : (
            books.map((book) => <BookRow key={book.id} book={book} />)
          )}
        </div>
      </div>
    </AdminArea>
  )
}

/** A labelled select, in the shape of the labelled inputs beside it. */
function Choice({
  label,
  hint,
  children,
  ...props
}: { label: string; hint?: string } & ComponentProps<'select'>) {
  const id = useId()
  const hintId = `${id}-hint`

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-muted-foreground">
        {label}
      </label>
      <select
        id={id}
        aria-describedby={hint ? hintId : undefined}
        className="h-11 w-full rounded-lg border border-hairline/10 bg-card px-3 text-md text-foreground focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-none"
        {...props}
      >
        {children}
      </select>
      {hint && (
        <p id={hintId} className="text-xs-plus text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}

function BookRow({ book }: { book: Photobook }) {
  const { t } = useTranslation()
  const remove = useRemovePhotobook()
  const rebuild = useRebuildPhotobook()

  const note =
    book.state === 'ready'
      ? [
          t('admin.photobooks.pagesAndMedia', { pages: book.pages, media: book.media }),
          book.written ? t('admin.photobooks.written') : t('admin.photobooks.plain'),
        ].join(' · ')
      : book.state === 'failed'
        ? book.trouble || t('photobooks.failed')
        : t('photobooks.building')

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {book.cover ? (
            <img src={book.cover} alt="" className="size-12 shrink-0 rounded-lg object-cover" />
          ) : (
            <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-secondary/60 text-muted-foreground">
              <Symbol name="menu_book" size={20} />
            </span>
          )}
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-base font-semibold text-foreground">
              {book.title}
              {book.state !== 'ready' && (
                <span className="rounded-badge bg-primary/[0.14] px-1.5 py-0.5 text-3xs font-medium tracking-section uppercase text-primary">
                  {t(book.state === 'failed' ? 'photobooks.failed' : 'photobooks.building')}
                </span>
              )}
            </p>
            <p className="mt-0.5 truncate text-xs-plus text-muted-foreground">
              {book.album}
              {book.subtitle ? ` · ${book.subtitle}` : ''}
            </p>
            <p className="mt-0.5 text-xs-plus text-muted-foreground">{note}</p>
          </div>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            className="h-8 px-2 text-xs-plus"
            disabled={rebuild.isPending}
            onClick={() => {
              rebuild.mutate(book.id)
            }}
          >
            <Symbol name="sync" size={16} />
            {t('admin.photobooks.rebuild')}
          </Button>
          <ConfirmDialog
            trigger={
              <Button
                variant="outline"
                aria-label={t('admin.photobooks.remove')}
                className="h-8 px-2 text-xs-plus"
                disabled={remove.isPending}
              >
                <Symbol name="delete" size={16} />
              </Button>
            }
            title={t('admin.photobooks.removeTitle')}
            description={t('admin.photobooks.removeBody', { title: book.title })}
            confirmLabel={t('admin.photobooks.remove')}
            cancelLabel={t('common.cancel')}
            closeLabel={t('common.close')}
            destructive
            pending={remove.isPending}
            onConfirm={() => {
              remove.mutate(book.id)
            }}
          />
        </div>
      </div>
    </Card>
  )
}

/** The folders a book will be made of, in the order they were ticked. */
function Chosen({
  chosen,
  albums,
  onChange,
}: {
  chosen: string[]
  albums: { id: string; title: string; relative_path: string; media_count: number }[]
  onChange: (chosen: string[]) => void
}) {
  const { t } = useTranslation()
  if (chosen.length === 0) return null

  const byId = new Map(albums.map((album) => [album.id, album]))
  const picked = chosen.map((id) => byId.get(id)).filter((album) => album !== undefined)
  const pictures = picked.reduce((all, album) => all + album.media_count, 0)

  return (
    <div className="mt-2">
      <ul className="flex flex-wrap gap-1.5">
        {picked.map((album, index) => (
          <li key={album.id}>
            <button
              type="button"
              aria-label={t('admin.photobooks.unpick', { name: album.title })}
              title={album.relative_path}
              className="flex items-center gap-1.5 rounded-full border border-hairline/10 bg-secondary/50 py-1 pl-2.5 pr-1.5 text-xs-plus text-foreground transition hover:border-destructive/40"
              onClick={() => {
                onChange(chosen.filter((id) => id !== album.id))
              }}
            >
              {index === 0 && <Symbol name="star" size={13} filled className="text-primary" />}
              <span className="max-w-[180px] truncate">{album.title}</span>
              <span className="tabular-nums text-muted-foreground">{album.media_count}</span>
              <Symbol name="close" size={14} className="text-muted-foreground" />
            </button>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-2xs text-muted-foreground">
        {t('admin.photobooks.chosenCount', { count: chosen.length, pictures })}
      </p>
    </div>
  )
}
