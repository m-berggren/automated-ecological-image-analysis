<template>
  <PageHeader title="Upload" subtitle="Add seed images to start a detection run" />
  <SeedsStepper current="upload" />

  <div class="flex-1 p-8 space-y-6 max-w-3xl mx-auto w-full">
    <!-- Run details -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-3">
      <h2 class="text-sm font-semibold">Run details</h2>
      <div class="space-y-2">
        <label class="block text-xs text-muted-foreground">Name</label>
        <input
          v-model="runName"
          type="text"
          placeholder="e.g. Seeds B — July 2026"
          class="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>
      <div class="space-y-2 pt-2">
        <label class="block text-xs text-muted-foreground"> Notes (Optional) </label>

        <textarea
          v-model="runNotes"
          placeholder="e.g. Dry soil, PEH test v2, camera slightly tilted"
          class="w-full px-3 py-2 text-sm rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
          rows="3"
        />
      </div>
    </section>

    <!-- Seed type -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <h2 class="text-sm font-semibold">Seed type</h2>
      <p class="text-xs text-muted-foreground">Each batch must contain a single species.</p>

      <!-- Seed list -->
      <div class="grid grid-cols-4 gap-3 pt-1 max-h-[10rem] overflow-y-auto">
        <div v-for="seed in seedTypes" :key="seed.id" class="relative shrink-0 pt-2 pr-2">
          <!-- Delete button -->
          <button
            v-if="seed.isCustom"
            @click.stop="removeSeed(seed.id)"
            class="absolute -top-0 -right-0 w-5 h-5 flex items-center justify-center rounded-full bg-green-900 text-white text-xs z-10"
          >
            ×
          </button>

          <!-- Seed button -->
          <button
            @click="selectedSeed = seed.id"
            :class="[
              'group w-36 flex items-center px-3 py-2 rounded-lg border-2 text-left transition-all overflow-hidden',

              selectedSeed === seed.id
                ? 'border-primary bg-primary/5'
                : 'border-border bg-background hover:border-primary/40',
            ]"
          >
            <span class="text-sm font-semibold shrink-0">
              {{ seed.id }}
            </span>

            <span
              v-if="seed.species"
              class="ml-2 overflow-hidden whitespace-nowrap text-[11px] text-muted-foreground italic max-w-0 group-hover:max-w-[100px] opacity-0 group-hover:opacity-100 transition-all duration-200"
            >
              · {{ seed.species }}
            </span>
          </button>
        </div>
      </div>

      <!-- Add button -->
      <button
        @click="openAddSeed"
        class="w-full px-4 py-2 rounded-lg border-2 border-dashed border-border text-sm text-muted-foreground hover:border-primary hover:text-primary transition"
      >
        + Add new seed type
      </button>

      <!-- Inline add form -->
      <div v-if="showAddSeed" class="p-3 border rounded-lg space-y-2 bg-background">
        <input
          v-model="newSeedId"
          placeholder="Code Name (e.g. PEH)"
          class="w-full px-2 py-1 text-sm border rounded"
        />
        <input
          v-model="newSeedSpecies"
          placeholder="Species (optional)"
          class="w-full px-2 py-1 text-sm border rounded"
        />
        <div class="flex gap-2">
          <button @click="addSeed" class="px-3 py-1 text-sm bg-primary text-white rounded-lg">
            Add
          </button>
          <button @click="cancelAddSeed" class="px-3 py-1 text-sm border rounded-lg">Cancel</button>
        </div>
      </div>
    </section>

    <!-- Detection settings -->
    <section class="rounded-xl border border-border bg-surface p-5 space-y-4">
      <h2 class="text-sm font-semibold">Detection settings</h2>
      <p class="text-xs text-muted-foreground">Select model version.</p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
        <div v-for="seed in seedTypes" :key="seed.id" class="space-y-1">
          <span class="text-xs text-muted-foreground"> {{ seed.id }} model version </span>

          <select
            v-model="config.models[seed.id].model_version_id"
            class="w-full px-2 py-1.5 rounded border border-border bg-background text-sm"
          >
            <option :value="null" disabled>Select {{ seed.id }} model version</option>

            <option v-for="m in []" :key="m.id" :value="m.id">
              {{ m.version_name }}
            </option>
          </select>
        </div>
      </div>
      <!-- Misc row -->

      <div class="flex flex-wrap items-center gap-x-6 gap-y-3 pt-3 border-t border-border">
        <!-- Overlapping seeds -->

        <label class="flex items-center gap-2 text-sm">
          <input v-model="overlapping" type="checkbox" />

          <span>Overlapping seeds</span>
        </label>
      </div>
    </section>

    <!-- Drop zone -->
    <section
      class="rounded-xl border-2 border-dashed border-border bg-surface p-10 text-center transition-colors"
      :class="{ 'border-primary bg-primary/5': dragOver, 'opacity-60': creatingUpload }"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <UploadCloud class="w-10 h-10 mx-auto text-muted-foreground" />
      <p class="mt-3 text-sm font-medium">
        Drop a folder or images here, or
        <label class="text-primary cursor-pointer hover:underline">
          browse files
          <input
            type="file"
            multiple
            accept="image/*"
            class="hidden"
            @change="onPick($event, false)"
          />
        </label>
        /
        <label class="text-primary cursor-pointer hover:underline">
          browse folder
          <input
            ref="folderInput"
            type="file"
            multiple
            class="hidden"
            @change="onPick($event, true)"
          />
        </label>
      </p>
      <p class="text-xs text-muted-foreground mt-1">JPG, PNG - uploads in batches of 4</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import SeedsStepper from '@/components/SeedsStepper.vue'
import { UploadCloud } from 'lucide-vue-next'

const runName = ref('')
const runNotes = ref('')
const dragOver = ref(false)

const selectedSeed = ref<string | null>(null)
const selectedCondition = ref<'clean' | 'mixed'>('clean')
const overlapping = ref(true)

const expectedMin = ref<number | null>(null)
const expectedMax = ref<number | null>(null)

const showAddSeed = ref(false)
const newSeedSpecies = ref('')
const newSeedId = ref('')

const seedTypes = ref([
  { id: 'PEH', species: 'Pisum sativum', isCustom: false },
  { id: 'PHYCA', species: 'Phacelia tanacetifolia', isCustom: false },
  { id: 'VAU', species: 'Vicia sativa', isCustom: false },
  { id: 'CAT', species: 'Carthamus tinctorius', isCustom: false },
])

const config = ref({
  models: {
    PEH: { model_version_id: null },
    PHYCA: { model_version_id: null },
    VAU: { model_version_id: null },
    CAT: { model_version_id: null },
  },
})

function openAddSeed() {
  showAddSeed.value = true
}

function cancelAddSeed() {
  showAddSeed.value = false
  newSeedId.value = ''
  newSeedSpecies.value = ''
}

function addSeed() {
  if (!newSeedId.value) return

  seedTypes.value.push({
    id: newSeedId.value,
    species: newSeedSpecies.value,
    isCustom: true,
  })

  cancelAddSeed()
}

function removeSeed(id: string) {
  seedTypes.value = seedTypes.value.filter((s) => s.id !== id)

  if (selectedSeed.value === id) {
    selectedSeed.value = null
  }
}

function onPick(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files) {
    console.log('picked files:', target.files)
  }
}

function onDrop(e: DragEvent) {
  dragOver.value = false
  if (e.dataTransfer?.files) {
    console.log('dropped files:', e.dataTransfer.files)
  }
}

function onDragLeave(e: DragEvent) {
  if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) {
    dragOver.value = false
  }
}
</script>
