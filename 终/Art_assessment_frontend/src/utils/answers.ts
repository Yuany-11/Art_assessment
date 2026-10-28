import type { AnswerFile } from '@/types'

export function answerFile(value: unknown): AnswerFile | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Record<string, unknown>
  if (typeof row.url !== 'string' || !row.url || row.fileId === undefined || row.fileId === null) return null
  return {
    fileId: Number(row.fileId),
    url: row.url,
    name: typeof row.name === 'string' ? row.name : '已上传文件',
    mimeType: typeof row.mimeType === 'string' ? row.mimeType : '',
    size: Number(row.size ?? 0)
  }
}

export function formatAnswer(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未作答'
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return value ? '正确' : '错误'
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) {
    const list = value.map((item) => formatAnswer(item)).filter((item) => item !== '未作答')
    return list.length ? list.join('、') : '未作答'
  }
  if (typeof value === 'object') {
    const file = answerFile(value)
    if (file) return file.name
    const row = value as Record<string, unknown>
    if (typeof row.text === 'string') return row.text || '未作答'
    if (Array.isArray(row.values)) {
      const list = row.values.map((item) => String(item ?? '').trim()).filter(Boolean)
      return list.length ? list.join('、') : '未作答'
    }
    if ('value' in row) return formatAnswer(row.value)
  }
  return '未作答'
}

export function isImageFile(file: AnswerFile) {
  return file.mimeType.startsWith('image/') || /\.(jpe?g|png|webp)$/i.test(file.name)
}

export function isAudioFile(file: AnswerFile) {
  return file.mimeType.startsWith('audio/') || /\.(mp3|wav|m4a|webm|ogg)$/i.test(file.name)
}
