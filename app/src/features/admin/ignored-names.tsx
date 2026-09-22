import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { isValidIgnoredName } from '@/features/admin/settings-rules'
import { Field } from '@/features/auth/field'

interface IgnoredNamesProps {
  names: string[]
  onChange: (names: string[]) => void
  onInvalid: () => void
}

/** The names the scanner skips, as removable chips plus one field to add another. */
export function IgnoredNames({ names, onChange, onInvalid }: IgnoredNamesProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState('')

  function add() {
    const name = draft.trim()
    if (!isValidIgnoredName(name)) {
      onInvalid()
      return
    }

    setDraft('')
    // Names are compared without case, so the same folder cannot be listed twice.
    if (names.some((existing) => existing.toLowerCase() === name.toLowerCase())) return
    onChange([...names, name])
  }

  return (
    <div className="mt-4 space-y-3">
      {names.length === 0 ? (
        <p className="text-base text-muted-foreground">{t('admin.settings.ignored.empty')}</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {names.map((name) => (
            <li key={name}>
              <button
                type="button"
                aria-label={t('admin.settings.ignored.remove', { name })}
                onClick={() => {
                  onChange(names.filter((other) => other !== name))
                }}
                className="flex items-center gap-1.5 rounded-full border border-hairline/10 bg-secondary/60 py-1.5 pl-3 pr-2 text-base text-foreground transition hover:border-destructive/40"
              >
                <span className="font-mono">{name}</span>
                <Symbol name="close" size={16} className="text-muted-foreground" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <Field
            label={t('admin.settings.ignored.add')}
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value)
            }}
            onKeyDown={(event) => {
              // Enter adds the name; without this it would submit the whole form instead.
              if (event.key === 'Enter') {
                event.preventDefault()
                add()
              }
            }}
          />
        </div>
        <Button type="button" variant="outline" className="h-11" onClick={add}>
          {t('admin.settings.ignored.addAction')}
        </Button>
      </div>
    </div>
  )
}
