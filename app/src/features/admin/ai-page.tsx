import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { AdminArea } from '@/features/admin/admin-area'
import { AiProfileForm } from '@/features/admin/ai-profile-form'
import {
  AI_KINDS,
  type AiKind,
  type AiProfile,
  useActivateAiProfile,
  useAiProfiles,
  useRemoveAiProfile,
  useTestAiProfile,
} from '@/features/admin/use-ai'
import { cn } from '@/lib/utils'

/**
 * The machines Muninn asks: one for describing pictures, two for turning them into vectors.
 *
 * Every interface can hold several profiles - the one in use and a spare - because the machine
 * in the house is not always the one that is running.
 */
export function AdminAiPage() {
  const { t } = useTranslation()
  const { data, isPending, isError } = useAiProfiles()

  return (
    <AdminArea section="ai">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{t('admin.ai.title')}</h2>
        <p className="mt-1.5 text-base text-muted-foreground">{t('admin.ai.description')}</p>
      </div>

      {isPending && <p className="text-base text-muted-foreground">{t('admin.ai.loading')}</p>}
      {isError && <p className="text-base text-destructive">{t('auth.error.unreachable')}</p>}

      {data &&
        AI_KINDS.map((kind) => (
          <Interface key={kind} kind={kind} profiles={data.filter((one) => one.kind === kind)} />
        ))}
    </AdminArea>
  )
}

function Interface({ kind, profiles }: { kind: AiKind; profiles: AiProfile[] }) {
  const { t } = useTranslation()
  const [adding, setAdding] = useState(false)

  return (
    <section aria-labelledby={`ai-${kind}`} className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <h3 id={`ai-${kind}`} className="text-md font-semibold text-foreground">
            {t(`admin.ai.kind.${kind}`)}
          </h3>
          <p className="mt-0.5 text-xs-plus text-muted-foreground">
            {t(`admin.ai.kindHint.${kind}`)}
          </p>
        </div>
        {!adding && (
          <Button
            variant="outline"
            className="h-8 shrink-0 px-2 text-xs-plus"
            onClick={() => {
              setAdding(true)
            }}
          >
            <Symbol name="add_photo_alternate" size={16} />
            {t('admin.ai.add')}
          </Button>
        )}
      </div>

      {profiles.length === 0 && !adding && (
        <Card className="p-5 text-base text-muted-foreground">{t('admin.ai.none')}</Card>
      )}

      {profiles.map((profile) => (
        <ProfileRow key={profile.id} profile={profile} />
      ))}

      {adding && (
        <Card className="p-5">
          <AiProfileForm
            kind={kind}
            onDone={() => {
              setAdding(false)
            }}
          />
        </Card>
      )}
    </section>
  )
}

function ProfileRow({ profile }: { profile: AiProfile }) {
  const { t } = useTranslation()
  const [editing, setEditing] = useState(false)
  const activate = useActivateAiProfile()
  const remove = useRemoveAiProfile()
  const test = useTestAiProfile()

  return (
    <Card className={cn('p-5', profile.is_active && 'ring-1 ring-primary/30')}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-base font-semibold text-foreground">
            {profile.name}
            {profile.is_active && (
              <span className="rounded-badge bg-primary/[0.14] px-1.5 py-0.5 text-3xs font-medium uppercase tracking-section text-primary">
                {t('admin.ai.inUse')}
              </span>
            )}
          </p>
          <p className="mt-0.5 truncate font-mono text-xs-plus text-muted-foreground">
            {profile.model} · {profile.base_url}
          </p>
          <p className="mt-0.5 text-xs-plus text-muted-foreground">
            {t('admin.ai.limits', {
              concurrency: profile.concurrency,
              seconds: profile.timeout_seconds,
            })}
            {profile.has_api_key && ` · ${t('admin.ai.keyStored')}`}
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            className="h-8 px-2 text-xs-plus"
            disabled={test.isPending}
            onClick={() => {
              test.mutate(profile.id)
            }}
          >
            <Symbol name="sync" size={16} />
            {test.isPending ? t('admin.ai.testing') : t('admin.ai.test')}
          </Button>
          {!profile.is_active && (
            <Button
              variant="outline"
              className="h-8 px-2 text-xs-plus"
              disabled={activate.isPending}
              onClick={() => {
                activate.mutate(profile.id)
              }}
            >
              {t('admin.ai.use')}
            </Button>
          )}
          <Button
            variant="outline"
            className="h-8 px-2 text-xs-plus"
            onClick={() => {
              setEditing((open) => !open)
            }}
          >
            {t(editing ? 'admin.ai.closeEdit' : 'admin.ai.edit')}
          </Button>
          <Button
            variant="outline"
            className="h-8 px-2 text-xs-plus"
            disabled={remove.isPending}
            onClick={() => {
              remove.mutate(profile.id)
            }}
          >
            <Symbol name="delete" size={16} />
          </Button>
        </div>
      </div>

      {test.data && (
        <p
          role="status"
          className={cn(
            'mt-3 flex items-start gap-2 text-base',
            test.data.ok ? 'text-foreground' : 'text-destructive',
          )}
        >
          <Symbol name={test.data.ok ? 'check_circle' : 'error'} size={18} className="mt-0.5" />
          <span>
            {test.data.detail}
            <span className="block text-xs-plus text-muted-foreground">
              {t('admin.ai.took', { count: test.data.milliseconds })}
            </span>
          </span>
        </p>
      )}

      {editing && (
        <div className="mt-4 border-t border-hairline/[0.06] pt-4">
          <AiProfileForm
            kind={profile.kind}
            profile={profile}
            onDone={() => {
              setEditing(false)
            }}
          />
        </div>
      )}
    </Card>
  )
}
