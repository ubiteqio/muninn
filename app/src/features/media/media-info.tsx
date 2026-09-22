import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import type { Medium } from '@/features/albums/use-albums'
import { placeName } from '@/features/map/place-name'
import {
  folderOf,
  formatBytes,
  formatCoordinates,
  formatDateTime,
  formatDuration,
} from '@/features/media/format'
import { type Analysis, type Transcript, useMediumDetail } from '@/features/media/use-medium'
import { VideoStory } from '@/features/media/video-story'
import { ViewerSheet } from '@/features/media/viewer-sheet'
import { PeopleInMedium } from '@/features/people/people-in-medium'
import { likedBy } from '@/features/social/liked-by'
import { emojiOf } from '@/features/social/reactions'
import type { Social } from '@/features/social/use-social'

interface MediaInfoProps {
  medium: Medium | undefined
  open: boolean
  onClose: () => void
  /** What the AI saw. Only the detail view carries it; until then the panel goes without. */
  analysis?: Analysis | null | undefined
  /** What is said in a video, from the detail view as well. */
  transcript?: Transcript | null | undefined
  /** The video element on screen, so the panel can follow the playback. */
  findVideo?: (() => HTMLVideoElement | null) | undefined
  /** Who likes it, from the detail view. */
  social?: Social | null | undefined
  /** Who is in it, under the description. Only where the server is asked. */
  people?: ReactNode
  /** Drawn at the end of the panel: the conversation, where there is one. */
  children?: ReactNode
}

interface Row {
  key: string
  label: string
  value: string
  /** A quieter second line, for where a date comes from or what lies beside the file. */
  note?: string | undefined
}

/**
 * What is known about the picture on screen: when, with what, and where it lies on the NAS.
 *
 * The facts come from the medium the grid already fetched. The description and tags come from the
 * detail view, which DescribedMediaInfo asks for; they are left out rather than shown empty, and
 * so are likes and comments until the social milestone.
 */
export function MediaInfo({
  medium,
  open,
  onClose,
  analysis,
  transcript,
  findVideo,
  social,
  people,
  children,
}: MediaInfoProps) {
  const { t } = useTranslation()

  if (!open || !medium) return null

  return (
    <ViewerSheet label={t('media.info.title')} title={t('media.info.title')} onClose={onClose}>
      {analysis && <Description analysis={analysis} />}
      {people}
      {social && social.likes > 0 && (
        <p className="mt-3 flex items-center gap-1.5 text-xs-plus text-muted-foreground">
          <span aria-hidden="true" className="shrink-0 text-sm leading-none">
            {social.reactions
              .slice(0, 3)
              .map((entry) => emojiOf(entry.reaction))
              .join('')}
          </span>
          {likedBy(social, t, { reactions: true })}
        </p>
      )}
      {medium.kind === 'video' && (analysis || transcript) && (
        <VideoStory
          duration={medium.duration_seconds ?? 0}
          moments={analysis?.moments ?? []}
          transcript={transcript}
          findVideo={findVideo}
        />
      )}

      <dl className="mt-4 space-y-3.5">
        {rowsOf(medium, t).map((row) => (
          <div key={row.key}>
            <dt className="text-xs-plus text-muted-foreground">{row.label}</dt>
            <dd className="break-words text-base text-foreground">
              {row.value}
              {row.note && (
                <span className="mt-0.5 block text-xs-plus text-muted-foreground">{row.note}</span>
              )}
            </dd>
          </div>
        ))}
      </dl>

      {children}
    </ViewerSheet>
  )
}

/** The panel for the picture on screen, with what the AI saw once the detail has arrived. */
export function DescribedMediaInfo({
  medium,
  onClose,
  findVideo,
}: {
  medium: Medium
  onClose: () => void
  findVideo?: (() => HTMLVideoElement | null) | undefined
}) {
  const detail = useMediumDetail(medium.id)

  return (
    <MediaInfo
      medium={medium}
      open
      onClose={onClose}
      analysis={detail.data?.analysis}
      transcript={detail.data?.transcript}
      social={detail.data?.social}
      findVideo={findVideo}
      people={<PeopleInMedium mediaId={medium.id} />}
    />
  )
}

