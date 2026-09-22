import type { TFunction } from 'i18next'
import { useTranslation } from 'react-i18next'

import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { type AiService, useAiHealth, useResumeAi } from '@/features/admin/use-jobs'
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
  const services = health.data?.services ?? []
  const checked = services
    .map((service) => service.checked_at)
    .filter((value): value is string => value !== null)
    .sort()
    .at(-1)
  const now = useTicker(checked !== undefined, 5000)

  if (services.length === 0) return null

  return (
    <section aria-label={t('admin.jobs.ai.title')}>
      <SectionHeading title={t('admin.jobs.ai.title')} />
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
  const resume = useResumeAi()
  const state = stateOf(service)
  const label = t(`admin.ai.kind.${service.kind}`)
  const status = t(`admin.jobs.ai.state.${state}`)
  const paused = service.paused_until
    ? t('admin.jobs.ai.pausedUntil', { time: clock(service.paused_until) })
    : null
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
      {paused && <span className="text-muted-foreground">· {paused}</span>}
    </>
  )

  // While the worker rests the stage, the chip is the way to wake it: the admin often knows
  // before the pause is over that the machine is back.
  if (paused) {
    return (
      <li>
        <button
          type="button"
          title={[title, t('admin.jobs.ai.resumeHint')].filter(Boolean).join('\n')}
          aria-label={[label, status, paused, t('admin.jobs.ai.resumeShort')].join(', ')}
          disabled={resume.isPending}
          className={cn(
            chip,
            'transition hover:border-accent/50 hover:bg-secondary/60 disabled:opacity-60',
          )}
          onClick={() => {
            resume.mutate(service.kind)
          }}
        >
          {content}
          <span className="flex items-center gap-1 font-medium text-accent">
            <Symbol name="sync" size={16} className={cn(resume.isPending && 'animate-spin')} />
            {t('admin.jobs.ai.resumeShort')}
          </span>
        </button>
      </li>
    )
  }

  return (
    <li title={title} aria-label={[label, status].filter(Boolean).join(', ')} className={chip}>
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
