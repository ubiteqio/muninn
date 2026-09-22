import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api, unwrap } from '@/api/client'
import { Symbol } from '@/components/muninn/symbol'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { placeContext } from '@/features/map/place-name'

function useAlbumPlace(albumId: string) {
  return useQuery({
    queryKey: ['albums', albumId, 'one'],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/albums/{album_id}', { params: { path: { album_id: albumId } } }),
      ),
    select: (album) => album.place ?? null,
  })
}

/** What was typed, a moment after the typing stopped: one request per pause, not per key. */
function useSettled(value: string, delay = 200): string {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => {
      setSettled(value)
    }, delay)
    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])
  return settled
}

function usePlaceSuggestions(words: string) {
  const typed = useSettled(words.trim())
  return useQuery({
    queryKey: ['places', typed],
    enabled: typed.length >= 2,
    staleTime: Infinity,
    queryFn: async () => {
      const found = await unwrap(
        await api.GET('/api/v1/places', { params: { query: { q: typed, limit: 8 } } }),
      )
      return found.items
    },
  })
}

/**
 * Where an album was taken, for its photos without GPS - scans, old cameras. They then stand
 * there on the map and are found by the place, marked as estimated.
 */
export function AlbumPlace({ albumId }: { albumId: string }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const current = useAlbumPlace(albumId)
  const [open, setOpen] = useState(false)
  const [words, setWords] = useState('')
  const suggestions = usePlaceSuggestions(words)

  const choose = useMutation({
    mutationFn: async (placeId: number | null) =>
      unwrap(
        await api.PUT('/api/v1/albums/{album_id}/place', {
          params: { path: { album_id: albumId } },
          body: { place_id: placeId },
        }),
      ),
    onSuccess: async () => {
      setOpen(false)
      setWords('')
      // The album, its media's info panels and the map all show it.
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['albums', albumId] }),
        queryClient.invalidateQueries({ queryKey: ['media'] }),
      ])
    },
  })

  const place = current.data ?? null

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" title={t('albums.place.title')}>
          <Symbol name="map" size={20} />
          <span className="max-w-[160px] truncate">
            {place ? place.name : t('albums.place.set')}
          </span>
        </Button>
      </DialogTrigger>

      <DialogContent closeLabel={t('common.close')}>
        <DialogTitle>{t('albums.place.title')}</DialogTitle>
        <DialogDescription>{t('albums.place.description')}</DialogDescription>

        {place && (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-hairline/10 bg-secondary/40 px-3 py-2.5">
            <div className="min-w-0">
              <p className="truncate text-md font-medium text-foreground">{place.name}</p>
              <p className="truncate text-sm text-muted-foreground">{placeContext(place)}</p>
            </div>
            <Button
              variant="outline"
              disabled={choose.isPending}
              onClick={() => {
                choose.mutate(null)
              }}
            >
              {t('albums.place.remove')}
            </Button>
          </div>
        )}

        <Input
          className="mt-4"
          autoFocus
          value={words}
          placeholder={t('albums.place.search')}
          aria-label={t('albums.place.search')}
          onChange={(event) => {
            setWords(event.target.value)
          }}
        />

        <ul className="mt-2 max-h-72 overflow-y-auto" aria-label={t('albums.place.suggestions')}>
          {(suggestions.data ?? []).map((suggestion) => (
            <li key={suggestion.id}>
              <button
                type="button"
                disabled={choose.isPending}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left hover:bg-secondary/60 disabled:opacity-50"
                onClick={() => {
                  choose.mutate(suggestion.id)
                }}
              >
                <Symbol name="map" size={18} className="shrink-0 text-muted-foreground" />
                <span className="min-w-0">
                  <span className="block truncate text-md text-foreground">{suggestion.name}</span>
                  <span className="block truncate text-sm text-muted-foreground">
                    {placeContext(suggestion)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
        {suggestions.isSuccess && suggestions.data.length === 0 && (
          <p className="mt-2 px-3 text-base text-muted-foreground">{t('albums.place.nothing')}</p>
        )}
        {choose.isError && (
          <p className="mt-2 text-base text-destructive">{t('auth.error.unreachable')}</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
