import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import { copyText } from '@/lib/copy-text'

/**
 * Shows a generated starting password. It is readable exactly once, right here: the server keeps
 * only the hash, so if this is closed without noting it down, the only way on is another reset.
 */
export function StartingPassword({ password, name }: { password: string; name: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState<boolean | null>(null)
  const shown = useRef<HTMLElement>(null)

  async function copy() {
    const done = await copyText(password)
    setCopied(done)
    if (!done) selectShown()
  }

  // When nothing can be copied for us, the password is at least selected for Cmd+C.
  function selectShown() {
    const element = shown.current
    const selection = window.getSelection()
    if (!element || !selection) return
    const range = document.createRange()
    range.selectNodeContents(element)
    selection.removeAllRanges()
    selection.addRange(range)
  }

  return (
    <div className="rounded-md border border-primary/40 bg-primary/[0.12] p-4">
      <p className="text-base text-foreground">
        {t('admin.users.startingPassword.title', { name })}
      </p>
      <div className="mt-2 flex items-center gap-2">
        <code
          ref={shown}
          onClick={selectShown}
          className="flex-1 select-all rounded-md bg-background/60 px-3 py-2 font-mono text-md tracking-wider text-foreground"
        >
          {password}
        </code>
        <Button
          variant="outline"
          size="icon"
          onClick={() => void copy()}
          aria-label={t('admin.users.startingPassword.copy')}
        >
          <Symbol
            name={copied ? 'check_circle' : 'content_copy'}
            size={20}
            filled={copied === true}
          />
        </Button>
      </div>
      {copied !== null && (
        <p role="status" className="mt-2 text-xs-plus text-foreground">
          {t(
            copied
              ? 'admin.users.startingPassword.copied'
              : 'admin.users.startingPassword.selected',
          )}
        </p>
      )}
      <p className="mt-2 text-xs-plus text-muted-foreground">
        {t('admin.users.startingPassword.hint')}
      </p>
    </div>
  )
}
