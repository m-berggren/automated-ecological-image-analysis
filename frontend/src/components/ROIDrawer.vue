<template>
  <div class="overlay-backdrop" @keydown.esc="$emit('close')" tabindex="0">
    <div class="modal animate-fade-in">

      <!-- Header -->
      <div class="modal-header">
        <h2 class="font-display">Select Region of Interest</h2>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <!-- Instructions -->
      <div class="instructions-bar">
        <span><strong>Draw:</strong> Click and drag on the image</span>
        <span><strong>Resize:</strong> Drag the handles on the selection</span>
        <span><strong>Save:</strong> Click "Confirm ROI"</span>
        <span><strong>Close:</strong> Press Escape or click "Cancel"</span>
      </div>

      <!-- Canvas -->
      <div
        class="canvas-area"
        ref="canvasRef"
        @mousedown="onCanvasMouseDown"
      >
        <img
          :src="imageUrl"
          class="background-img"
          ref="imgRef"
          @load="onImageLoad"
          draggable="false"
        />

        <template v-if="hasSelection">
          <div class="selection-box" :style="selectionStyle">
            <span class="selection-label">
              {{ Math.round(roi.width) }} × {{ Math.round(roi.height) }}
            </span>
            <div
              v-for="handle in handles"
              :key="handle.cursor"
              class="handle"
              :style="handle.style"
              @mousedown.stop="startResize($event, handle.directions)"
            />
          </div>
        </template>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <div class="roi-info" v-if="hasSelection">
          <code>x: {{ Math.round(roi.x) }}, y: {{ Math.round(roi.y) }}, w: {{ Math.round(roi.width) }}, h: {{ Math.round(roi.height) }}</code>
        </div>
        <div class="roi-info muted" v-else>No region selected yet</div>

        <div class="actions">
          <button class="btn btn-secondary" @click="clearSelection">Clear</button>
          <button class="btn btn-cancel" @click="$emit('close')">Cancel</button>
          <button class="btn btn-confirm" :disabled="!hasSelection" @click="confirmRoi">
            Confirm ROI
          </button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  imageUrl: { type: String, required: true },
})
const emit = defineEmits(['close', 'confirm'])

const imgRef    = ref(null)
const canvasRef = ref(null)
const isDrawing  = ref(false)
const isResizing = ref(false)
const hasSelection = ref(false)
const roi = ref({ x: 0, y: 0, width: 0, height: 0 })
const naturalW = ref(1)
const naturalH = ref(1)
const dragStart    = ref({ x: 0, y: 0 })
const roiSnapshot  = ref(null)
const resizeDirs   = ref(null)

const onImageLoad = () => {
  naturalW.value = imgRef.value.naturalWidth
  naturalH.value = imgRef.value.naturalHeight
}

const imgPos = (e) => {
  const r = imgRef.value.getBoundingClientRect()
  return {
    x: Math.min(Math.max(e.clientX - r.left, 0), r.width),
    y: Math.min(Math.max(e.clientY - r.top,  0), r.height),
  }
}

const clampRoi = (r) => {
  const { width: iw, height: ih } = imgRef.value.getBoundingClientRect()
  const x = Math.min(Math.max(r.x, 0), iw - 1)
  const y = Math.min(Math.max(r.y, 0), ih - 1)
  const w = Math.min(Math.max(r.width,  1), iw - x)
  const h = Math.min(Math.max(r.height, 1), ih - y)
  return { x, y, width: w, height: h }
}

const onCanvasMouseDown = (e) => {
  if (e.target !== canvasRef.value && e.target !== imgRef.value) return
  hasSelection.value = false
  isDrawing.value    = true
  const p = imgPos(e)
  dragStart.value = p
  roi.value = { x: p.x, y: p.y, width: 0, height: 0 }
}

const startResize = (e, directions) => {
  isResizing.value  = true
  resizeDirs.value  = directions
  dragStart.value   = { x: e.clientX, y: e.clientY }
  roiSnapshot.value = { ...roi.value }
}

const onMouseMove = (e) => {
  if (isDrawing.value) {
    const p = imgPos(e)
    roi.value = clampRoi({
      x:      Math.min(p.x, dragStart.value.x),
      y:      Math.min(p.y, dragStart.value.y),
      width:  Math.abs(p.x - dragStart.value.x),
      height: Math.abs(p.y - dragStart.value.y),
    })
    hasSelection.value = true
  }

  if (isResizing.value) {
    const dx = e.clientX - dragStart.value.x
    const dy = e.clientY - dragStart.value.y
    const s  = roiSnapshot.value
    const d  = resizeDirs.value
    let { x, y, width, height } = s
    if (d.left)   { x = s.x + dx; width  = s.width  - dx }
    if (d.top)    { y = s.y + dy; height = s.height - dy }
    if (d.right)  { width  = s.width  + dx }
    if (d.bottom) { height = s.height + dy }
    roi.value = clampRoi({ x, y, width, height })
  }
}

const onMouseUp = () => {
  if (isDrawing.value && (roi.value.width < 5 || roi.value.height < 5)) {
    hasSelection.value = false
  }
  isDrawing.value  = false
  isResizing.value = false
}

const confirmRoi = () => {
  if (!hasSelection.value || !imgRef.value) return
  const { width: rw, height: rh } = imgRef.value.getBoundingClientRect()
  const sx = naturalW.value / rw
  const sy = naturalH.value / rh
  emit('confirm', {
    x:      Math.round(roi.value.x      * sx),
    y:      Math.round(roi.value.y      * sy),
    width:  Math.round(roi.value.width  * sx),
    height: Math.round(roi.value.height * sy),
  })
  emit('close')
}

const clearSelection = () => { hasSelection.value = false }

