import { Link } from '@tanstack/react-router'
import type { TFunction } from 'i18next'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ConfirmDialog } from '@/components/muninn/confirm-dialog'
import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { AdminArea } from '@/features/admin/admin-area'
import { AiServices } from '@/features/admin/ai-services'
import {
  type ActiveTask,
  type Change,
  type FinishedTask,
  type Jobs,
  type RunningRead,
  useChanges,
  useJobs,
  useLiveJobs,
  usePurgeQueue,
  useStopRead,
  useStopTask,
  useWaiting,
} from '@/features/admin/use-jobs'
import { formatBytes } from '@/features/media/format'
import { useTicker } from '@/hooks/use-ticker'
import { cn } from '@/lib/utils'

/** What the change log calls things, and the icon that says it at a glance. */
const CHANGE_ICON: Record<string, string> = {
  album_added: 'folder',
  album_removed: 'delete',
  media_added: 'add_photo_alternate',
  media_changed: 'sync',
  media_touched: 'history',
  media_moved: 'arrow_back',
  media_missing: 'warning',
  media_restored: 'check_circle',
  media_removed: 'delete',
}

/**
 * Hliðskjálf's engine room, in the order an admin asks: what is happening right now, what is
 * still outstanding, when the clock comes around, and what the last reads found.
 *
 * The numbers used to sit in one row although they mean two different things - tasks queued in
 * the broker, and work the database still owes. They are now kept apart: the outstanding work is
 * the way a medium travels, the queues are a quiet line underneath, which is what they are.
 */
export function AdminJobsPage() {
  const { t } = useTranslation()
  const { data, isPending, isError } = useJobs()
  const changes = useChanges()
  useLiveJobs()

  return (
    <AdminArea section="jobs">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{t('admin.jobs.title')}</h2>
        <p className="mt-1.5 text-base text-muted-foreground">{t('admin.jobs.description')}</p>
      </div>

      <AiServices />

      {isPending && <p className="text-base text-muted-foreground">{t('admin.jobs.loading')}</p>}
      {isError && <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>}

      {data && (
        <>
          <WhatHuginnDoes jobs={data} />
          <JustFinished jobs={data} />
          <OpenWork jobs={data} />
          <Schedule jobs={data} />
        </>
      )}

      <FoundRecently changes={changes.data ?? []} />
    </AdminArea>
  )
}

/**
 * What Huginn is doing, in one card: the state now, and what happened last.
 *
 * "What is running" used to carry finished work as well, which left a page full of ticked-off
 * lines standing under a heading that promised the present. The state is its own sentence now,
 * and what is over is a stream of its own below it.
 */
function WhatHuginnDoes({ jobs }: { jobs: Jobs }) {
  const { t } = useTranslation()
  // A read reports its own progress below; the task behind it would only say the same twice.
  const tasks = jobs.active.filter((task) => task.stage !== 'read')
  const quiet = jobs.running.length === 0 && tasks.length === 0

  return (
    <section aria-label={t('admin.jobs.now.title')}>
      <SectionHeading title={t('admin.jobs.now.title')} />
      <Card className="mt-3 overflow-hidden">
        {quiet ? (
          <p className="flex items-center gap-2 px-4 py-4 text-base text-muted-foreground">
            <Symbol name={waiting(jobs) ? 'history' : 'check_circle'} size={20} />
            {t(waiting(jobs) ? 'admin.jobs.now.waiting' : 'admin.jobs.now.idle')}
          </p>
        ) : (
          <ul>
            {jobs.running.map((read) => (
              <ReadRow key={read.publication_id} read={read} />
            ))}
            {tasks.map((task) => (
              <TaskRow key={task.task_id} task={task} />
            ))}
          </ul>
        )}

        <p className="border-t border-hairline/[0.06] bg-secondary/25 px-4 py-2.5 text-xs-plus text-muted-foreground">
          {jobs.last_read_at
            ? t('admin.jobs.now.lastRead', {
                when: moment(jobs.last_read_at, t),
                media: jobs.media,
                albums: jobs.albums,
              })
            : t('admin.jobs.now.neverRead')}
          {jobs.schedule.next_quick_sync_at && (
            <>
              {' · '}
              {t('admin.jobs.now.next', {
                when: moment(jobs.schedule.next_quick_sync_at, t),
              })}
            </>
          )}
        </p>
      </Card>
    </section>
  )
}

