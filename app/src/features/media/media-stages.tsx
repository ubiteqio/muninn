import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, unwrap } from '@/api/client'
import { Symbol } from '@/components/muninn/symbol'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useAuthStore } from '@/features/auth/auth-store'
import { cn } from '@/lib/utils'

/** What the pipeline did to a medium: one line per step. */
interface Stage {
  stage: string
  state: string
  attempts: number
  last_error?: string | null | undefined
}

function stagesKey(mediaId: string) {
  return ['media', mediaId, 'stages'] as const
}

/**
 * Everything the pipeline can do to one medium, for an admin standing in front of it.
 *
 * The menu only asks the server when it is opened: a viewer that fetched this for every picture
 * one swipes past would ask a question nobody had.
 */
export function MediaStagesMenu({ mediaId }: { mediaId: string }) {
  const { t } = useTranslation()
  const isAdmin = useAuthStore((state) => state.user?.role === 'admin')
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  const stages = useQuery({
    queryKey: stagesKey(mediaId),
    enabled: isAdmin && open,
    queryFn: async (): Promise<Stage[]> => {
      const answer = await unwrap(
        await api.GET('/api/v1/media/{media_id}/stages', {
          params: { path: { media_id: mediaId } },
        }),
      )
      return answer.stages
    },
  })

  const run = useMutation({
    mutationFn: async (stage: string): Promise<Stage[]> => {
      const answer = await unwrap(
        await api.POST('/api/v1/media/{media_id}/stages/{stage}', {
          params: { path: { media_id: mediaId, stage } },
        }),
      )
      return answer.stages
    },
    onSuccess: (next) => {
      queryClient.setQueryData(stagesKey(mediaId), next)
      // What the step writes lands on the medium itself, so its details are asked again.
      void queryClient.invalidateQueries({ queryKey: ['media', mediaId] })
    },
  })

  if (!isAdmin) return null

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t('media.stages.title')}
          className="flex size-11 items-center justify-center rounded-full bg-black/45 text-white backdrop-blur-sm transition hover:bg-black/65"
        >
          <Symbol name="more_horiz" size={22} />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[280px]">
        <p className="px-2 py-1.5 text-xs font-semibold uppercase tracking-section text-muted-foreground">
          {t('media.stages.title')}
        </p>
        {stages.isPending && (
          <p className="px-2 py-1.5 text-base text-muted-foreground">{t('common.loading')}</p>
        )}
        {(stages.data ?? [])
          .filter((step) => step.state !== 'not-for-this')
          .map((step) => (
            <DropdownMenuItem
              key={step.stage}
              disabled={run.isPending}
              onSelect={(event) => {
                // The menu stays open: one usually asks for more than one step.
                event.preventDefault()
                run.mutate(step.stage)
              }}
            >
              <span className="flex w-full items-start gap-2">
                <Symbol
                  name={ICONS[step.stage] ?? 'auto_awesome'}
                  size={18}
                  className={cn(
                    'mt-0.5 shrink-0',
                    step.state === 'given-up' ? 'text-destructive' : 'text-muted-foreground',
                  )}
                />
                <span className="min-w-0 flex-1">
                  <span className="block">{t(`media.stages.${step.stage}`)}</span>
                  <span className="block truncate text-xs-plus text-muted-foreground">
                    {step.state === 'given-up'
                      ? t('media.stages.gaveUp', { count: step.attempts })
                      : t(`media.stages.state.${step.state}`)}
                  </span>
                  {step.state === 'given-up' && step.last_error && (
                    <span className="block truncate text-xs-plus text-destructive/80">
                      {step.last_error}
                    </span>
                  )}
                </span>
                {step.state === 'done' && (
                  <Symbol name="check_circle" size={16} className="mt-0.5 shrink-0 text-primary" />
                )}
              </span>
            </DropdownMenuItem>
          ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** One icon per step, so the list can be read at a glance. */
const ICONS: Record<string, string> = {
  metadata: 'info',
  derive: 'photo_library',
  image_vector: 'image_search',
  transcription: 'chat_bubble',
  analysis: 'auto_awesome',
  caption_vector: 'search',
  faces: 'group',
}
