import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { type AiService, useAiHealth, useRetryAi } from '@/features/admin/use-jobs'
import { useTicker } from '@/hooks/use-ticker'
import { cn } from '@/lib/utils'

/**
 * The AI services at a glance: one chip each, green when its machine answered, red when it did
 * not, grey when nothing is set up for it. The reason sits in the tooltip, and a stage the worker
 * rests because its machine was away says until when.
 */
export function AiServices() {
  const { t } = useTranslation()
  const health = useAiHealth()
  const retry = useRetryAi()
  const services = health.data?.services ?? []
  const checked = services
    .map((service) => service.checked_at)
    .filter((value): value is string => value !== null)
    .sort()
    .at(-1)
  const now = useTicker(checked !== undefined, 5000)

  if (services.length === 0) return null

  // Worth offering whenever something is not answering, whether or not a stage happens to
  // carry a pause: the machine is what was switched off and on again, not the stage.
  const ailing = services.some((service) => service.configured && !service.ok)

  return (
    <section aria-label={t('admin.jobs.ai.title')}>
      <div className="flex items-baseline justify-between gap-3">
        <SectionHeading title={t('admin.jobs.ai.title')} />
        {ailing && (
          <button
            type="button"
            disabled={retry.isPending}
            title={t('admin.jobs.ai.retryHint')}
            className="flex shrink-0 items-center gap-1.5 rounded-full border border-hairline/10 bg-card px-3 py-1 text-sm font-medium text-accent transition hover:border-accent/50 hover:bg-secondary/60 disabled:opacity-60"
            onClick={() => {
              retry.mutate()
            }}
          >
            <Symbol name="sync" size={16} className={cn(retry.isPending && 'animate-spin')} />
            {t('admin.jobs.ai.retry')}
          </button>
        )}
      </div>
      <ul className="mt-3 flex flex-wrap gap-2">
        {services.map((service) => (
          <ServiceChip key={service.kind} service={service} />
        ))}
      </ul>
      {checked && (
        <p className="mt-2 text-xs-plus text-muted-foreground">
          {t('admin.jobs.ai.checked', { when: since(checked, now, t) })}
        </p>
      )}
    </section>
  )
}

type State = 'up' | 'down' | 'off'

function stateOf(service: AiService): State {
  if (!service.configured) return 'off'
  return service.ok ? 'up' : 'down'
}

const DOT: Record<State, string> = {
  up: 'bg-emerald-500',
  down: 'bg-destructive',
  off: 'bg-muted-foreground/40',
}

function ServiceChip({ service }: { service: AiService }) {
  const { t } = useTranslation()
  const state = stateOf(service)
  const label = t(`admin.ai.kind.${service.kind}`)
  const status = t(`admin.jobs.ai.state.${state}`)
  const paused = service.paused_until
    ? t('admin.jobs.ai.pausedUntil', { time: clock(service.paused_until) })
    : null
  // Paused, or simply not asked lately: a stage is paused only if it happened to have work
  // while the machine was away, which says more about what there was to do than about it.
  const note = state === 'down' ? (paused ?? t('admin.jobs.ai.whenThereIsWork')) : null
  const title = [service.model, service.detail, paused].filter(Boolean).join('\n') || undefined
  const chip = cn(
    'flex items-center gap-2 rounded-full border border-hairline/10 bg-card px-3 py-1.5 text-sm',
    state === 'off' && 'text-muted-foreground',
  )
  const content = (
    <>
      <span aria-hidden="true" className={cn('h-2.5 w-2.5 shrink-0 rounded-full', DOT[state])} />
      <span className="font-medium">{label}</span>
      {state === 'up' && service.milliseconds !== null && (
        <span className="tabular-nums text-muted-foreground">{duration(service.milliseconds)}</span>
      )}
      {state === 'down' && <span className="text-destructive">{status}</span>}
      {/* Paused, or simply not asked lately: a stage is paused only if it happened to have
        work while the machine was away, which says more about what there was to do. */}
      {note && <span className="text-muted-foreground">· {note}</span>}
    </>
  )

  return (
    <li
      title={title}
      aria-label={[label, status, note].filter(Boolean).join(', ')}
      className={chip}
    >
      {content}
    </li>
  )
}

/** 38 ms, 4,1 s: how long the answer took, short. */
function duration(milliseconds: number): string {
  if (milliseconds < 1000) return `${String(milliseconds)} ms`
  return `${(milliseconds / 1000).toLocaleString('de-DE', { maximumFractionDigits: 1 })} s`
}

function clock(value: string): string {
  return new Date(value).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
}

function since(value: string, now: number, t: TFunction): string {
  const passed = Math.max(0, Math.round((now - new Date(value).getTime()) / 1000))
  return t('admin.jobs.agoSeconds', { count: passed })
}
