import type { components } from '@/api/generated/schema'

type Moment = components['schemas']['MomentView']
type Spoken = components['schemas']['SpokenView']

/** A spoken part stays on screen this long after it ended, so a short sentence can be read. */
const LINGER_SECONDS = 2

/** The last second that was looked at, up to now. Before the first one, the first one. */
export function momentAt(moments: Moment[], time: number): Moment | undefined {
  let found = moments[0]
  for (const item of moments) {
    if (item.second > time) break
    found = item
  }
  return found
}

/** What is being said right now, or was a moment ago. */
export function spokenAt(parts: Spoken[], time: number): Spoken | undefined {
  let found: Spoken | undefined
  for (const part of parts) {
    if (part.start > time) break
    if (time <= part.end + LINGER_SECONDS) found = part
  }
  return found
}
