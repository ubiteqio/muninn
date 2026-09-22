import { useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'

import { BrandSplash } from '@/features/auth/splash-screen'

/** How long the mark stands before it dissolves, and how long dissolving takes. */
const HOLD_MS = 900
const FADE_MS = 500

/**
 * The bare address greets with the mark, large and centred, then dissolves into the start page.
 * The intro replaces itself in the history, so the back button never leads back to it.
 */
export function IntroScreen() {
  const navigate = useNavigate()
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    const hold = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 300 : HOLD_MS
    const dissolve = window.setTimeout(() => {
      setLeaving(true)
    }, hold)
    const onward = window.setTimeout(() => {
      void navigate({ to: '/home', replace: true })
    }, hold + FADE_MS)
    return () => {
      window.clearTimeout(dissolve)
      window.clearTimeout(onward)
    }
  }, [navigate])

  return (
    <div
      data-leaving={leaving || undefined}
      className="h-full transition-[opacity,transform] ease-out data-[leaving]:scale-[1.04] data-[leaving]:opacity-0 motion-reduce:data-[leaving]:scale-100"
      style={{ transitionDuration: `${String(FADE_MS)}ms` }}
    >
      <BrandSplash />
    </div>
  )
}
