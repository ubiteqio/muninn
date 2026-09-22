import { useCallback, useEffect, useRef, useState } from 'react'

interface Playback {
  /** Where the video stands, in seconds. */
  time: number
  playing: boolean
  /** Whether a video element was found at all; without one nothing follows along. */
  attached: boolean
  seek: (seconds: number) => void
}

/** How often the element is looked for while PhotoSwipe is still building the slide. */
const LOOK_AGAIN_MS = 250
const LOOK_AT_MOST = 20

/**
 * Follows the video on screen: where it stands and whether it plays, and a way to jump.
 *
 * The element belongs to PhotoSwipe, which builds it a moment after the panel opens, so it is
 * looked for a few times rather than once. `timeupdate` comes about four times a second, which
 * is as often as the panel needs to change anyway.
 */
export function usePlayback(findVideo: (() => HTMLVideoElement | null) | undefined): Playback {
  const [video, setVideo] = useState<HTMLVideoElement | null>(null)
  // Jumping writes to the element; React state is for reading, the ref for writing.
  const element = useRef<HTMLVideoElement | null>(null)
  const [time, setTime] = useState(0)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (!findVideo) return
    let tries = 0
    let timer: ReturnType<typeof setTimeout> | undefined
    const look = () => {
      const found = findVideo()
      if (found) {
        element.current = found
        setVideo(found)
        return
      }
      tries += 1
      if (tries < LOOK_AT_MOST) timer = setTimeout(look, LOOK_AGAIN_MS)
    }
    look()
    return () => {
      clearTimeout(timer)
    }
  }, [findVideo])

  useEffect(() => {
    if (!video) return
    const follow = () => {
      setTime(video.currentTime)
      setPlaying(!video.paused && !video.ended)
    }
    follow()
    const events = ['timeupdate', 'play', 'pause', 'seeked', 'ended'] as const
    for (const name of events) video.addEventListener(name, follow)
    return () => {
      for (const name of events) video.removeEventListener(name, follow)
    }
  }, [video])

  const seek = useCallback((seconds: number) => {
    const playing = element.current
    if (!playing) return
    playing.currentTime = Math.max(0, seconds)
    setTime(playing.currentTime)
  }, [])

  return { time, playing, attached: video !== null, seek }
}
