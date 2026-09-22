import { Link } from '@tanstack/react-router'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import {
  type Notice,
  people,
  useMarkAllRead,
  useNoticeUpdates,
  useNotifications,
  useUnreadCount,
} from '@/features/notify/use-notifications'
import { when } from '@/features/social/when'
import { cn } from '@/lib/utils'

const ICONS: Record<string, string> = {
  reply: 'chat_bubble',
  mention: 'chat_bubble',
  comment: 'chat_bubble',
  comment_like: 'favorite',
  new_media: 'add_photo_alternate',
}

/**
 * The bell: how much is new, and a list of it one tap away. Opening it reads everything; what
 * was new keeps its mark until the list closes, so one can still see what it was. On the desktop
 * the list drops from the bell, on the phone it takes the screen below the header.
 */
export function NotificationBell({ className }: { className?: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const unread = useUnreadCount()
  const list = useNotifications(open)
  const read = useMarkAllRead()
  const box = useRef<HTMLDivElement>(null)
  useNoticeUpdates()

  const count = unread.data?.count ?? 0
  const items = useMemo(() => list.data?.pages.flatMap((page) => page.items) ?? [], [list.data])

  // Everything is read the moment the list is shown.
  useEffect(() => {
    if (open && list.isSuccess && count > 0 && !read.isPending) read.mutate()
  }, [open, list.isSuccess, count, read])

  useEffect(() => {
    if (!open) return
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', escape)
    }
  }, [open])

  return (
    <div ref={box} className={cn('md:relative', className)}>
      <button
        type="button"
        aria-label={t('header.notifications', { count })}
        aria-expanded={open}
        onClick={() => {
          setOpen(!open)
        }}
        className="relative flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground transition hover:bg-secondary hover:text-foreground"
      >
        <Symbol name="notifications" size={22} filled={open} />
        {count > 0 && (
          <span className="absolute right-1.5 top-1.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full border-2 border-background bg-primary px-1 text-3xs font-semibold text-primary-foreground">
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label={t('notify.title')}
          className="fixed inset-x-0 bottom-0 top-[60px] z-40 flex flex-col overflow-hidden border-t border-hairline/10 bg-background shadow-xl md:absolute md:inset-auto md:right-0 md:top-full md:mt-2 md:max-h-[70vh] md:w-[380px] md:rounded-xl md:border"
        >
          <div className="flex items-center justify-between border-b border-hairline/10 px-4 py-3">
            <h2 className="text-md font-semibold text-foreground">{t('notify.title')}</h2>
          </div>
          <div className="flex-1 overflow-y-auto">
            {list.isPending && (
              <p className="px-4 py-6 text-base text-muted-foreground">{t('notify.loading')}</p>
            )}
            {list.isSuccess && items.length === 0 && (
              <p className="px-4 py-10 text-center text-base text-muted-foreground">
                {t('notify.empty')}
              </p>
            )}
            <ol>
              {items.map((item) => (
                <li key={item.id}>
                  <NoticeRow
                    notice={item}
                    onOpen={() => {
                      setOpen(false)
                    }}
                  />
                </li>
              ))}
            </ol>
            {list.hasNextPage && (
              <button
                type="button"
                onClick={() => void list.fetchNextPage()}
                className="w-full py-3 text-xs-plus text-accent hover:underline"
              >
                {t('notify.more_button')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function NoticeRow({ notice, onOpen }: { notice: Notice; onOpen: () => void }) {
  const { t } = useTranslation()
  const who = people(notice.actors, notice.count, t)
  const text =
    notice.kind === 'new_media'
      ? t('notify.kind.new_media', { count: notice.count, album: notice.album?.title ?? '' })
      : t(`notify.kind.${notice.kind}`, { who, count: Math.max(notice.actors.length, 1) })

  const body = (
    <>
      <span
        className={cn(
          'mt-1.5 h-2 w-2 shrink-0 rounded-full',
          notice.read ? 'bg-transparent' : 'bg-primary',
        )}
      />
      <Symbol
        name={ICONS[notice.kind] ?? 'notifications'}
        size={18}
        filled={notice.kind === 'comment_like'}
        className={cn(
          'mt-0.5 shrink-0',
          notice.kind === 'comment_like' ? 'text-rose-500' : 'text-muted-foreground',
        )}
      />
      <span className="min-w-0 flex-1">
        <span className="block text-base text-foreground">{text}</span>
        {notice.excerpt && (
          <span className="mt-0.5 block truncate text-xs-plus text-muted-foreground">
            „{notice.excerpt}“
          </span>
        )}
        <span className="mt-0.5 block text-2xs text-muted-foreground">
          {when(notice.updated_at)}
          {notice.album && notice.kind !== 'new_media' && ` · ${notice.album.title}`}
        </span>
      </span>
      {notice.media?.thumb && (
        <img
          src={notice.media.thumb}
          alt=""
          loading="lazy"
          className="h-11 w-11 shrink-0 rounded-md object-cover"
        />
      )}
    </>
  )
  const row = 'flex items-start gap-2.5 px-4 py-3 transition hover:bg-secondary/40'

  if (notice.media) {
    return (
      <Link
        to="/albums/$albumId"
        params={{ albumId: notice.media.album_id }}
        search={{ medium: notice.media.id }}
        onClick={onOpen}
        className={row}
      >
        {body}
      </Link>
    )
  }
  if (notice.album) {
    return (
      <Link
        to="/albums/$albumId"
        params={{ albumId: notice.album.id }}
        onClick={onOpen}
        className={row}
      >
        {body}
      </Link>
    )
  }
  return <div className={row}>{body}</div>
}