/** What the AI saw: the caption as a sentence, the tags as words, text in the picture as written. */
function Description({ analysis }: { analysis: Analysis }) {
  const { t } = useTranslation()

  return (
    <section aria-label={t('media.info.description')} className="mt-4">
      <p className="text-base text-foreground">{analysis.caption}</p>
      {analysis.tags.length > 0 && (
        <ul aria-label={t('media.info.tags')} className="mt-2.5 flex flex-wrap gap-1.5">
          {analysis.tags.map((tag) => (
            <li
              key={tag}
              className="rounded-full border border-hairline/15 px-2.5 py-0.5 text-xs-plus text-muted-foreground"
            >
              {tag}
            </li>
          ))}
        </ul>
      )}
      {analysis.ocr_text && (
        <p className="mt-2.5 text-xs-plus text-muted-foreground">
          {t('media.info.textInPicture')}{' '}
          <span className="font-mono text-foreground">{analysis.ocr_text}</span>
        </p>
      )}
    </section>
  )
}

type Translate = ReturnType<typeof useTranslation>['t']

/** Only what this medium actually has: an empty row says nothing and takes the same space. */
function rowsOf(medium: Medium, t: Translate): Row[] {
  const rows: Row[] = []

  if (medium.taken_at) {
    rows.push({
      key: 'date',
      label: t('media.info.date'),
      value: formatDateTime(medium.taken_at),
      note: noteOnDate(medium, t),
    })
  }

  const camera = [medium.camera_make, medium.camera_model].filter(Boolean).join(' ')
  if (camera) {
    rows.push({
      key: 'camera',
      label: t('media.info.camera'),
      value: camera,
      note: medium.lens ?? undefined,
    })
  }

  const size =
    medium.width && medium.height ? `${String(medium.width)} × ${String(medium.height)}` : ''
  if (medium.kind === 'video') {
    rows.push({
      key: 'video',
      label: t('media.info.video'),
      value: formatDuration(medium.duration_seconds) || t('media.info.unknownDuration'),
      note: size || undefined,
    })
  } else if (size) {
    rows.push({
      key: 'image',
      label: t('media.info.image'),
      value: `${size} ${t('media.info.px')}`,
    })
  }

  const coordinates =
    medium.latitude !== null && medium.longitude !== null
      ? formatCoordinates(medium.latitude, medium.longitude)
      : null
  const place = medium.place ? placeName(medium.place) : null
  if (place ?? coordinates) {
    rows.push({
      key: 'place',
      label: t('media.info.place'),
      value: place ?? coordinates ?? '',
      // GeoNames asks to be named wherever its names are shown.
      note: medium.place?.estimated
        ? t('media.info.placeEstimated')
        : place && coordinates
          ? t('media.info.placeSource', { coordinates })
          : undefined,
    })
  }

  rows.push({
    key: 'file',
    label: t('media.info.file'),
    value: medium.origin.filename,
    // Worth knowing before the download button in the bar above is pressed.
    note: formatBytes(medium.origin.byte_size),
  })

  rows.push({
    key: 'folder',
    label: t('media.info.folder'),
    value: folderOf(medium.origin.relative_path) || t('media.info.libraryRoot'),
  })

  // A RAW beside the JPEG, or the clip of a Live Photo: they belong to the same medium and are
  // easy to miss on the NAS.
  const extras = medium.files.filter((file) => file.role !== 'primary')
  if (extras.length > 0) {
    rows.push({
      key: 'extras',
      label: t('media.info.extras'),
      value: extras.map((file) => file.filename).join(', '),
    })
  }

  return rows
}

/** Where the date comes from. Worth saying, because two of the five sources are guesses. */
function noteOnDate(medium: Medium, t: Translate): string | undefined {
  if (!medium.taken_at_source) return undefined

  const source = t(`media.info.source.${medium.taken_at_source}`)
  return medium.date_is_estimated ? `${source} · ${t('media.estimated')}` : source
}
