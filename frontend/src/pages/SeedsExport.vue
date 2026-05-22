<template>
  <PageHeader
    title="Export Results"
    subtitle="Download your final annotated images and CSV dataset"
  />

  <SeedsStepper current="export" :runId="route.params.id" />

  <div
    v-if="loading"
    class="flex-1 flex flex-col items-center justify-center p-12 text-muted-foreground"
  >
    <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mb-4"></div>
    Generating final annotated images and dataset...
  </div>

  <div v-else-if="loadError" class="flex-1 flex items-center justify-center text-sm text-red-600">
    {{ loadError }}
  </div>

  <div v-else class="flex-1 flex flex-col min-h-0 bg-background p-6 overflow-y-auto">
    <div class="max-w-7xl mx-auto w-full space-y-8">
      <section class="rounded-xl border border-border bg-surface overflow-hidden">
        <header
          class="px-6 py-4 border-b border-border flex items-center justify-between bg-muted/20"
        >
          <div>
            <h2 class="text-lg font-semibold">Dataset Preview</h2>
            <p class="text-xs text-muted-foreground mt-1">
              Final active seed counts and confidence metrics.
            </p>
          </div>
          <button
            @click="downloadCSV"
            class="px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-md hover:bg-primary/90 shadow-sm"
          >
            Download CSV
          </button>
        </header>

        <div class="overflow-x-auto">
          <table class="w-full text-sm text-left">
            <thead
              class="text-xs text-muted-foreground bg-muted/30 uppercase border-b border-border"
            >
              <tr>
                <th class="px-6 py-3 font-medium">Filename</th>
                <th class="px-6 py-3 font-medium">Species</th>
                <th class="px-6 py-3 font-medium">Calculated Active Seed Count</th>
                <th class="px-6 py-3 font-medium">Model Confidence</th>
                <th class="px-6 py-3 font-medium text-green-600">Corrected Active Seed Count</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-border">
              <tr v-for="row in exportData" :key="row.filename" class="hover:bg-muted/10">
                <td class="px-6 py-3 font-mono text-xs">{{ row.filename }}</td>
                <td class="px-6 py-3">{{ row.species }}</td>
                <td class="px-6 py-3">{{ row.calculated_active }}</td>
                <td class="px-6 py-3">{{ (row.confidence * 100).toFixed(1) }}%</td>
                <td class="px-6 py-3 font-bold text-green-600">{{ row.final_active }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="rounded-xl border border-border bg-surface overflow-hidden">
        <header
          class="px-6 py-4 border-b border-border flex items-center justify-between bg-muted/20"
        >
          <div>
            <h2 class="text-lg font-semibold">Annotated Images</h2>
            <p class="text-xs text-muted-foreground mt-1">
              Images featuring hard-drawn OBB polygons reflecting final status.
            </p>
          </div>
        </header>

        <div class="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div v-for="row in exportData" :key="row.filename" class="flex flex-col gap-3 group">
            <div
              class="relative rounded-lg overflow-hidden border border-border shadow-sm bg-black/5 aspect-[4/3]"
            >
              <img
                v-if="row.export_image_url"
                :src="row.export_image_url"
                class="w-full h-full object-cover"
              />
              <div
                class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
              >
                <button
                  @click="downloadImage(row.export_image_url, `annotated_${row.filename}`)"
                  class="px-4 py-2 bg-white text-black text-sm font-medium rounded-md shadow-lg hover:bg-gray-100"
                >
                  Download Image
                </button>
              </div>
            </div>
            <div class="text-xs font-mono text-center text-muted-foreground truncate px-2">
              {{ row.filename }}
            </div>
          </div>
        </div>
      </section>

      <div class="flex justify-end pt-4 pb-12">
        <RouterLink
          to="/seeds/runs"
          class="px-6 py-2 border border-border text-foreground hover:bg-muted font-medium text-sm rounded-md transition-colors"
        >
          Return to Runs
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'
import { api } from '@/api'

const route = useRoute()

interface ExportRow {
  filename: string
  species: string
  calculated_active: number
  confidence: number
  final_active: number
  export_image_url: string
}

const loading = ref(true)
const loadError = ref('')
const exportData = ref<ExportRow[]>([])

onMounted(async () => {
  const id = route.params.id
  try {
    const res = await api(`/api/seeds/runs/${id}/export/`)
    if (!res.ok) throw new Error(`Failed to generate export: ${res.status}`)

    const data = await res.json()
    exportData.value = data.data
  } catch (e) {
    loadError.value = String(e)
  } finally {
    loading.value = false
  }
})

function downloadCSV() {
  const headers = [
    'Filename',
    'Species',
    'Calculated Active Seed Count',
    'Model Confidence',
    'Corrected Active Seed Count',
  ]

  const rows = exportData.value.map((r) => [
    r.filename,
    r.species,
    r.calculated_active,
    r.confidence,
    r.final_active,
  ])

  const csvContent = [headers.join(','), ...rows.map((e) => e.join(','))].join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)

  const link = document.createElement('a')
  link.setAttribute('href', url)
  link.setAttribute('download', `seeds_export_run_${route.params.id}.csv`)
  link.style.visibility = 'hidden'
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

async function downloadImage(url: string, filename: string) {
  try {
    const response = await fetch(url)
    const blob = await response.blob()
    const blobUrl = URL.createObjectURL(blob)

    const link = document.createElement('a')
    link.href = blobUrl
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(blobUrl)
  } catch (e) {
    console.error('Image download failed', e)
    alert('Failed to download image.')
  }
}
</script>