const selectionStyle = computed(() => ({
  left:   roi.value.x      + 'px',
  top:    roi.value.y      + 'px',
  width:  roi.value.width  + 'px',
  height: roi.value.height + 'px',
}))

const H = 'calc(50% - 5px)'
const handles = [
  { cursor: 'nw-resize', directions: { left: true,  top: true,  right: false, bottom: false }, style: { top: '-5px',    left: '-5px',  cursor: 'nw-resize' } },
  { cursor: 'ne-resize', directions: { left: false, top: true,  right: true,  bottom: false }, style: { top: '-5px',    right: '-5px', cursor: 'ne-resize' } },
  { cursor: 'sw-resize', directions: { left: true,  top: false, right: false, bottom: true  }, style: { bottom: '-5px', left: '-5px',  cursor: 'sw-resize' } },
  { cursor: 'se-resize', directions: { left: false, top: false, right: true,  bottom: true  }, style: { bottom: '-5px', right: '-5px', cursor: 'se-resize' } },
  { cursor: 'n-resize',  directions: { left: false, top: true,  right: false, bottom: false }, style: { top: '-5px',    left: H,       cursor: 'n-resize'  } },
  { cursor: 's-resize',  directions: { left: false, top: false, right: false, bottom: true  }, style: { bottom: '-5px', left: H,       cursor: 's-resize'  } },
  { cursor: 'w-resize',  directions: { left: true,  top: false, right: false, bottom: false }, style: { top: H,         left: '-5px',  cursor: 'w-resize'  } },
  { cursor: 'e-resize',  directions: { left: false, top: false, right: true,  bottom: false }, style: { top: H,         right: '-5px', cursor: 'e-resize'  } },
]

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup',   onMouseUp)
})
onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup',   onMouseUp)
})
</script>

<style scoped>
.overlay-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--color-foreground) 60%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  max-width: 90vw;
  max-height: 90vh;
  box-shadow:
    0 4px 6px -1px color-mix(in srgb, var(--color-foreground) 8%, transparent),
    0 20px 48px -8px color-mix(in srgb, var(--color-foreground) 16%, transparent);
}

/* ── Header ── */
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}

.modal-header h2 {
  color: var(--color-foreground);
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  letter-spacing: -0.01em;
}

.close-btn {
  background: none;
  border: 1px solid transparent;
  color: var(--color-muted-foreground);
  font-size: 16px;
  cursor: pointer;
  padding: 3px 8px;
  border-radius: calc(var(--radius) * 0.5);
  transition: color 0.15s, background 0.15s, border-color 0.15s;
  line-height: 1;
}
.close-btn:hover {
  color: var(--color-primary-foreground);
  background: var(--color-primary);
  border-color: var(--color-primary);
}

/* ── Instructions ── */
.instructions-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  padding: 10px 20px;
  background: var(--color-muted);
  border-bottom: 1px solid var(--color-border);
  font-size: 12px;
  color: var(--color-muted-foreground);
}
.instructions-bar strong {
  color: var(--color-primary);
  font-weight: 600;
}

/* ── Canvas ── */
.canvas-area {
  position: relative;
  overflow: auto;
  cursor: crosshair;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--color-foreground) 85%, transparent);
  user-select: none;
}

.background-img {
  max-width: 100%;
  max-height: 65vh;
  display: block;
  pointer-events: none;
}

/* ── Selection box ── */
.selection-box {
  position: absolute;
  border: 2px solid RED;
  background: color-mix(in srgb, RED 15%, transparent);
  box-sizing: border-box;
  pointer-events: none;
  animation: bbox-pulse 2s ease-in-out infinite;
}

.selection-label {
  position: absolute;
  top: -24px;
  left: 0;
  background: var(--color-accent);
  color: var(--color-eco-forest);
  font-size: 11px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: calc(var(--radius) * 0.4);
  white-space: nowrap;
  pointer-events: none;
  font-family: var(--font-sans-display);
}

/* ── Handles ── */
.handle {
  position: absolute;
  width: 10px;
  height: 10px;
  background: RED;
  border: 2px solid RED;
  border-radius: 2px;
  pointer-events: all;
  box-sizing: border-box;
  transition: background 0.15s, transform 0.15s;
}
.handle:hover {
  background: var(--color-accent);
  transform: scale(1.3);
}

/* ── Footer ── */
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  gap: 16px;
  flex-wrap: wrap;
}

.roi-info {
  font-family: monospace;
  font-size: 12px;
  color: var(--color-primary);
  background: var(--color-muted);
  padding: 4px 10px;
  border-radius: calc(var(--radius) * 0.5);
  border: 1px solid var(--color-border);
}
.roi-info.muted {
  color: var(--color-muted-foreground);
}

.actions { display: flex; gap: 8px; }

.btn {
  padding: 8px 16px;
  border-radius: calc(var(--radius) * 0.6);
  border: 1px solid transparent;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  font-family: var(--font-sans-display);
  transition: all 0.15s ease;
  letter-spacing: -0.01em;
}
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

.btn-secondary {
  background: var(--color-secondary);
  color: var(--color-secondary-foreground);
  border-color: var(--color-border);
}
.btn-secondary:hover:not(:disabled) {
  background: var(--color-muted);
  border-color: var(--color-eco-sage);
}

.btn-cancel {
  background: transparent;
  color: var(--color-muted-foreground);
  border-color: var(--color-border);
}
.btn-cancel:hover {
  background: var(--color-muted);
  color: var(--color-foreground);
}

.btn-confirm {
  background: var(--color-primary);
  color: var(--color-primary-foreground);
  border-color: var(--color-primary);
}
.btn-confirm:hover:not(:disabled) {
  background: var(--color-eco-forest);
  border-color: var(--color-eco-forest);
}
</style>