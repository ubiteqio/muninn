import { useTranslation } from 'react-i18next'

import { SectionHeading } from '@/components/muninn/section-heading'
import { Toggle } from '@/components/muninn/toggle'
import { Card } from '@/components/ui/card'
import {
  type NotificationSettings,
  useNotificationSettings,
  useSaveNotificationSettings,
} from '@/features/profile/use-notification-settings'

/** The events in the order the concept lists them. */
const EVENTS = [
  'reply',
  'mention',
  'comment_like',
  'comment',
  'activity',
  'new_media',
  'admin_alerts',
] as const

/**
 * Which events also come as a push notification, and the quiet hours without any. In the app
 * everything appears regardless - the page says so, because otherwise switching something off
 * looks like it hides it. Every change is saved as it is made.
 */
export function NotificationsCard() {
  const { t } = useTranslation()
  const settings = useNotificationSettings()
  const save = useSaveNotificationSettings()
  const current = settings.data

  const change = (next: Partial<NotificationSettings>) => {
    if (current) save.mutate({ ...current, ...next })
  }

  return (
    <section aria-labelledby="notifications-heading" className="space-y-3">
      <SectionHeading id="notifications-heading" title={t('profile.notifications.title')} />
      <p className="text-xs-plus text-muted-foreground">{t('profile.notifications.hint')}</p>

      <Card className="divide-y divide-hairline/[0.06] overflow-hidden">
        {current &&
          EVENTS.filter((event) => event in current.push).map((event) => (
            <div key={event} className="flex items-center gap-3 px-4 py-3">
              <span className="min-w-0 flex-1">
                <span className="block text-base text-foreground">
                  {t(`profile.notifications.event.${event}`)}
                </span>
              </span>
              <Toggle
                label={t(`profile.notifications.event.${event}`)}
                checked={current.push[event] ?? false}
                onChange={(on) => {
                  change({ push: { ...current.push, [event]: on } })
                }}
              />
            </div>
          ))}
      </Card>

      {current && (
        <Card className="space-y-3 p-4">
          <div className="flex items-center gap-3">
            <span className="min-w-0 flex-1">
              <span className="block text-base text-foreground">
                {t('profile.notifications.quiet')}
              </span>
              <span className="block text-xs-plus text-muted-foreground">
                {t('profile.notifications.quietHint')}
              </span>
            </span>
            <Toggle
              label={t('profile.notifications.quiet')}
              checked={current.quiet_enabled}
              onChange={(on) => {
                change({ quiet_enabled: on })
              }}
            />
          </div>
          {current.quiet_enabled && (
            <div className="flex items-center gap-2 text-base text-muted-foreground">
              <TimeField
                label={t('profile.notifications.from')}
                value={current.quiet_start}
                onChange={(value) => {
                  change({ quiet_start: value })
                }}
              />
              <span>–</span>
              <TimeField
                label={t('profile.notifications.until')}
                value={current.quiet_end}
                onChange={(value) => {
                  change({ quiet_end: value })
                }}
              />
            </div>
          )}
        </Card>
      )}
    </section>
  )
}

/** "22:00" in and out; the server answers "22:00:00". Saved once the time is complete. */
function TimeField({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label className="flex items-center gap-1.5">
      <span className="sr-only">{label}</span>
      <input
        type="time"
        value={value.slice(0, 5)}
        onChange={(event) => {
          if (/^\d{2}:\d{2}$/.test(event.target.value)) onChange(event.target.value)
        }}
        className="rounded-md border border-hairline/15 bg-secondary/40 px-2 py-1 text-base text-foreground"
      />
    </label>
  )
}
