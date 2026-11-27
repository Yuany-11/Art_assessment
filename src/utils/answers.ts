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
    size: Number(row.size ?? 0),
    captureMode:
      row.captureMode === 'camera' || row.captureMode === 'album' || row.captureMode === 'file'
        ? row.captureMode
        : undefined
  }
}

/** 美术作品多图；没有 files 时回退到主文件。 */
export function answerFiles(value: unknown): AnswerFile[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return []
  const row = value as Record<string, unknown>
  if (Array.isArray(row.files)) {
    const files = row.files
      .map((item) => answerFile(item))
      .filter((item): item is AnswerFile => item !== null)
    if (files.length) return files
  }
  const file = answerFile(value)
  return file ? [file] : []
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
    const row = value as Record<string, unknown>
    const file = answerFile(value)
    if (file) return file.name
    // 美术多图：至少显示图片数量，不把 files/values 这类字段名直接暴露给学生。
    if (Array.isArray(row.files) && row.files.length) {
      const names = row.files
        .map((item) => answerFile(item)?.name)
        .filter((name): name is string => Boolean(name))
      return names.length ? names.join('、') : `已上传 ${row.files.length} 张图片`
    }
    if (typeof row.text === 'string') return row.text.trim() || '未作答'
    if (Array.isArray(row.values)) {
      const list = row.values.map((item) => String(item ?? '').trim()).filter(Boolean)
      // 填空题/多选题只展示答案内容，不展示 JSON 字段名。
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
