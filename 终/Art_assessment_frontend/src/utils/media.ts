const AUDIO_EXTS = ['mp3', 'wav', 'm4a', 'webm', 'ogg']
const IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'webp']

function extOf(name: string): string {
  return name.includes('.') ? name.split('.').pop()?.toLowerCase() ?? '' : ''
}

export function isAudioFile(name: string, mimeType?: string | null): boolean {
  if (mimeType) return mimeType.startsWith('audio/')
  return AUDIO_EXTS.includes(extOf(name))
}

export function isImageFile(name: string, mimeType?: string | null): boolean {
  if (mimeType) return mimeType.startsWith('image/')
  return IMAGE_EXTS.includes(extOf(name))
}