/** How long a finished piece of work is news. After that it belongs to the change log. */
const FRESH_MS = 2 * 60_000

/**
 * The media that went through a moment ago.
 *
 * A medium takes about a tenth of a second, so asking every few seconds catches one in the act
 * about never - what is finished is the only way to watch the work flow. It is news, not a log:
 * once the newest line has gone cold, the whole section steps aside.
 */
function JustFinished({ jobs }: { jobs: Jobs }) {
  const { t } = useTranslation()
  const now = useTicker(jobs.finished.length > 0)

  const fresh = jobs.finished.filter(
    (task) => now - new Date(task.finished_at).getTime() < FRESH_MS,
  )
  if (fresh.length === 0) return null

  return (
    <section aria-label={t('admin.jobs.finished.title')}>
      <SectionHeading title={t('admin.jobs.finished.title')} />
      <Card className="mt-3 overflow-hidden">
        <Throughput done={jobs.done_last_minute} />
        <ul>
          {fresh.slice(0, FINISHED_SHOWN).map((task) => (
            <FinishedRow
              key={`${task.stage}-${task.finished_at}-${task.label}`}
              task={task}
              now={now}
            />
          ))}
        </ul>
      </Card>
    </section>
  )
}

/** One folder being read, with how far it got and a way to call it off. */
function ReadRow({ read }: { read: RunningRead }) {
  const { t } = useTranslation()
  const stopRead = useStopRead()

  return (
    <li className="space-y-2 border-b border-hairline/[0.06] p-4 last:border-b-0">
      <div className="flex items-center gap-2">
        <p className="flex flex-1 items-center gap-2 text-md font-semibold text-foreground">
          <Symbol name="sync" size={18} className="text-accent" />
          {read.name || t('admin.folders.library')}
        </p>
        <Button
          variant="outline"
          disabled={stopRead.isPending}
          onClick={() => {
            stopRead.mutate(read.publication_id)
          }}
        >
          <Symbol name="block" size={18} />
          {t('admin.jobs.stopRead')}
        </Button>
      </div>

      {read.progress ? (
        <>
          <p className="flex flex-wrap items-center gap-x-2 text-xs-plus text-muted-foreground">
            <span>
              {t('admin.folders.progress.files', {
                done: read.progress.files_done,
                total: read.progress.files_total,
              })}
            </span>
            {read.progress.current && (
              <>
                <span>·</span>
                <span className="truncate font-mono">{read.progress.current}</span>
              </>
            )}
          </p>
          <div
            role="progressbar"
            aria-label={t('admin.folders.progress.label')}
            aria-valuenow={share(read.progress)}
            aria-valuemin={0}
            aria-valuemax={100}
            className="h-1 w-full overflow-hidden rounded-full bg-secondary"
          >
            <div
              className="h-full bg-primary transition-[width]"
              style={{ width: `${String(share(read.progress))}%` }}
            />
          </div>
        </>
      ) : (
        <p className="text-xs-plus text-muted-foreground">{t('admin.jobs.starting')}</p>
      )}
    </li>
  )
}

const STAGE_ICONS: Record<string, string> = {
  derive: 'add_photo_alternate',
  image_vector: 'image_search',
  transcription: 'history',
  analysis: 'image_search',
  caption_vector: 'search',
  faces: 'group',
}

/** One medium in a worker's hands: which stage, which file, for how long. */
function TaskRow({ task }: { task: ActiveTask }) {
  const { t } = useTranslation()
  const stopTask = useStopTask()

  return (
    <li className="flex items-center gap-3 border-b border-hairline/[0.06] px-4 py-2.5 last:border-b-0">
      <Symbol
        name={STAGE_ICONS[task.stage] ?? 'history'}
        size={18}
        className="shrink-0 text-accent"
      />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-base text-foreground">
          {t(stageKey('stage', task.stage, task.media), {
            defaultValue: t(`admin.jobs.stage.${task.stage}`),
          })}
        </span>
        <WhatAndWhere label={task.label} media={task.media} />
      </span>
      <span className="shrink-0 text-xs-plus text-muted-foreground">
        {seconds(task.started_at, t)}
      </span>
      <Button
        variant="outline"
        size="icon"
        aria-label={t('admin.jobs.stop')}
        disabled={stopTask.isPending}
        onClick={() => {
          stopTask.mutate(task.task_id)
        }}
      >
        <Symbol name="block" size={18} />
      </Button>
    </li>
  )
}

