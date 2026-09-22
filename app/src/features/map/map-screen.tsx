import 'maplibre-gl/dist/maplibre-gl.css'

import { useNavigate } from '@tanstack/react-router'
import { Map as MapLibre, Marker, NavigationControl, setWorkerUrl } from 'maplibre-gl'
// MapLibre draws in a worker it loads from its own file, which a bundle does not carry along
// by itself: Vite builds it into one file here and MapLibre is told where it lies.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { AppShell } from '@/components/layout/app-shell'
import { ScrollContainerProvider } from '@/components/layout/scroll-container'
import { Symbol } from '@/components/muninn/symbol'
import { plainStyle } from '@/features/map/map-style'
import {
  type Bounds,
  type Cluster,
  useAreaMedia,
  useClusters,
  useMapStyle,
  type View,
} from '@/features/map/use-map'
import { MediaGrid } from '@/features/media/media-grid'
import { useMediaViewer } from '@/features/media/use-media-viewer'
import { useSearchAbilities } from '@/features/search/use-search'
import { useSocialUpdates } from '@/features/social/use-social'
import { useDark } from '@/hooks/use-dark'
import { useMediaQuery, WIDE_QUERY } from '@/hooks/use-media-query'

setWorkerUrl(workerUrl)

const VIEW_KEY = 'muninn.map.view'
/** Germany in the middle, most of Europe around it. */
const FIRST_VIEW = { center: [10.4, 51.2] as [number, number], zoom: 4 }
/** Beyond this a cluster is not zoomed into any more: it opens as a list. */
const LIST_FROM_ZOOM = 16
/** Web Mercator's own limit; the server leaves points beyond it off. */
const MERCATOR_LIMIT = 85

function storedView(): { center: [number, number]; zoom: number } {
  try {
    const raw = localStorage.getItem(VIEW_KEY)
    if (raw) {
      const view = JSON.parse(raw) as { center: [number, number]; zoom: number }
      if (Array.isArray(view.center) && typeof view.zoom === 'number') return view
    }
  } catch {
    // Nothing stored, or storage blocked: start from the first view.
  }
  return FIRST_VIEW
}

function storeView(map: MapLibre): void {
  try {
    const center = map.getCenter()
    localStorage.setItem(
      VIEW_KEY,
      JSON.stringify({ center: [center.lng, center.lat], zoom: map.getZoom() }),
    )
  } catch {
    // Only a convenience.
  }
}

/** The visible part, a little generous, rounded so that small moves ask the same question. */
function viewOf(map: MapLibre): View {
  const bounds = map.getBounds()
  const down = (value: number) => Math.floor(value * 100) / 100
  const up = (value: number) => Math.ceil(value * 100) / 100
  return {
    west: Math.max(-180, down(bounds.getWest())),
    south: Math.max(-MERCATOR_LIMIT, down(bounds.getSouth())),
    east: Math.min(180, up(bounds.getEast())),
    north: Math.min(MERCATOR_LIMIT, up(bounds.getNorth())),
    zoom: Math.floor(map.getZoom()),
  }
}

/** The database keeps a cluster's box in single precision; a margin keeps its edge points in. */
function padded(bounds: Bounds): Bounds {
  const margin = 0.0005
  return {
    west: Math.max(-180, bounds.west - margin),
    south: Math.max(-90, bounds.south - margin),
    east: Math.min(180, bounds.east + margin),
    north: Math.min(90, bounds.north + margin),
  }
}

interface Chosen {
  bounds: Bounds
  count: number
  /** A single picture opens straight away; a group shows as a list first. */
  list: boolean
}

/**
 * Midgard: every medium with a place, as round thumbnails on the map. Close ones gather
 * into one circle with a count; tapping zooms in until they part, and where they do not part
 * any more - the same spot, a whole afternoon - the circle opens as a list.
 */
