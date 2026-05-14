<template>
  <div v-if="!charts" class="text-xs text-muted-foreground">
    No charts available for this version.
  </div>
  <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <!-- Training curve -->
    <div v-if="charts.training_curve?.length">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
        Training curve
      </div>
      <svg :viewBox="`0 0 ${CHART_W} ${CHART_H}`" class="w-full">
        <!-- gridlines -->
        <line
          v-for="g in [0.25, 0.5, 0.75]"
          :key="g"
          :x1="MARGIN_L"
          :x2="CHART_W - MARGIN_R"
          :y1="yScale(g)"
          :y2="yScale(g)"
          stroke="currentColor"
          class="text-border"
          stroke-dasharray="2,2"
          opacity="0.5"
        />
        <!-- axes -->
        <line :x1="MARGIN_L" :y1="MARGIN_T" :x2="MARGIN_L" :y2="CHART_H - MARGIN_B" class="stroke-border" />
        <line :x1="MARGIN_L" :y1="CHART_H - MARGIN_B" :x2="CHART_W - MARGIN_R" :y2="CHART_H - MARGIN_B" class="stroke-border" />
        <!-- y-axis labels -->
        <text v-for="g in [0, 0.5, 1]" :key="g" :x="MARGIN_L - 4" :y="yScale(g) + 3" text-anchor="end" class="fill-muted-foreground text-[9px] font-mono">
          {{ g.toFixed(1) }}
        </text>
        <!-- loss line -->
        <polyline :points="lossPoints" fill="none" stroke="#ef4444" stroke-width="1.5" />
        <!-- val_metric line -->
        <polyline :points="valPoints" fill="none" stroke="#3b82f6" stroke-width="1.5" />
        <!-- legend -->
        <g :transform="`translate(${CHART_W - MARGIN_R - 80}, ${MARGIN_T})`">
          <rect width="80" height="34" fill="white" opacity="0.85" class="fill-card" />
          <line x1="6" y1="9" x2="18" y2="9" stroke="#ef4444" stroke-width="1.5" />
          <text x="22" y="12" class="fill-foreground text-[9px]">loss</text>
          <line x1="6" y1="22" x2="18" y2="22" stroke="#3b82f6" stroke-width="1.5" />
          <text x="22" y="25" class="fill-foreground text-[9px]">val metric</text>
        </g>
        <!-- x-axis epoch labels -->
        <text :x="MARGIN_L" :y="CHART_H - 4" text-anchor="start" class="fill-muted-foreground text-[9px] font-mono">
          epoch {{ xMin }}
        </text>
        <text :x="CHART_W - MARGIN_R" :y="CHART_H - 4" text-anchor="end" class="fill-muted-foreground text-[9px] font-mono">
          {{ xMax }}
        </text>
      </svg>
    </div>

    <!-- Confusion matrix -->
    <div v-if="charts.confusion_matrix">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
        Confusion matrix
      </div>
      <div class="inline-block">
        <table class="text-xs border-collapse">
          <thead>
            <tr>
              <th class="text-right pr-2 text-muted-foreground font-normal align-bottom">true ↓</th>
              <th
                v-for="label in charts.confusion_matrix.labels"
                :key="`top-${label}`"
                class="px-2 pb-1 text-muted-foreground font-normal text-[10px] -rotate-45 origin-bottom-left h-12 align-bottom"
              >
                {{ label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in charts.confusion_matrix.values" :key="i">
              <td class="text-right pr-2 text-muted-foreground text-[10px]">
                {{ charts.confusion_matrix.labels[i] }}
              </td>
              <td
                v-for="(val, j) in row"
                :key="j"
                class="w-12 h-10 text-center border border-border font-mono"
                :style="cellStyle(val, i, j, charts.confusion_matrix.values)"
              >
                {{ val }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Per-class metric (alternative to confusion matrix, used by detection models) -->
    <div v-if="charts.per_class?.length">
      <div class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2">
        Per-class metric
      </div>
      <div class="space-y-1.5">
        <div v-for="row in charts.per_class" :key="row.label" class="flex items-center gap-2 text-xs">
          <span class="w-20 text-muted-foreground">{{ row.label }}</span>
          <div class="flex-1 h-3 bg-muted rounded-sm overflow-hidden max-w-[200px]">
            <div
              class="h-full bg-primary"
              :style="{ width: (row.value * 100) + '%' }"
            />
          </div>
          <span class="font-mono">{{ row.value.toFixed(2) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface ConfusionMatrix {
  labels: string[]
  values: number[][]
}
interface CurvePoint {
  epoch: number
  loss: number
  val_metric: number
}
interface PerClass {
  label: string
  value: number
}
interface Charts {
  training_curve?: CurvePoint[]
  confusion_matrix?: ConfusionMatrix
  per_class?: PerClass[]
}

const props = defineProps<{ charts: Charts | null | undefined }>()

const CHART_W = 320
const CHART_H = 160
const MARGIN_L = 22
const MARGIN_R = 8
const MARGIN_T = 8
const MARGIN_B = 18

const xMin = computed(() => props.charts?.training_curve?.[0]?.epoch ?? 0)
const xMax = computed(() => {
  const curve = props.charts?.training_curve
  if (!curve?.length) return 1
  return curve[curve.length - 1].epoch
})

function xScale(epoch: number): number {
  const range = xMax.value - xMin.value || 1
  return MARGIN_L + ((epoch - xMin.value) / range) * (CHART_W - MARGIN_L - MARGIN_R)
}
function yScale(value: number): number {
  // value range 0..1, inverted for SVG
  return MARGIN_T + (1 - value) * (CHART_H - MARGIN_T - MARGIN_B)
}

const lossPoints = computed(() => {
  const curve = props.charts?.training_curve
  if (!curve?.length) return ''
  return curve.map((p) => `${xScale(p.epoch)},${yScale(Math.min(1, p.loss))}`).join(' ')
})

const valPoints = computed(() => {
  const curve = props.charts?.training_curve
  if (!curve?.length) return ''
  return curve.map((p) => `${xScale(p.epoch)},${yScale(p.val_metric)}`).join(' ')
})

function cellStyle(value: number, rowIdx: number, colIdx: number, matrix: number[][]) {
  const rowSum = matrix[rowIdx].reduce((a, b) => a + b, 0) || 1
  const ratio = value / rowSum
  // Diagonal correct predictions in green; off-diagonal in red, intensity by ratio
  const isDiag = rowIdx === colIdx
  const hue = isDiag ? '142 76% 45%' : '0 84% 60%'
  return {
    backgroundColor: `hsl(${hue} / ${Math.min(0.6, ratio * 0.7)})`,
  }
}
</script>
