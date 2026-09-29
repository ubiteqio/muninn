import { Capacitor } from '@capacitor/core'
import { FileTransfer } from '@capacitor/file-transfer'
import { Directory, Filesystem } from '@capacitor/filesystem'
import { Share } from '@capacitor/share'
import { Media } from '@capacitor-community/media'

import type { Medium } from '@/features/albums/use-albums'
import { downloadOriginal } from '@/features/media/original'
import { isNative } from '@/platform/server'

/**
 * Handing a medium over: into the phone's photos, or to another app through the share sheet.
 *
 * What goes is the file itself, never a link: a link to Muninn means nothing to somebody in a
 * WhatsApp chat, and the address inside the native app points at the phone.
 */

/** A file as it leaves Muninn: where it is loaded from, and what it is called on arrival. */
export interface Handed {
  url: string
  filename: string
}

/** Videos a phone plays, and its photo library takes, as they are. */
const PLAYABLE = new Set(['mp4', 'm4v', 'mov'])

/** Where the native app keeps a file for as long as it is being handed over. */
const FOLDER = 'handed-over'

/** The album saved media go into on Android, which wants one; iOS puts them in the library. */
const ALBUM = 'Muninn'

/** The photo library said no; the user can change that in the settings, and should be told. */
export class PhotosDenied extends Error {}

/**
 * The file that is handed over: the original, as good as it gets.
 *
 * Except a video in a format of old cameras - AVI, MTS and their like - which no phone plays and
 * no photo library takes. That goes as the MP4 Muninn made of it for playing.
 */
export function fileFor(medium: Medium): Handed {
  const original = { url: medium.urls.original, filename: medium.origin.filename }
  if (medium.kind !== 'video' || medium.urls.video === null) return original
  if (PLAYABLE.has(extensionOf(medium.origin.filename))) return original

  return { url: medium.urls.video, filename: `${stemOf(medium.origin.filename)}.mp4` }
}

/** The large JPEG, for a picture in a format the photo library does not take. */
export function previewFor(medium: Medium): Handed | null {
  if (medium.kind !== 'image' || medium.urls.preview === null) return null
  return { url: medium.urls.preview, filename: `${stemOf(medium.origin.filename)}.jpg` }
}

/** Whether this device can share a file at all - every phone app can, a browser may not. */
export function canShareFiles(): boolean {
  if (isNative()) return true
  if (typeof navigator === 'undefined' || typeof navigator.canShare !== 'function') return false
  try {
    return navigator.canShare({ files: [new File([''], 'a.jpg', { type: 'image/jpeg' })] })
  } catch {
    return false
  }
}

/**
 * Into the phone's photos. A browser has no photo library, so there it is a download.
 */
export async function saveMedium(medium: Medium): Promise<'saved' | 'downloaded'> {
  if (!isNative()) {
    downloadOriginal(medium)
    return 'downloaded'
  }

  try {
    await intoPhotos(medium.kind, await fetchToCache(fileFor(medium)))
  } catch (error) {
    if (codeOf(error) === 'accessDenied') throw new PhotosDenied()
    // A picture the library will not take - a RAW of a rare camera - still goes, as the JPEG.
    const preview = previewFor(medium)
    if (preview === null) throw error
    await intoPhotos('image', await fetchToCache(preview))
  }
  return 'saved'
}

/**
 * Through the share sheet, to whatever app the user picks. Closing the sheet is no failure: it
 * is somebody who changed their mind.
 */
export async function shareMedium(medium: Medium): Promise<'shared' | 'cancelled'> {
  const file = fileFor(medium)
  try {
    if (isNative()) {
      await Share.share({ files: [await fetchToCache(file)] })
    } else {
      const response = await fetch(file.url)
      if (!response.ok) throw new Error(`The file could not be loaded: ${String(response.status)}`)
      const blob = await response.blob()
      await navigator.share({ files: [new File([blob], file.filename, { type: blob.type })] })
    }
  } catch (error) {
    if (isCancelled(error)) return 'cancelled'
    throw error
  }
  return 'shared'
}

/**
 * Load the file into the app's cache, under its own name, and say where it lies.
 *
 * What was handed over last time goes first. Not straight after the handing over: an Android
 * app that was shared a file may only read it once the share sheet has long closed.
 */
async function fetchToCache(file: Handed): Promise<string> {
  await Filesystem.rmdir({ path: FOLDER, directory: Directory.Cache, recursive: true }).catch(
    () => undefined,
  )
  await Filesystem.mkdir({ path: FOLDER, directory: Directory.Cache, recursive: true })
  const { uri } = await Filesystem.getUri({
    path: `${FOLDER}/${safeName(file.filename)}`,
    directory: Directory.Cache,
  })
  await FileTransfer.downloadFile({ url: file.url, path: uri })
  return uri
}

async function intoPhotos(kind: Medium['kind'], path: string): Promise<void> {
  const options = { path, ...(await album()) }
  if (kind === 'video') await Media.saveVideo(options)
  else await Media.savePhoto(options)
}

/** Android saves only into an album, and makes one on the first save. */
async function album(): Promise<{ albumIdentifier?: string }> {
  if (Capacitor.getPlatform() !== 'android') return {}
  const { path } = await Media.getAlbumsPath()
  // It says no when the album is there already, which is exactly what is wanted.
  await Media.createAlbum({ name: ALBUM }).catch(() => undefined)
  return { albumIdentifier: `${path}/${ALBUM}` }
}

function isCancelled(error: unknown): boolean {
  if (error instanceof DOMException && error.name === 'AbortError') return true
  return error instanceof Error && /cancel/i.test(error.message)
}

function codeOf(error: unknown): string | undefined {
  if (typeof error !== 'object' || error === null || !('code' in error)) return undefined
  return typeof error.code === 'string' ? error.code : undefined
}

function extensionOf(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot === -1 ? '' : filename.slice(dot + 1).toLowerCase()
}

function stemOf(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot <= 0 ? filename : filename.slice(0, dot)
}

/** A name from the NAS may hold what a path must not. */
function safeName(filename: string): string {
  return filename.replace(/[/\\:]/g, '_') || 'medium'
}
