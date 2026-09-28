import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Medium } from '@/features/albums/use-albums'

const native = vi.hoisted(() => ({ on: true, platform: 'ios' }))
const plugins = vi.hoisted(() => ({
  download: vi.fn(),
  share: vi.fn(),
  savePhoto: vi.fn(),
  saveVideo: vi.fn(),
  createAlbum: vi.fn(),
  downloadOriginal: vi.fn(),
}))

vi.mock('@/platform/server', () => ({ isNative: () => native.on }))
vi.mock('@/features/media/original', () => ({ downloadOriginal: plugins.downloadOriginal }))
vi.mock('@capacitor/core', () => ({ Capacitor: { getPlatform: () => native.platform } }))
vi.mock('@capacitor/filesystem', () => ({
  Directory: { Cache: 'CACHE' },
  Filesystem: {
    rmdir: vi.fn().mockResolvedValue(undefined),
    mkdir: vi.fn().mockResolvedValue(undefined),
    getUri: vi.fn(({ path }: { path: string }) => Promise.resolve({ uri: `file:///cache/${path}` })),
  },
}))
vi.mock('@capacitor/file-transfer', () => ({ FileTransfer: { downloadFile: plugins.download } }))
vi.mock('@capacitor/share', () => ({ Share: { share: plugins.share } }))
vi.mock('@capacitor-community/media', () => ({
  Media: {
    savePhoto: plugins.savePhoto,
    saveVideo: plugins.saveVideo,
    createAlbum: plugins.createAlbum,
    getAlbumsPath: () => Promise.resolve({ path: '/storage/media' }),
  },
}))

const { fileFor, PhotosDenied, saveMedium, shareMedium } = await import(
  '@/features/media/hand-over'
)

function aMedium(kind: 'image' | 'video', filename: string): Medium {
  return {
    id: 'medium-1',
    kind,
    origin: { filename },
    urls: {
      preview: 'https://nas/media/medium-1/preview?token=a',
      original: 'https://nas/media/medium-1/original?token=a',
      video: kind === 'video' ? 'https://nas/media/medium-1/video?token=a' : null,
    },
  } as unknown as Medium
}

beforeEach(() => {
  native.on = true
  native.platform = 'ios'
  for (const mock of Object.values(plugins)) mock.mockReset().mockResolvedValue({})
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('which file is handed over', () => {
  it('is the original of a picture', () => {
    expect(fileFor(aMedium('image', 'Strand.HEIC'))).toEqual({
      url: 'https://nas/media/medium-1/original?token=a',
      filename: 'Strand.HEIC',
    })
  })

  it('is the original of a video a phone plays', () => {
    expect(fileFor(aMedium('video', 'Geburtstag.MOV')).filename).toBe('Geburtstag.MOV')
  })

  it('is the MP4 Muninn made of a video from an old camera', () => {
    expect(fileFor(aMedium('video', 'Hochzeit.avi'))).toEqual({
      url: 'https://nas/media/medium-1/video?token=a',
      filename: 'Hochzeit.mp4',
    })
  })
})

describe('saving into the photos', () => {
  it('loads the file under its own name and hands it to the photo library', async () => {
    await expect(saveMedium(aMedium('video', 'Geburtstag.mp4'))).resolves.toBe('saved')

    expect(plugins.download).toHaveBeenCalledWith({
      url: 'https://nas/media/medium-1/original?token=a',
      path: 'file:///cache/handed-over/Geburtstag.mp4',
    })
    expect(plugins.saveVideo).toHaveBeenCalledWith({
      path: 'file:///cache/handed-over/Geburtstag.mp4',
    })
  })

  it('puts it into an album of its own on Android, which will not save without one', async () => {
    native.platform = 'android'

    await saveMedium(aMedium('image', 'Strand.jpg'))

    expect(plugins.createAlbum).toHaveBeenCalledWith({ name: 'Muninn' })
    expect(plugins.savePhoto).toHaveBeenCalledWith({
      path: 'file:///cache/handed-over/Strand.jpg',
      albumIdentifier: '/storage/media/Muninn',
    })
  })

  it('saves the large JPEG of a picture the library will not take', async () => {
    plugins.savePhoto.mockRejectedValueOnce(new Error('Unable to save image to album'))

    await expect(saveMedium(aMedium('image', 'Kirche.CR2'))).resolves.toBe('saved')

    expect(plugins.savePhoto).toHaveBeenLastCalledWith({
      path: 'file:///cache/handed-over/Kirche.jpg',
    })
  })

  it('says so when the photo library is closed to it', async () => {
    plugins.savePhoto.mockRejectedValueOnce(
      Object.assign(new Error('Access to photos not allowed by user'), { code: 'accessDenied' }),
    )

    await expect(saveMedium(aMedium('image', 'Strand.jpg'))).rejects.toBeInstanceOf(PhotosDenied)
  })

  it('downloads the original in a browser, which has no photo library', async () => {
    native.on = false

    await expect(saveMedium(aMedium('image', 'Strand.jpg'))).resolves.toBe('downloaded')

    expect(plugins.downloadOriginal).toHaveBeenCalledOnce()
    expect(plugins.savePhoto).not.toHaveBeenCalled()
  })
})

describe('sharing', () => {
  it('hands the share sheet the file, not a link', async () => {
    await expect(shareMedium(aMedium('image', 'Strand.jpg'))).resolves.toBe('shared')

    expect(plugins.share).toHaveBeenCalledWith({
      files: ['file:///cache/handed-over/Strand.jpg'],
    })
  })

  it('takes a closed share sheet for a change of mind, not a failure', async () => {
    plugins.share.mockRejectedValueOnce(new Error('Share canceled'))

    await expect(shareMedium(aMedium('image', 'Strand.jpg'))).resolves.toBe('cancelled')
  })

  it('shares the file itself from a browser too', async () => {
    native.on = false
    const shared = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { share: shared })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('jpeg', { headers: { 'Content-Type': 'image/jpeg' } })),
    )

    await shareMedium(aMedium('image', 'Strand.jpg'))

    const [[{ files }]] = shared.mock.calls as [[{ files: File[] }]]
    expect(files[0]?.name).toBe('Strand.jpg')
    expect(files[0]?.type).toBe('image/jpeg')
    expect(plugins.share).not.toHaveBeenCalled()
  })
})
