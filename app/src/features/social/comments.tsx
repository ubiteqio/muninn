import {
  type KeyboardEvent,
  type ReactNode,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { PersonInitial } from '@/components/muninn/person-initial'
import { Symbol } from '@/components/muninn/symbol'
import {
  type Comment,
  type Person,
  useAddComment,
  useComments,
  useDeleteComment,
  useEditComment,
  useLikeComment,
  usePeople,
} from '@/features/social/use-comments'
import type { SocialTarget } from '@/features/social/use-social'
import { when } from '@/features/social/when'
import { cn } from '@/lib/utils'

/**
 * The conversation about a medium or album: comments with their answers underneath, a heart on
 * each, and a field to write in. Kept quiet - names and times small, the words themselves in
 * the reading size - so a long thread stays readable in a narrow panel.
 */
export function CommentsSection({ target }: { target: SocialTarget }) {
  const { t } = useTranslation()
  const comments = useComments(target)
  const [answering, setAnswering] = useState<string | null>(null)
  const items = comments.data?.items ?? []

  return (
    <section aria-label={t('comments.title')} className="space-y-4">
      {comments.isPending && (
        <p className="text-xs-plus text-muted-foreground">{t('comments.loading')}</p>
      )}
      {comments.isSuccess && items.length === 0 && (
        <p className="text-xs-plus text-muted-foreground">{t('comments.none')}</p>
      )}

      <ol className="space-y-4">
        {items.map((comment) => (
          <li key={comment.id}>
            <CommentItem
              target={target}
              comment={comment}
              onAnswer={() => {
                setAnswering(comment.id)
              }}
            />
            {comment.replies.length > 0 && (
              <ol className="ml-9 mt-3 space-y-3 border-l border-hairline/10 pl-3">
                {comment.replies.map((reply) => (
                  <li key={reply.id}>
                    <CommentItem
                      target={target}
                      comment={reply}
                      small
                      onAnswer={() => {
                        setAnswering(comment.id)
                      }}
                    />
                  </li>
                ))}
              </ol>
            )}
            {answering === comment.id && (
              <div className="ml-9 mt-3">
                <Composer
                  target={target}
                  parentId={comment.id}
                  autoFocus
                  placeholder={t('comments.answerTo', { name: comment.author.display_name })}
                  onDone={() => {
                    setAnswering(null)
                  }}
                />
              </div>
            )}
          </li>
        ))}
      </ol>

      <Composer target={target} placeholder={t('comments.placeholder')} />
    </section>
  )
}

function CommentItem({
  target,
  comment,
  small = false,
  onAnswer,
}: {
  target: SocialTarget
  comment: Comment
  small?: boolean
  onAnswer: () => void
}) {
  const { t } = useTranslation()
  const like = useLikeComment(target)
  const remove = useDeleteComment(target)
  const [editing, setEditing] = useState(false)

  if (comment.deleted) {
    return <p className="text-xs-plus italic text-muted-foreground/70">{t('comments.deleted')}</p>
  }

  return (
    <article className="flex gap-2.5">
      <PersonInitial name={comment.author.display_name} size={small ? 24 : 28} />
      <div className="min-w-0 flex-1">
        <p className="flex items-baseline gap-2">
          <span className="truncate text-xs-plus font-semibold text-foreground">
            {comment.author.display_name}
          </span>
          <span className="shrink-0 text-2xs text-muted-foreground">
            {when(comment.created_at)}
            {comment.edited_at && ` · ${t('comments.edited')}`}
          </span>
        </p>

        {editing ? (
          <div className="mt-1">
            <Composer
              target={target}
              editing={comment}
              autoFocus
              onDone={() => {
                setEditing(false)
              }}
            />
          </div>
        ) : (
          <p className="mt-0.5 whitespace-pre-wrap break-words text-base text-foreground">
            {withMentions(comment.body)}
          </p>
        )}

        {!editing && (
          <div className="mt-1 flex items-center gap-3 text-2xs text-muted-foreground">
            <button
              type="button"
              aria-pressed={comment.liked}
              aria-label={t(comment.liked ? 'comments.unlike' : 'comments.like')}
              onClick={() => {
                like.mutate({ id: comment.id, on: !comment.liked })
              }}
              className={cn(
                'flex items-center gap-0.5 hover:text-foreground',
                comment.liked && 'text-rose-500',
              )}
            >
              <Symbol name="favorite" size={13} filled={comment.liked} />
              {comment.likes > 0 && <span className="tabular-nums">{comment.likes}</span>}
            </button>
            <button type="button" onClick={onAnswer} className="hover:text-foreground">
              {t('comments.answer')}
            </button>
            {comment.can_edit && (
              <button
                type="button"
                onClick={() => {
                  setEditing(true)
                }}
                className="hover:text-foreground"
              >
                {t('comments.edit')}
              </button>
            )}
            {comment.can_delete && (
              <ConfirmDialog
                trigger={
                  <button type="button" className="hover:text-destructive">
                    {t('comments.delete')}
                  </button>
                }
                title={t('comments.confirmDelete.title')}
                description={t('comments.confirmDelete.description')}
                confirmLabel={t('comments.delete')}
                cancelLabel={t('common.cancel')}
                closeLabel={t('common.close')}
                destructive
                pending={remove.isPending}
                onConfirm={async () => {
                  // A refusal leaves the comment where it was, which says enough.
                  await remove.mutateAsync(comment.id).catch(() => undefined)
                }}
              />
            )}
          </div>
        )}
      </div>
    </article>
  )
}

/** "@anna" stands out from the words around it. */
function withMentions(body: string): ReactNode[] {
  return body.split(/(@[\w.-]{2,40})/g).map((part, index) =>
    part.startsWith('@') ? (
      <span key={index} className="font-medium text-accent">
        {part}
      </span>
    ) : (
      part
    ),
  )
}

/**
 * The field to write in. Enter sends, Shift+Enter makes a new line. Typing "@" offers the people
 * who can be named; arrows choose, Enter or Tab takes one.
 */
function Composer({
  target,
  parentId,
  editing,
  placeholder,
  autoFocus = false,
  onDone,
}: {
  target: SocialTarget
  parentId?: string | undefined
  editing?: Comment | undefined
  placeholder?: string | undefined
  autoFocus?: boolean
  onDone?: (() => void) | undefined
}) {
  const { t } = useTranslation()
  const add = useAddComment(target)
  const edit = useEditComment(target)
  const people = usePeople()
  const field = useRef<HTMLTextAreaElement>(null)
  const [text, setText] = useState(editing?.body ?? '')
  const [cursor, setCursor] = useState(0)
  const [chosen, setChosen] = useState(0)

  // The word being typed at the cursor, when it starts with "@".
  const naming = useMemo(() => {
    const before = text.slice(0, cursor)
    const match = /(^|\s)@([\w.-]*)$/.exec(before)
    return match
      ? {
          query: (match[2] ?? '').toLowerCase(),
          start: before.length - (match[2] ?? '').length - 1,
        }
      : null
  }, [text, cursor])
  const offered: Person[] = useMemo(() => {
    if (!naming) return []
    return (people.data ?? [])
      .filter(
        (person) =>
          person.username.toLowerCase().startsWith(naming.query) ||
          person.display_name.toLowerCase().startsWith(naming.query),
      )
      .slice(0, 5)
  }, [naming, people.data])

  const busy = add.isPending || edit.isPending

  // Where the caret goes once the chosen name is in the text - set right after that render,
  // before anything else can be typed.
  const caret = useRef<number | null>(null)
  useLayoutEffect(() => {
    if (caret.current === null) return
    field.current?.setSelectionRange(caret.current, caret.current)
    field.current?.focus()
    caret.current = null
  }, [text])

  const take = (person: Person) => {
    if (!naming) return
    const next = `${text.slice(0, naming.start)}@${person.username} ${text.slice(cursor)}`
    const at = naming.start + person.username.length + 2
    caret.current = at
    setText(next)
    setCursor(at)
  }

  const send = () => {
    const body = text.trim()
    if (!body || busy) return
    const done = () => {
      setText('')
      onDone?.()
    }
    if (editing) edit.mutate({ id: editing.id, body }, { onSuccess: done })
    else add.mutate({ body, parentId }, { onSuccess: done })
  }

  const keys = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (offered.length > 0) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault()
        const step = event.key === 'ArrowDown' ? 1 : -1
        setChosen((chosen + step + offered.length) % offered.length)
        return
      }
      if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault()
        const person = offered[chosen] ?? offered[0]
        if (person) take(person)
        return
      }
    }
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      send()
    }
    if (event.key === 'Escape' && onDone) onDone()
  }

  return (
    <div className="relative">
      {/* The rounded field shows the focus as a whole - a soft amber edge and halo - so the
          textarea inside draws no ring of its own. */}
      <div className="flex items-end gap-2 rounded-2xl border border-hairline/15 bg-secondary/40 px-3 py-1.5 transition-[border-color,box-shadow] focus-within:border-accent/50 focus-within:ring-[3px] focus-within:ring-accent/10">
        <textarea
          ref={field}
          rows={1}
          value={text}
          autoFocus={autoFocus}
          placeholder={placeholder ?? t('comments.placeholder')}
          aria-label={placeholder ?? t('comments.placeholder')}
          maxLength={2000}
          onChange={(event) => {
            setText(event.target.value)
            setCursor(event.target.selectionStart)
            setChosen(0)
          }}
          onSelect={(event) => {
            setCursor(event.currentTarget.selectionStart)
          }}
          onKeyDown={keys}
          className="max-h-32 min-h-[28px] flex-1 resize-none bg-transparent py-1 text-base text-foreground outline-none placeholder:text-muted-foreground focus-visible:ring-0 focus-visible:ring-offset-0"
        />
        <button
          type="button"
          aria-label={editing ? t('comments.save') : t('comments.send')}
          disabled={!text.trim() || busy}
          onClick={send}
          className="mb-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground transition disabled:opacity-40"
        >
          <Symbol name={editing ? 'check_circle' : 'arrow_upward'} size={18} />
        </button>
      </div>

      {offered.length > 0 && (
        <ul
          role="listbox"
          aria-label={t('comments.people')}
          className="absolute bottom-full left-0 z-10 mb-1 w-56 overflow-hidden rounded-lg border border-hairline/15 bg-background shadow-lg"
        >
          {offered.map((person, index) => (
            <li
              key={person.id}
              role="option"
              aria-selected={index === chosen}
              onMouseDown={(event) => {
                event.preventDefault()
                take(person)
              }}
              className={cn(
                'cursor-pointer px-3 py-1.5 text-base',
                index === chosen ? 'bg-accent/15 text-foreground' : 'text-muted-foreground',
              )}
            >
              {person.display_name}
              <span className="ml-1.5 text-2xs text-muted-foreground">@{person.username}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