/** How many finished pieces of work are worth listing: enough to see a flow, not a log. */
const FINISHED_SHOWN = 4

/** One medium that is through, and how long ago that was. */
function FinishedRow({ task, now }: { task: FinishedTask; now: number }) {
  const { t } = useTranslation()
  const done = t(stageKey('finishedStage', task.stage, task.media), {
    defaultValue: t(`admin.jobs.finishedStage.${task.stage}`),
  })

  return (
    <li className="flex items-center gap-3 border-b border-hairline/[0.06] px-4 py-2 last:border-b-0">
      <Symbol
        name={task.failed ? 'error' : 'check_circle'}
        size={18}
        className={cn('shrink-0', task.failed ? 'text-destructive' : 'text-muted-foreground/70')}
      />
      <span className="min-w-0 flex-1">
        <span
          className={cn(
            'block truncate text-base',
            task.failed ? 'text-foreground' : 'text-muted-foreground',
          )}
        >
          {task.failed ? t(`admin.jobs.failedStage.${task.stage}`, { defaultValue: done }) : done}
        </span>
        <WhatAndWhere label={task.label} media={task.media} quiet />
      </span>
      <span className="shrink-0 text-xs-plus text-muted-foreground">
        {ago(task.finished_at, now, t)}
      </span>
    </li>
  )
}

type TaskMedia = NonNullable<ActiveTask['media']>

/** The key for a stage, in its video wording when the medium is a video and there is one. */
function stageKey(group: 'stage' | 'finishedStage', stage: string, media?: TaskMedia | null) {
  return media?.kind === 'video'
    ? `admin.jobs.${group}.${stage}_video`
    : `admin.jobs.${group}.${stage}`
}

/**
 * Which file, and in which album - each a way there: the file opens in the viewer, the album
 * opens as it is. Without a medium (a read of a whole folder) it is the plain label, if any.
 */
function WhatAndWhere({
  label,
  media,
  quiet = false,
}: {
  label: string
  media?: TaskMedia | null | undefined
  quiet?: boolean
}) {
  if (!label) return null
  const tone = quiet ? 'text-muted-foreground/70' : 'text-muted-foreground'

  if (!media) {
    return <span className={cn('block truncate font-mono text-xs-plus', tone)}>{label}</span>
  }

  return (
    <span className={cn('flex min-w-0 items-baseline gap-1.5 text-xs-plus', tone)}>
      <Link
        to="/albums/$albumId"
        params={{ albumId: media.album_id }}
        search={{ medium: media.id }}
        className="min-w-0 shrink truncate font-mono hover:text-foreground hover:underline"
      >
        {label}
      </Link>
      <span aria-hidden="true">·</span>
      <Link
        to="/albums/$albumId"
        params={{ albumId: media.album_id }}
        className="flex min-w-0 shrink items-center gap-1 truncate hover:text-foreground hover:underline"
      >
        <Symbol name="folder" size={13} className="shrink-0" />
        <span className="truncate">{media.album_path}</span>
      </Link>
    </span>
  )
}

/** What went through in the last minute. Nothing through means the line stays away. */
function Throughput({ done }: { done: Record<string, number> }) {
  const { t } = useTranslation()
  const stages = Object.entries(done).filter(([, count]) => count > 0)

  if (stages.length === 0) return null

  return (
    <p className="border-b border-hairline/[0.06] px-4 py-2 text-xs-plus text-muted-foreground">
      {t('admin.jobs.now.lastMinute')}{' '}
      {stages.map(([stage, count]) => t(`admin.jobs.done.${stage}`, { count })).join(' · ')}
    </p>
  )
}

/**
 * What is behind one of the numbers: the media themselves, and what stopped each of them.
 *
 * A number can only be watched; a list can be acted on. The file and the album say which
 * pictures these are, the count of tries says whether the pipeline has given up, and the last
 * error says what the machine actually said - which until now lived only in a worker's log.
 */
