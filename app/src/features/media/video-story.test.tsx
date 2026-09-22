import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { momentAt, spokenAt } from '@/features/media/story'
import { VideoStory } from '@/features/media/video-story'

const MOMENTS = [
  { second: 0, caption: 'Ein Junge sitzt vor der Couch.' },
  { second: 2, caption: 'Er hält eine orangefarbene Flasche.' },
  { second: 7, caption: 'Er trinkt aus der Flasche.' },
]
const PARTS = [
  { start: 1, end: 2.5, text: 'Guck mal, Papa!' },
  { start: 8, end: 9, text: 'Lecker!' },
]

function aVideo(): HTMLVideoElement {
  const video = document.createElement('video')
  document.body.append(video)
  return video
}

/** Moves the fake player and tells the panel, the way a playing video would. */
function playTo(video: HTMLVideoElement, seconds: number) {
  act(() => {
    video.currentTime = seconds
    video.dispatchEvent(new Event('timeupdate'))
  })
}

describe('VideoStory', () => {
  it('says what is on screen and what is said, following the playback', async () => {
    const video = aVideo()
    render(
      <VideoStory
        duration={10}
        moments={MOMENTS}
        transcript={{ language: 'de', model: 'whisper', parts: PARTS }}
        findVideo={() => video}
      />,
    )

    expect(await screen.findByText('Ein Junge sitzt vor der Couch.')).toBeInTheDocument()

    playTo(video, 2)
    expect(screen.getByText('Er hält eine orangefarbene Flasche.')).toBeInTheDocument()
    expect(screen.getByText('„Guck mal, Papa!“')).toBeInTheDocument()

    playTo(video, 7.5)
    expect(screen.getByText('Er trinkt aus der Flasche.')).toBeInTheDocument()
    // The words from second one have long been said.
    expect(screen.queryByText('„Guck mal, Papa!“')).toBeNull()
    expect(screen.getByRole('slider', { name: 'Zeitstrahl des Videos' })).toHaveAttribute(
      'aria-valuetext',
      '0:07',
    )
  })

  it('jumps to a sentence from everything that was said', async () => {
    const video = aVideo()
    render(
      <VideoStory
        duration={10}
        moments={MOMENTS}
        transcript={{ language: 'de', model: 'whisper', parts: PARTS }}
        findVideo={() => video}
      />,
    )

    await userEvent.click(await screen.findByText('Alles Gesagte · 2 Sätze'))
    const said = screen.getByRole('list')
    await userEvent.click(within(said).getByRole('button', { name: /Lecker!/ }))

    expect(video.currentTime).toBe(8)
  })

  it('says so when nobody speaks in the video', () => {
    render(
      <VideoStory
        duration={10}
        moments={MOMENTS}
        transcript={{ language: '', model: 'whisper', parts: [] }}
      />,
    )

    expect(screen.getByText('Im Video wird nicht gesprochen.')).toBeInTheDocument()
    expect(screen.queryByText(/Alles Gesagte/)).toBeNull()
  })
})

describe('finding the moment', () => {
  it('takes the last second looked at, and the first one before it starts', () => {
    expect(momentAt(MOMENTS, 0)?.second).toBe(0)
    expect(momentAt(MOMENTS, 6.9)?.second).toBe(2)
    expect(momentAt(MOMENTS, 100)?.second).toBe(7)
  })

  it('keeps a sentence on screen for a moment after it was said', () => {
    expect(spokenAt(PARTS, 0.5)).toBeUndefined()
    expect(spokenAt(PARTS, 4)?.text).toBe('Guck mal, Papa!')
    expect(spokenAt(PARTS, 5)).toBeUndefined()
  })
})
