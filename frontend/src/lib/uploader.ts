import { reactive } from 'vue'
import { api } from '@/api'
import { UPLOAD_CONCURRENCY } from '@/lib/config'

export type UploadStatus = 'pending' | 'uploading' | 'done' | 'failed'

export interface UploadItem {
  id: string
  file: File
  status: UploadStatus
  progress: number
  error?: string
  imageId?: number
  imageUrl?: string
}

interface UploadResponse {
  id: number
  file_url: string | null
}

export interface UploadOptions {
  module: string
  purpose?: 'training' | 'inference'
  concurrency?: number
  /** Attach uploaded images to this Upload row (sent as `upload` form field). */
  uploadId?: number
}

export function createUploader(opts: UploadOptions) {
  const items = reactive<UploadItem[]>([])
  const concurrency = opts.concurrency ?? UPLOAD_CONCURRENCY
  let active = 0
  let counter = 0

  function enqueue(files: File[]) {
    for (const file of files) {
      items.push({
        id: `u${++counter}`,
        file,
        status: 'pending',
        progress: 0,
      })
    }
    pump()
  }

  function pump() {
    while (active < concurrency) {
      const next = items.find((i) => i.status === 'pending')
      if (!next) return
      next.status = 'uploading'
      active += 1
      void uploadOne(next).finally(() => {
        active -= 1
        pump()
      })
    }
  }

  async function uploadOne(item: UploadItem) {
    try {
      const fd = new FormData()
      fd.append('file', item.file)
      fd.append('module', opts.module)
      fd.append('purpose', opts.purpose ?? 'inference')
      if (opts.uploadId) fd.append('upload', String(opts.uploadId))
      const res = await api('/api/datasets/images/', { method: 'POST', body: fd })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(text || `HTTP ${res.status}`)
      }
      const data = (await res.json()) as UploadResponse
      item.imageId = data.id
      item.imageUrl = data.file_url ?? undefined
      item.status = 'done'
      item.progress = 100
    } catch (err) {
      item.status = 'failed'
      item.error = err instanceof Error ? err.message : String(err)
    }
  }

  function retry(id: string) {
    const item = items.find((i) => i.id === id)
    if (!item || item.status !== 'failed') return
    item.status = 'pending'
    item.error = undefined
    pump()
  }

  function remove(id: string) {
    const idx = items.findIndex((i) => i.id === id)
    if (idx >= 0) items.splice(idx, 1)
  }

  function clearDone() {
    for (let i = items.length - 1; i >= 0; i--) {
      if (items[i].status === 'done') items.splice(i, 1)
    }
  }

  return { items, enqueue, retry, remove, clearDone }
}