function Behind({ stage }: { stage: string }) {
  const { t } = useTranslation()
  const waiting = useWaiting(stage)

  if (waiting.isPending) {
    return (
      <p className="px-4 pb-3 text-xs-plus text-muted-foreground">{t('admin.jobs.open.loading')}</p>
    )
  }

  const items = waiting.data?.items ?? []
  const files = waiting.data?.files ?? []
  if (items.length === 0 && files.length === 0) {
    return (
      <p className="px-4 pb-3 text-xs-plus text-muted-foreground">{t('admin.jobs.open.gone')}</p>
    )
  }

  return (
    <ul className="border-t border-hairline/[0.06] bg-secondary/25 px-4 py-2">
      {files.map((file) => (
        <li key={file.relative_path} className="py-1 text-xs-plus">
          <span className="font-mono text-foreground">{file.relative_path}</span>
          {file.byte_size > 0 && (
            <span className="text-muted-foreground"> · {formatBytes(file.byte_size)}</span>
          )}
          {file.reason && (
            <span className="mt-0.5 block break-words font-mono text-2xs text-destructive">
              {file.reason}
            </span>
          )}
        </li>
      ))}
      {items.map((item) => (
        <li key={item.media_id} className="py-1 text-xs-plus">
          <Link
            to="/albums/$albumId"
            params={{ albumId: item.album_id }}
            search={{ medium: item.media_id }}
            className="font-mono text-foreground hover:underline"
          >
            {item.filename}
          </Link>
          <span className="text-muted-foreground"> · {item.album}</span>
          {item.byte_size > 0 && (
            <span className="text-muted-foreground"> · {formatBytes(item.byte_size)}</span>
          )}
          {item.attempts > 0 && (
            <span className="text-muted-foreground">
              {' · '}
              {t('admin.jobs.open.attempts', { count: item.attempts })}
              {item.last_at && ` · ${when(item.last_at)}`}
            </span>
          )}
          {item.last_error && (
            <span className="mt-0.5 block break-words font-mono text-2xs text-destructive">
              {item.last_error}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

/**
 * The work still owed, in the order a file travels: seen, read, previews, then the AI stages.
 * Only the steps with something waiting are listed; when nothing waits, one line says so.
 */
function OpenWork({ jobs }: { jobs: Jobs }) {
  const { t } = useTranslation()

  // Which line asks the server what is behind it; one at a time.
  const [open, setOpen] = useState<string | null>(null)

  const steps = [
    // First, because it is the only one nothing will clear by itself: somebody has to give
    // Muninn leave to read those files.
    { key: 'unreadable', stage: 'unreadable', value: jobs.unreadable_files },
    { key: 'check', stage: 'files', value: jobs.waiting_files },
    { key: 'metadata', stage: 'metadata', value: jobs.pending_metadata },
    { key: 'preview', stage: 'derive', value: jobs.pending_derivatives },
    // Only once a picture model is set up; before that there is no such step, not an empty one.
    ...(jobs.pending_image_vectors === null
      ? []
      : [{ key: 'vector', stage: 'image_vector', value: jobs.pending_image_vectors }]),
    ...(jobs.pending_transcripts === null
      ? []
      : [{ key: 'transcript', stage: 'transcription', value: jobs.pending_transcripts }]),
    ...(jobs.pending_analyses === null
      ? []
      : [{ key: 'analysis', stage: 'analysis', value: jobs.pending_analyses }]),
    ...(jobs.pending_caption_vectors === null
      ? []
      : [{ key: 'captionVector', stage: 'caption_vector', value: jobs.pending_caption_vectors }]),
    ...(jobs.pending_faces === null || jobs.pending_faces === undefined
      ? []
      : [{ key: 'faces', stage: 'faces', value: jobs.pending_faces }]),
  ]

  // Only what actually waits. Seven zeros in a row say nothing, and squeeze every label.
  const owed = steps.filter((step) => step.value > 0)
  const queued = jobs.queues.filter((queue) => queue.waiting > 0)

  return (
    <section aria-label={t('admin.jobs.open.title')}>
      <SectionHeading title={t('admin.jobs.open.title')} />
      <Card className="mt-3 overflow-hidden">
        {owed.length === 0 ? (
          <p className="flex items-center gap-2 px-4 py-4 text-base text-muted-foreground">
            <Symbol name="check_circle" size={20} className="shrink-0 text-accent" />
            {t('admin.jobs.open.nothing')}
          </p>
        ) : (
          <ul className="divide-y divide-hairline/[0.06]">
            {owed.map((step) => (
              <li key={step.key}>
                <button
                  type="button"
                  aria-expanded={open === step.stage}
                  onClick={() => {
                    setOpen((shown) => (shown === step.stage ? null : step.stage))
                  }}
                  className="flex w-full items-baseline gap-3 px-4 py-2.5 text-left transition hover:bg-secondary/40"
                >
                  <span className="min-w-12 text-md font-semibold text-foreground">
                    {step.value.toLocaleString('de-DE')}
                  </span>
                  <span className="flex-1 text-base text-muted-foreground">
                    {t(`admin.jobs.open.${step.key}`)}
                  </span>
                  <Symbol
                    name="expand_more"
                    size={18}
                    className={cn(
                      'shrink-0 text-muted-foreground transition-transform',
                      open === step.stage && 'rotate-180',
                    )}
                  />
                </button>
                {open === step.stage && <Behind stage={step.stage} />}
              </li>
            ))}
          </ul>
        )}

        {/* The broker's queues: how much is handed out right now. A diagnosis, not a measure of
            the backlog - and only worth a line while something is in one. */}
        {queued.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-hairline/[0.06] bg-secondary/25 px-4 py-2.5 text-xs-plus text-muted-foreground">
            <span>{t('admin.jobs.open.queues')}</span>
            {queued.map((queue) => (
              <span key={queue.name} className="flex items-center gap-1.5">
                <span className="text-foreground">{queue.waiting.toLocaleString('de-DE')}</span>
                {t(`admin.jobs.open.queue.${queue.name}`)}
                <PurgeQueue name={queue.name} />
              </span>
            ))}
          </div>
        )}
      </Card>
    </section>
  )
}

/** Emptying one queue. It asks first: what is thrown away is gone until the next read. */
function PurgeQueue({ name }: { name: string }) {
  const { t } = useTranslation()
  const purge = usePurgeQueue()

  return (
    <ConfirmDialog
      trigger={
        <Button variant="ghost" className="h-7 px-2 text-xs-plus">
          <Symbol name="delete" size={16} />
          {t('admin.jobs.purge')}
        </Button>
      }
      title={t('admin.jobs.purgeTitle', { queue: t(`admin.jobs.open.queue.${name}`) })}
      description={t('admin.jobs.purgeHint')}
      confirmLabel={t('admin.jobs.purgeConfirm')}
      cancelLabel={t('admin.folders.action.cancel')}
      closeLabel={t('common.close')}
      destructive
      pending={purge.isPending}
      onConfirm={() => {
        purge.mutate(name)
      }}
    />
  )
}

/** When the clock comes around. The next quick read stands in the card above. */
function Schedule({ jobs }: { jobs: Jobs }) {
  const { t } = useTranslation()

  return (
    <section aria-label={t('admin.jobs.schedule.title')}>
      <SectionHeading title={t('admin.jobs.schedule.title')} />
      <p className="mt-2 text-base text-muted-foreground">
        {t('admin.jobs.schedule.quick', {
          count: Math.round(jobs.schedule.quick_sync_seconds / 60),
        })}
        {' · '}
        {t('admin.jobs.schedule.full', {
          hour: jobs.schedule.full_sync_hour,
          when: moment(jobs.schedule.next_full_sync_at, t),
        })}
        {' · '}
        {t('admin.jobs.schedule.stability', { count: jobs.schedule.stability_seconds })}
      </p>
    </section>
  )
}

/**
 * What the last reads found - the log the concept keeps so that the morning after can be
 * explained. A first read finds everything at once, and twenty lines of "Album angelegt" say
 * less than one, so findings of the same kind that follow each other are shown as one line.
 */
function FoundRecently({ changes }: { changes: Change[] }) {
  const { t } = useTranslation()

  return (
    <section aria-label={t('admin.jobs.changes')}>
      <SectionHeading title={t('admin.jobs.changes')} />
      <div className="mt-3">
        {changes.length === 0 ? (
          <Card className="p-5 text-base text-muted-foreground">{t('admin.jobs.noChanges')}</Card>
        ) : (
          <Card className="overflow-hidden">
            <ul>
              {grouped(changes).map((group) => (
                <ChangeRow key={group.newest.id} group={group} />
              ))}
            </ul>
          </Card>
        )}
      </div>
    </section>
  )
}

interface ChangeGroup {
  /** The first of the run, which is also the newest: the log arrives newest first. */
  newest: Change
  count: number
}

/** Findings of the same kind that follow each other, as one entry each. */
function grouped(changes: Change[]): ChangeGroup[] {
  const groups: ChangeGroup[] = []
  for (const change of changes) {
    const last = groups.at(-1)
    if (last && last.newest.kind === change.kind) {
      last.count += 1
      continue
    }
    groups.push({ newest: change, count: 1 })
  }
  return groups
}

function ChangeRow({ group }: { group: ChangeGroup }) {
  const { t } = useTranslation()
  const { newest, count } = group

  return (
    <li className="flex items-center gap-3 border-b border-hairline/[0.06] px-4 py-2.5 last:border-b-0">
      <Symbol
        name={CHANGE_ICON[newest.kind] ?? 'history'}
        size={18}
        className="shrink-0 text-muted-foreground"
      />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-base text-foreground">
          {t(`admin.jobs.change.${newest.kind}`)}
          {count > 1 && (
            <span className="ml-1.5 text-muted-foreground">
              {t('admin.jobs.moreOfThem', { count: count - 1 })}
            </span>
          )}
        </span>
        {newest.path && (
          <span className="block truncate font-mono text-xs-plus text-muted-foreground">
            {newest.path}
          </span>
        )}
      </span>
      <span className="shrink-0 text-xs-plus text-muted-foreground">
        {when(newest.occurred_at)}
      </span>
    </li>
  )
}

/** Whether anything is owed at all, running or not. */
function waiting(jobs: Jobs): boolean {
  return (
    jobs.queues.some((queue) => queue.waiting > 0) ||
    jobs.pending_metadata > 0 ||
    jobs.pending_derivatives > 0 ||
    (jobs.pending_image_vectors ?? 0) > 0 ||
    (jobs.pending_transcripts ?? 0) > 0 ||
    (jobs.pending_analyses ?? 0) > 0 ||
    (jobs.pending_caption_vectors ?? 0) > 0 ||
    (jobs.pending_faces ?? 0) > 0 ||
    jobs.waiting_files > 0
  )
}

/** The time of a finding - with its date as soon as it is not from today. */
function when(occurredAt: string): string {
  const moment = new Date(occurredAt)
  const time = moment.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
  if (moment.toDateString() === new Date().toDateString()) return time
  return `${moment.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })} ${time}`
}

/** How long ago something was finished, in words. */
function ago(finishedAt: string, now: number, t: TFunction): string {
  const passed = Math.max(0, Math.round((now - new Date(finishedAt).getTime()) / 1000))
  return passed < 60
    ? t('admin.jobs.agoSeconds', { count: passed })
    : t('admin.jobs.agoMinutes', { count: Math.round(passed / 60) })
}

/** How long a task has been running, in words. */
function seconds(startedAt: string, t: TFunction): string {
  const passed = Math.max(0, Math.round((Date.now() - new Date(startedAt).getTime()) / 1000))
  return passed < 60
    ? t('admin.jobs.forSeconds', { count: passed })
    : t('admin.jobs.forMinutes', { count: Math.round(passed / 60) })
}

/**
 * How far the read got, in percent of the files it set out to read.
 *
 * Counted in files, not folders: one folder can hold a thousand pictures and take minutes, and
 * a bar that does not move looks like a bar that is stuck.
 */
function share(progress: NonNullable<RunningRead['progress']>): number {
  if (progress.files_total === 0) return 0
  return Math.min(100, Math.round((progress.files_done / progress.files_total) * 100))
}

/**
 * A time in words: "vor 2 Minuten", "in 4 Minuten", "um 01:00 Uhr".
 *
 * Past and future are told apart by the sign of the difference, not by the rounded minutes:
 * half a minute ago rounds to zero, and "läuft gleich an" is the wrong thing to say about
 * something that is over.
 */
function moment(value: string | null, t: TFunction): string {
  if (!value) return t('admin.jobs.unknown')

  const difference = new Date(value).getTime() - Date.now()
  const minutes = Math.round(Math.abs(difference) / 60_000)

  if (difference < 0) {
    return minutes < 1 ? t('admin.jobs.justNow') : t('admin.jobs.agoMinutes', { count: minutes })
  }
  if (minutes < 1) return t('admin.jobs.dueNow')
  if (minutes < 60) return t('admin.jobs.inMinutes', { count: minutes })
  return t('admin.jobs.atTime', {
    time: new Date(value).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }),
  })
}
