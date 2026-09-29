import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SectionHeading } from '@/components/muninn/section-heading'
import { Symbol } from '@/components/muninn/symbol'
import { chooseTheme, storedTheme, type Theme } from '@/lib/theme'
import { cn } from '@/lib/utils'

const CHOICES: { value: Theme; icon: string }[] = [
  { value: 'system', icon: 'contrast' },
  { value: 'light', icon: 'light_mode' },
  { value: 'dark', icon: 'dark_mode' },
]

/** Light, dark, or as the device says - for this device, taking effect at once. */
export function AppearanceCard() {
  const { t } = useTranslation()
  const [theme, setTheme] = useState<Theme>(storedTheme)

  return (
    <section aria-labelledby="appearance-heading" className="space-y-3">
      <SectionHeading id="appearance-heading" title={t('profile.appearance.title')} />
      <div
        role="radiogroup"
        aria-label={t('profile.appearance.title')}
        className="grid grid-cols-3 gap-2"
      >
        {CHOICES.map((choice) => (
          <button
            key={choice.value}
            type="button"
            role="radio"
            aria-checked={theme === choice.value}
            onClick={() => {
              chooseTheme(choice.value)
              setTheme(choice.value)
            }}
            className={cn(
              'flex flex-col items-center gap-1.5 rounded-xl border px-3 py-3 text-xs-plus transition',
              theme === choice.value
                ? 'border-primary bg-primary/10 text-foreground'
                : 'border-hairline/15 text-muted-foreground hover:text-foreground',
            )}
          >
            <Symbol name={choice.icon} size={22} />
            {t(`profile.appearance.${choice.value}`)}
          </button>
        ))}
      </div>
      <p className="text-xs-plus text-muted-foreground">{t('profile.appearance.hint')}</p>
    </section>
  )
}
