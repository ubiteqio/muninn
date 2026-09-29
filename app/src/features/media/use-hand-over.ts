import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { Medium } from '@/features/albums/use-albums'
import { canShareFiles, PhotosDenied, saveMedium, shareMedium } from '@/features/media/hand-over'

/** How long a word about what happened stays on screen. */
const NEWS_MS = 3000

export type Handing = 'save' | 'share'

/**
 * Saving and sharing the medium on screen, and what the user is told about it.
 *
 * A video can take a while to load, so what is under way is known, and a second tap waits for
 * the first. Every outcome is said out loud: a button that seems to do nothing is worse than one
 * that says it failed. `onNews` is told whenever there is something to read.
 */
export function useHandOver(medium: Medium, onNews: () => void) {
  const { t } = useTranslation()
  const [working, setWorking] = useState<Handing | null>(null)
  const [news, setNews] = useState<string | null>(null)

  useEffect(() => {
    if (news === null) return undefined
    const gone = window.setTimeout(() => {
      setNews(null)
    }, NEWS_MS)
    return () => {
      window.clearTimeout(gone)
    }
  }, [news])

  const tell = (text: string) => {
    setNews(text)
    onNews()
  }

  const save = () => {
    if (working !== null) return
    setWorking('save')
    saveMedium(medium)
      .then((outcome) => {
        if (outcome === 'saved') tell(t('media.saved'))
      })
      .catch((error: unknown) => {
        tell(t(error instanceof PhotosDenied ? 'media.photosDenied' : 'media.saveFailed'))
      })
      .finally(() => {
        setWorking(null)
      })
  }

  const share = () => {
    if (working !== null) return
    setWorking('share')
    shareMedium(medium)
      .catch(() => {
        tell(t('media.shareFailed'))
      })
      .finally(() => {
        setWorking(null)
      })
  }

  return { working, news, save, share, shareable: canShareFiles() }
}
