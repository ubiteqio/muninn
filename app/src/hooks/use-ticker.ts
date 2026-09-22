import { useEffect, useState } from 'react'

/**
 * A clock that ticks while something on screen is told in relative time.
 *
 * "vor 5 s" is written once and then stands there for ever: React has no reason to render again
 * when the data behind it has not moved. The tick gives it one, and stops as soon as nothing on
 * the page depends on the passing time.
 */
export function useTicker(running: boolean, everyMs = 1000): number {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (!running) return

    const timer = setInterval(() => {
      setNow(Date.now())
    }, everyMs)
    return () => {
      clearInterval(timer)
    }
  }, [running, everyMs])

  return now
}
