import { ref, type Ref } from 'vue'

export interface SourceImage {
  w: number
  h: number
  url: string | null
}

// Fullscreen zoom/pan over the selected detection's source image. State lives
// in viewBox units; the SVG <g> is translated then scaled, so the
// wheel-around-cursor math converts the cursor's client coords into viewBox
// coords before applying. Depends only on the reactive source-image size/url.
export function useImageZoom(sourceImage: Ref<SourceImage>) {
  const zoomDialog = ref<HTMLDialogElement | null>(null)
  const zoom = ref({ scale: 1, tx: 0, ty: 0 })
  const panning = ref(false)
  const panStart = ref({ x: 0, y: 0, tx: 0, ty: 0 })

  function openZoom() {
    if (!sourceImage.value.url || !sourceImage.value.w) return
    zoom.value = { scale: 1, tx: 0, ty: 0 }
    zoomDialog.value?.showModal()
  }

  function closeZoom() {
    zoomDialog.value?.close()
  }

  function onZoomClose() {
    panning.value = false
  }

  // Zoom toward the cursor: keep the source-image point under the cursor
  // fixed while the scale changes. Done by adjusting the translate so the
  // post-scale cursor location matches the pre-scale one.
  function onZoomWheel(e: WheelEvent) {
    const target = e.currentTarget as HTMLElement
    const rect = target.getBoundingClientRect()
    // Cursor in viewBox coords: the SVG fills the container and uses
    // preserveAspectRatio=meet, so map via the longest fitted side.
    const sx = sourceImage.value.w
    const sy = sourceImage.value.h
    const fit = Math.min(rect.width / sx, rect.height / sy)
    const offX = (rect.width - sx * fit) / 2
    const offY = (rect.height - sy * fit) / 2
    const vx = (e.clientX - rect.left - offX) / fit
    const vy = (e.clientY - rect.top - offY) / fit

    const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2
    const next = Math.max(1, Math.min(20, zoom.value.scale * factor))
    if (next === zoom.value.scale) return
    const k = next / zoom.value.scale
    zoom.value = {
      scale: next,
      tx: vx - k * (vx - zoom.value.tx),
      ty: vy - k * (vy - zoom.value.ty),
    }
  }

  function onPanStart(e: MouseEvent) {
    if (e.button !== 0) return
    panning.value = true
    panStart.value = {
      x: e.clientX,
      y: e.clientY,
      tx: zoom.value.tx,
      ty: zoom.value.ty,
    }
  }

  function onPanMove(e: MouseEvent) {
    if (!panning.value) return
    const target = e.currentTarget as HTMLElement
    const rect = target.getBoundingClientRect()
    const sx = sourceImage.value.w
    const sy = sourceImage.value.h
    const fit = Math.min(rect.width / sx, rect.height / sy)
    zoom.value = {
      ...zoom.value,
      tx: panStart.value.tx + (e.clientX - panStart.value.x) / fit,
      ty: panStart.value.ty + (e.clientY - panStart.value.y) / fit,
    }
  }

  function onPanEnd() {
    panning.value = false
  }

  return {
    zoomDialog,
    zoom,
    panning,
    openZoom,
    closeZoom,
    onZoomClose,
    onZoomWheel,
    onPanStart,
    onPanMove,
    onPanEnd,
  }
}