export function MapScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const isWide = useMediaQuery(WIDE_QUERY)
  const dark = useDark()
  const style = useMapStyle(dark)
  const element = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<MapLibre | null>(null)
  const [view, setView] = useState<View | null>(null)
  const [chosen, setChosen] = useState<Chosen | null>(null)
  const [current, setCurrent] = useState<string | undefined>()
  const [panel, setPanel] = useState<HTMLElement | null>(null)

  const clusters = useClusters(view)
  const area = useAreaMedia(chosen?.bounds ?? null)
  useSocialUpdates()

  const abilities = useSearchAbilities()
  const pictures = abilities.data?.pictures ?? false
  const viewer = useMediaViewer(area.media, {
    // The viewer builds its buttons when it opens, so it waits until "Ähnliche Bilder" is decided.
    current: abilities.isPending ? undefined : current,
    onCurrentChange: setCurrent,
    // Nothing to compare without a picture model.
    onSimilar: pictures
      ? (mediaId: string) => {
          void navigate({ to: '/search', search: { similar: mediaId } })
        }
      : undefined,
    social: true,
  })

  useEffect(() => {
    if (element.current === null) return
    const created = new MapLibre({
      container: element.current,
      style: plainStyle(document.documentElement.classList.contains('dark')),
      ...storedView(),
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    })
    created.touchZoomRotate.disableRotation()
    created.addControl(new NavigationControl({ showCompass: false }), 'top-right')
    const update = () => {
      setView(viewOf(created))
      storeView(created)
    }
    created.on('load', update)
    created.on('moveend', update)
    setMap(created)
    return () => {
      created.remove()
      setMap(null)
    }
  }, [])

  useEffect(() => {
    map?.setStyle(style.data ?? plainStyle(dark))
  }, [map, dark, style.data])

  const choose = useCallback(
    (cluster: Cluster) => {
      if (map === null) return
      const { west, south, east, north } = cluster.bounds
      const spread = east - west > 0.0001 || north - south > 0.0001
      if (cluster.count > 1 && spread && map.getZoom() < LIST_FROM_ZOOM) {
        map.fitBounds(
          [
            [west, south],
            [east, north],
          ],
          { padding: 96, maxZoom: LIST_FROM_ZOOM + 1 },
        )
        return
      }
      const single = cluster.count === 1
      setChosen({ bounds: padded(cluster.bounds), count: cluster.count, list: !single })
      if (single) setCurrent(cluster.cover_id)
    },
    [map],
  )

  useEffect(() => {
    if (map === null) return
    const markers = (clusters.data ?? []).map((cluster) =>
      new Marker({
        element: markerOf(cluster, t('map.cluster', { count: cluster.count }), choose),
      })
        .setLngLat([cluster.longitude, cluster.latitude])
        .addTo(map),
    )
    return () => {
      for (const marker of markers) marker.remove()
    }
  }, [map, clusters.data, choose, t])

  const listed = chosen?.list === true

  return (
    <AppShell title={t('nav.map')} active="map" fill>
      {/* MapLibre's stylesheet makes its element position: relative, so it cannot place
          itself; the frame around it does, and the map fills the frame. */}
      <div className="absolute inset-0">
        <div ref={element} className="size-full" aria-label={t('map.label')} role="region" />
      </div>

      {style.isError && (
        <p className="absolute left-3 right-3 top-3 z-10 mx-auto flex max-w-md items-start gap-2 rounded-md border border-hairline/10 bg-card/95 px-3 py-2 text-base text-muted-foreground shadow-lg md:right-auto">
          <Symbol name="info" size={18} className="mt-px shrink-0" />
          {t('map.offline')}
        </p>
      )}

      {listed && (
        <section
          aria-label={t('map.here', { count: chosen.count })}
          className={
            isWide
              ? 'absolute bottom-4 right-4 top-4 z-10 flex w-[380px] flex-col rounded-lg border border-hairline/10 bg-card/95 shadow-2xl backdrop-blur-nav'
              : 'absolute inset-x-0 bottom-[calc(64px+env(safe-area-inset-bottom))] z-10 flex max-h-[55%] flex-col rounded-t-xl border-t border-hairline/10 bg-card/95 shadow-2xl backdrop-blur-nav'
          }
        >
          <header className="flex items-center justify-between gap-3 px-4 py-3">
            <h2 className="text-md font-semibold text-foreground">
              {t('map.here', { count: chosen.count })}
            </h2>
            <button
              type="button"
              aria-label={t('common.close')}
              className="grid size-8 place-items-center rounded-full text-muted-foreground hover:bg-secondary"
              onClick={() => {
                setChosen(null)
              }}
            >
              <Symbol name="close" size={20} />
            </button>
          </header>
          <div ref={setPanel} className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
            <ScrollContainerProvider container={panel}>
              <MediaGrid
                media={area.media}
                columns={3}
                onOpen={(index) => {
                  setCurrent(area.media[index]?.id)
                }}
                onEndReached={() => {
                  if (area.hasNextPage && !area.isFetchingNextPage) void area.fetchNextPage()
                }}
              />
            </ScrollContainerProvider>
          </div>
        </section>
      )}
      {viewer.panel}
    </AppShell>
  )
}

/** A round thumbnail on the map, with the count on it when it stands for several. */
function markerOf(
  cluster: Cluster,
  label: string,
  onChoose: (cluster: Cluster) => void,
): HTMLElement {
  const size = cluster.count === 1 ? 44 : cluster.count < 10 ? 52 : cluster.count < 100 ? 58 : 64
  const button = document.createElement('button')
  button.type = 'button'
  button.setAttribute('aria-label', label)
  button.className =
    'relative block rounded-full border-2 border-white bg-secondary shadow-[0_4px_14px_rgba(0,0,0,0.45)] transition-transform hover:z-10 hover:scale-110 focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent'
  button.style.width = `${size}px`
  button.style.height = `${size}px`
  if (cluster.cover_thumb) {
    const image = document.createElement('img')
    image.src = cluster.cover_thumb
    image.alt = ''
    image.loading = 'lazy'
    image.className = 'size-full rounded-full object-cover'
    button.append(image)
  }
  if (cluster.count > 1) {
    const badge = document.createElement('span')
    badge.textContent =
      cluster.count > 999 ? `${Math.floor(cluster.count / 1000)}k` : String(cluster.count)
    badge.className =
      'absolute -right-1.5 -top-1.5 min-w-6 rounded-full bg-accent px-1.5 py-0.5 text-center text-xs font-semibold leading-4 text-accent-foreground shadow'
    button.append(badge)
  }
  button.addEventListener('click', (event) => {
    event.stopPropagation()
    onChoose(cluster)
  })
  return button
}
