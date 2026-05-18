<template>
  <PageHeader title="Training" subtitle="Update the pollinator pipeline on reviewed detections" />

  <div class="flex-1 overflow-auto">
    <div v-if="loading" class="p-8 text-sm text-muted-foreground">Loading…</div>
    <div v-else-if="loadError" class="p-8 text-sm text-red-600">{{ loadError }}</div>

    <div v-else class="p-6 space-y-4 max-w-4xl mx-auto w-full">
      <!-- New training job card -->
      <section class="rounded-xl border border-border bg-card overflow-hidden shadow-md">
        <header class="px-5 py-4 bg-primary/[0.22] border-b border-border">
          <h2 class="font-bold text-lg tracking-tight">New training job</h2>
          <p class="text-xs text-muted-foreground mt-0.5">Pick a model, choose data, and start.</p>
        </header>

        <!-- Step 1: Pick model -->
        <div class="px-5 py-4 border-b border-border">
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            1. Pick a model to retrain
          </div>
          <div class="space-y-2">
            <label
              v-for="track in tracks"
              :key="track.id"
              class="flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors"
              :class="
                selectedTrackId === track.id
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-primary/40'
              "
            >
              <input type="radio" :value="track.id" v-model="selectedTrackId" class="mt-0.5" />
              <div class="flex-1 min-w-0">
                <div class="flex items-baseline gap-2 flex-wrap">
                  <span class="font-medium text-sm">{{ track.label }}</span>
                  <span
                    v-if="activeVersion(track)"
                    class="text-xs px-2 py-0.5 rounded-full bg-green-300 text-green-900 font-medium"
                  >
                    {{ activeVersion(track)!.version_name }}
                  </span>
                  <span
                    v-if="track.active_job"
                    class="text-xs px-2 py-0.5 rounded-full bg-blue-200 text-blue-800 font-medium"
                  >
                    training in progress
                  </span>
                </div>
                <p class="text-xs text-muted-foreground mt-0.5">{{ track.description }}</p>
                <div v-if="activeVersion(track)" class="text-xs text-muted-foreground mt-1">
                  {{ track.metric_label }}
                  <span class="font-mono ml-1 text-foreground">
                    {{ formatMetric(activeMainMetric(track)) }}
                  </span>
                  · {{ track.data_pool.total_samples.toLocaleString() }} samples available
                  <span v-if="track.data_pool.new_since_active > 0" class="text-primary">
                    (+{{ track.data_pool.new_since_active }} new since active)
                  </span>
                </div>
              </div>
            </label>
          </div>
        </div>

        <!-- Step 2: Choose data -->
        <div v-if="selectedTrack" class="px-5 py-4 border-b border-border">
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            2. Choose training data
          </div>
          <!-- Pool summary card -->
          <div class="rounded-lg border border-border bg-muted/20 p-4 space-y-3">
            <div class="flex items-start gap-3">
              <input
                id="use-training-pool"
                type="checkbox"
                class="mt-1 accent-primary disabled:opacity-50"
                :checked="useTrainingPool"
                :disabled="!canUseTrainingPool"
                @change="useTrainingPool = !useTrainingPool"
              />
              <div class="flex-1 min-w-0">
                <label
                  for="use-training-pool"
                  class="text-sm font-medium block"
                  :class="!canUseTrainingPool && 'text-muted-foreground'"
                >
                  {{ totalPoolSamples.toLocaleString() }} samples in pool
                </label>
                <div class="text-xs text-muted-foreground">
                  {{ selectedTrack.data_pool.total_samples.toLocaleString() }} from review ·
                  {{ uploadedFiles.length }} uploaded
                  {{ uploadedFiles.length === 1 ? 'file' : 'files' }}
                </div>
                <!-- Always rendered so the card height stays constant across
                     track selections; invisible when YOLO isn't selected. -->
                <div
                  class="text-xs text-amber-700 mt-1"
                  :class="{ invisible: canUseTrainingPool }"
                  :aria-hidden="canUseTrainingPool"
                >
                  Not usable for YOLO — it trains on full reviewed images, not uploaded crops or the
                  aggregated pool.
                </div>
              </div>
              <button
                class="text-xs text-primary hover:underline shrink-0"
                @click="openReviewDrawer"
              >
                Browse pool →
              </button>
            </div>
            <div class="flex flex-wrap gap-3 text-xs text-muted-foreground">
              <span
                v-for="row in classRows(selectedTrack)"
                :key="row.label"
                class="inline-flex items-center gap-1"
              >
                <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: row.color }" />
                {{ row.count.toLocaleString() }} {{ row.label.toLowerCase() }}
              </span>
            </div>
            <div class="h-1.5 rounded-full overflow-hidden flex">
              <div
                v-for="row in classRows(selectedTrack)"
                :key="row.label"
                :style="{ width: row.percent + '%', backgroundColor: row.color }"
                class="h-full"
              />
            </div>
          </div>

          <!-- Add data drop zone. Tabs swap between file/folder modes;
               the box highlights green (theme primary) when files exist. -->
          <UploadDropZone
            class="mt-3"
            v-model:active-tab="trainingUploadTab"
            :tabs="trainingUploadTabs"
            :has-files="uploadedFiles.length > 0"
            @select="onTrainingUploadSelect"
          >
            <template #body>
              <UploadCloud class="w-8 h-8 mx-auto text-muted-foreground" />
              <div class="text-sm font-medium mt-2">
                <template v-if="uploadedFiles.length">
                  {{ uploadedFiles.length }} file{{ uploadedFiles.length === 1 ? '' : 's' }} added —
                  drop more to extend
                </template>
                <template v-else> Drop a folder or images here, or click to browse </template>
              </div>
              <div class="text-xs text-muted-foreground mt-1">
                Adds to the training pool. Accepts .jpg, .png, .zip, or a folder of images.
              </div>
            </template>
          </UploadDropZone>

          <!-- View / clear link row. Shown only when files exist. Clicking
               "View files" opens a modal so the form layout doesn't shift. -->
          <div v-if="uploadedFiles.length" class="mt-2 text-xs flex items-center justify-end gap-3">
            <button class="text-primary hover:underline" @click.stop="filesModalOpen = true">
              View files →
            </button>
            <button class="text-muted-foreground hover:text-red-600" @click.stop="clearUploads">
              Clear
            </button>
          </div>

          <!-- Class filter (detector and group classifier only) -->
          <div v-if="trackHasClassFilter" class="mt-4 space-y-2 min-h-14">
            <div class="flex items-center gap-1.5 text-xs font-medium text-foreground">
              <span>Classes to include</span>
              <InfoPopover>
                Only selected classes are used. Images containing detections of unselected classes
                are dropped (not relabelled as background).
              </InfoPopover>
            </div>
            <div class="flex flex-wrap gap-3">
              <label
                v-for="cls in POLLINATOR_PREDICTED_CLASSES"
                :key="cls"
                class="inline-flex items-center gap-1.5 text-xs cursor-pointer"
              >
                <input type="checkbox" :checked="classFilter.has(cls)" @change="toggleClass(cls)" />
                <span
                  class="w-1.5 h-1.5 rounded-full"
                  :style="{ backgroundColor: CLASS_COLORS[cls] }"
                />
                <span class="capitalize">{{ cls }}</span>
              </label>
            </div>
          </div>
          <!-- Placeholder when the class filter doesn't apply (binary
               classifier). Keeps step 2 the same height across tracks. -->
          <div v-else class="mt-4 min-h-14" aria-hidden="true" />
        </div>

        <!-- Step 3: Settings -->
        <div v-if="selectedTrack" class="px-5 py-4 border-b border-border">
          <div
            class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-3"
          >
            3. Settings
          </div>
          <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <label
              class="text-xs text-muted-foreground space-y-1"
              title="Percentage of the dataset used to train the model. The rest goes to val (early-stop signal) and test (held-out evaluation)."
            >
              <span>Train %</span>
              <input
                v-model.number="settings.train_split"
                type="number"
                min="50"
                max="95"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label
              class="text-xs text-muted-foreground space-y-1"
              title="Percentage used during training to monitor loss/metrics each epoch and trigger early stopping. Not used for gradient updates."
            >
              <span>Val %</span>
              <input
                v-model.number="settings.val_split"
                type="number"
                min="0"
                max="40"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label
              class="text-xs text-muted-foreground space-y-1"
              title="Percentage held out and never seen during training. Reported once at the end as an unbiased performance estimate."
            >
              <span>Test %</span>
              <input
                v-model.number="settings.test_split"
                type="number"
                min="0"
                max="40"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
            <label
              class="text-xs text-muted-foreground space-y-1"
              title="Number of full passes over the training set. Higher = more time, more risk of overfitting. The backend may early-stop sooner if val metrics plateau."
            >
              <span>Epochs</span>
              <input
                v-model.number="settings.epochs"
                type="number"
                min="1"
                max="200"
                class="w-full px-2 py-1 rounded border border-border bg-background text-sm font-mono text-foreground"
              />
            </label>
          </div>

          <!-- Sub-options: horizontal layout, each column has header + info + control -->
          <div class="mt-4 flex flex-wrap gap-x-8 gap-y-4 min-h-14">
            <div class="space-y-1.5">
              <div class="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <span>Sampling strategy</span>
                <InfoPopover>
                  Keeps per-class proportions equal across train/val/test. Otherwise random splits
                  can leave rare classes out entirely.
                </InfoPopover>
              </div>
              <label class="inline-flex items-center gap-2 text-xs cursor-pointer">
                <input v-model="settings.stratified" type="checkbox" />
                Stratified split
              </label>
            </div>

            <div v-if="trackHasImgSize" class="space-y-1.5">
              <div class="flex items-center gap-1.5 text-xs font-medium text-foreground">
                <span>Image size</span>
                <InfoPopover>
                  Training input resolution. Larger = finer detail for small insects, more memory.
                  Inference defaults to this size, meaning different sizes work but usually reduce
                  accuracy.
                </InfoPopover>
              </div>
              <select
                v-model.number="imgSize"
                class="px-2 py-1 rounded border border-border bg-background text-foreground text-xs"
              >
                <option v-for="s in IMG_SIZE_OPTIONS" :key="s" :value="s">{{ s }}</option>
              </select>
            </div>
          </div>

          <div class="mt-3 text-xs">
            <span v-if="splitTotal !== 100" class="text-amber-700">
              ⚠ Splits sum to {{ splitTotal }}% (must equal 100)
            </span>
          </div>
        </div>

        <!-- Submit -->
        <div class="px-5 py-4 flex items-center gap-3 justify-end">
          <span v-if="formMessage" class="text-xs text-muted-foreground">{{ formMessage }}</span>
          <span v-else-if="!canSubmit && submitBlockReason" class="text-xs text-muted-foreground">
            {{ submitBlockReason }}
          </span>
          <button
            :disabled="!canSubmit"
            class="px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="startTraining"
          >
            Start training
          </button>
        </div>
      </section>

      <!-- Active job (if any) -->
      <section
        v-if="activeJobs.length"
        class="rounded-xl border border-border bg-card overflow-hidden shadow-md"
      >
        <header class="px-5 py-4 bg-blue-100 border-b border-border">
          <h2 class="font-bold text-base tracking-tight">
            Currently training · {{ activeJobs.length }}
          </h2>
        </header>
        <ul class="divide-y divide-border">
          <li v-for="entry in activeJobs" :key="entry.track.id" class="px-5 py-4">
            <div class="flex items-baseline gap-3 mb-2">
              <span class="font-medium text-sm">{{ entry.track.label }}</span>
              <span class="text-xs text-muted-foreground">
                {{ entry.track.active_job!.version_name }}
              </span>
              <button
                class="ml-auto text-xs px-2 py-1 rounded border border-border hover:bg-muted"
                @click="cancelJob(entry.track)"
              >
                Cancel
              </button>
            </div>
            <div class="text-xs text-muted-foreground mb-2">
              epoch {{ entry.track.active_job!.current_epoch }} /
              {{ entry.track.active_job!.total_epochs }} · loss
              {{ entry.track.active_job!.loss.toFixed(3) }} · val acc
              {{ (entry.track.active_job!.val_accuracy * 100).toFixed(1) }}%
            </div>
            <div class="h-1.5 rounded-full bg-muted overflow-hidden max-w-md">
              <div
                class="h-full bg-blue-500 transition-all"
                :style="{ width: jobPercent(entry.track.active_job!) + '%' }"
              />
            </div>
            <div class="text-xs text-muted-foreground mt-1 font-mono">
              {{ humanDuration(jobElapsed(entry.track.active_job!)) }} elapsed · ~{{
                humanDuration(jobRemaining(entry.track.active_job!))
              }}
              remaining
            </div>
          </li>
        </ul>
      </section>

      <!-- Training history -->
      <section class="rounded-xl border border-border bg-card overflow-hidden shadow-md">
        <header class="px-5 py-4 bg-primary/[0.22] border-b border-border">
          <h2 class="font-bold text-lg tracking-tight">Training history</h2>
        </header>
        <table class="w-full text-sm">
          <thead class="text-xs text-muted-foreground bg-muted/30">
            <tr>
              <th class="text-left font-medium px-5 py-2">Job</th>
              <th class="text-left font-medium px-3 py-2">Model</th>
              <th class="text-left font-medium px-3 py-2">Started</th>
              <th class="text-left font-medium px-3 py-2">Duration</th>
              <th class="text-left font-medium px-3 py-2">Samples</th>
              <th class="text-left font-medium px-3 py-2">Status</th>
              <th class="text-left font-medium px-3 py-2">Result</th>
              <th class="px-3 py-2"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="job in history" :key="job.id">
              <tr
                class="border-t border-border hover:bg-muted/20 cursor-pointer"
                @click="toggleHistory(job.id)"
              >
                <td class="px-5 py-2 font-mono text-xs">#{{ job.id }}</td>
                <td class="px-3 py-2 text-xs">{{ job.track_label }}</td>
                <td class="px-3 py-2 text-xs text-muted-foreground">
                  {{ formatRelative(job.started_at) }}
                </td>
                <td class="px-3 py-2 text-xs font-mono">
                  {{ job.duration_seconds ? humanDuration(job.duration_seconds) : '—' }}
                </td>
                <td class="px-3 py-2 text-xs">{{ job.samples_used.toLocaleString() }}</td>
                <td class="px-3 py-2">
                  <span class="text-xs px-2 py-0.5 rounded-full" :class="statusClass(job.status)">
                    {{ job.status }}
                  </span>
                </td>
                <td class="px-3 py-2 text-xs">
                  <template v-if="job.main_metric_value != null">
                    <span class="text-muted-foreground">{{ job.main_metric_label }}</span>
                    <span class="ml-1 font-mono">{{ job.main_metric_value.toFixed(2) }}</span>
                  </template>
                  <span v-else-if="job.error_message" class="text-red-700 text-xs">
                    {{ job.error_message }}
                  </span>
                  <span v-else class="text-muted-foreground">—</span>
                </td>
                <td class="px-3 py-2 text-right text-muted-foreground">
                  {{ expandedHistory.has(job.id) ? '▾' : '▸' }}
                </td>
              </tr>
              <tr v-if="expandedHistory.has(job.id)" class="border-t border-border bg-muted/10">
                <td></td>
                <td colspan="7" class="px-3 py-4">
                  <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs max-w-md">
                    <dt class="text-muted-foreground">Resulting version</dt>
                    <dd class="font-medium">{{ job.version_name }}</dd>
                    <dt class="text-muted-foreground">Started</dt>
                    <dd>{{ new Date(job.started_at).toLocaleString() }}</dd>
                    <dt class="text-muted-foreground">Epochs requested</dt>
                    <dd class="font-mono">{{ job.epochs_total }}</dd>
                    <dt class="text-muted-foreground">Samples used</dt>
                    <dd class="font-mono">{{ job.samples_used.toLocaleString() }}</dd>
                    <dt class="text-muted-foreground">Initiated by</dt>
                    <dd>{{ job.initiated_by }}</dd>
                    <template v-if="job.error_message">
                      <dt class="text-muted-foreground">Error</dt>
                      <dd class="text-red-700">{{ job.error_message }}</dd>
                    </template>
                  </dl>
                  <div v-if="chartsForJob(job)" class="mt-4 pt-3 border-t border-border">
                    <div
                      class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-2"
                    >
                      Charts
                    </div>
                    <TrainingCharts :charts="chartsForJob(job)" />
                  </div>
                </td>
              </tr>
            </template>
            <tr v-if="!history.length">
              <td colspan="8" class="px-5 py-6 text-center text-sm text-muted-foreground">
                No training jobs yet.
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <!-- Review drawer -->
    <Transition name="drawer">
      <div
        v-if="reviewDrawerOpen"
        class="fixed inset-0 z-50 flex"
        @click.self="reviewDrawerOpen = false"
      >
        <div class="flex-1 bg-black/40" />
        <aside class="w-[640px] max-w-full bg-card border-l border-border shadow-2xl flex flex-col">
          <header
            class="px-5 py-3 border-b border-border bg-primary/[0.22] flex items-center gap-3"
          >
            <h2 class="font-bold text-base tracking-tight">Review training pool</h2>
            <span v-if="selectedTrack" class="text-xs text-muted-foreground">
              {{ selectedTrack.label }} ·
              <span class="font-mono">{{ drawerIncludedCount }}</span>
              of
              <span class="font-mono">{{ drawerThumbnails.length }}</span>
              included
            </span>
            <button
              class="ml-auto text-muted-foreground hover:text-foreground"
              @click="reviewDrawerOpen = false"
            >
              ✕
            </button>
          </header>
          <div
            v-if="selectedTrack?.id === 'detector'"
            class="px-5 py-2 border-b border-amber-200 bg-amber-50 text-xs text-amber-900 flex items-start gap-2"
          >
            <span aria-hidden="true">⚠</span>
            <span>
              YOLO trains on fully-reviewed images. Detections from images with pending review are
              skipped server-side regardless of selection here.
            </span>
          </div>
          <div class="px-5 py-3 border-b border-border flex flex-wrap items-center gap-2 text-xs">
            <span class="text-muted-foreground">Filter:</span>
            <button
              v-for="cls in drawerClasses"
              :key="cls.value"
              class="px-2 py-1 rounded font-medium transition-colors"
              :class="
                drawerFilter === cls.value
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted'
              "
              @click="drawerFilter = cls.value"
            >
              {{ cls.label }}
            </button>
            <span class="ml-auto flex items-center gap-2">
              <button class="text-primary hover:underline" @click="selectAllSamples">
                Include all
              </button>
              <span class="text-muted-foreground">·</span>
              <button class="text-primary hover:underline" @click="deselectAllSamples">
                Exclude all
              </button>
            </span>
          </div>
          <div class="flex-1 overflow-auto p-4">
            <div
              v-if="!drawerThumbnails.length"
              class="text-xs text-muted-foreground text-center py-12"
            >
              No samples available for this track yet.
            </div>
            <div v-else class="grid grid-cols-5 gap-2">
              <label
                v-for="thumb in drawerThumbnails"
                :key="thumb.id"
                class="aspect-square rounded border flex items-center justify-center text-2xl relative overflow-hidden cursor-pointer transition-opacity"
                :class="
                  excludedSampleIds.has(thumb.id)
                    ? 'opacity-30 border-border'
                    : 'border-border hover:border-primary/40'
                "
                :style="{
                  backgroundColor: excludedSampleIds.has(thumb.id) ? 'transparent' : thumb.bg,
                }"
                :title="thumb.label"
              >
                <input
                  type="checkbox"
                  :checked="!excludedSampleIds.has(thumb.id)"
                  class="absolute top-1.5 left-1.5 z-10 accent-primary"
                  @change="toggleSampleInclusion(thumb.id)"
                />
                <span class="opacity-50">{{ thumb.glyph }}</span>
                <div
                  class="absolute bottom-0 left-0 right-0 h-1.5"
                  :style="{ backgroundColor: thumb.color }"
                />
              </label>
            </div>
            <p
              v-if="drawerThumbnails.length"
              class="text-xs text-muted-foreground mt-4 text-center"
            >
              Placeholder thumbnails. Real crops will replace these once the training-pool endpoint
              is wired.
            </p>
          </div>
        </aside>
      </div>
    </Transition>

    <!-- Uploaded files modal. Listed here (not inline) so adding files
         doesn't push the rest of the form down. -->
    <Transition name="info-pop">
      <div
        v-if="filesModalOpen"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        @click.self="filesModalOpen = false"
      >
        <div class="absolute inset-0 bg-black/40" />
        <div
          class="relative w-[480px] max-w-full max-h-[80vh] bg-card border border-border rounded-lg shadow-2xl flex flex-col"
        >
          <header class="px-5 py-3 border-b border-border flex items-center gap-3">
            <h3 class="font-bold text-sm tracking-tight">
              Uploaded files
              <span class="text-muted-foreground font-mono ml-1">
                ({{ uploadedFiles.length }})
              </span>
            </h3>
            <button
              class="ml-auto text-muted-foreground hover:text-foreground"
              @click="filesModalOpen = false"
            >
              ✕
            </button>
          </header>
          <ul class="flex-1 overflow-auto p-3 space-y-1 text-xs">
            <li
              v-for="(file, idx) in uploadedFiles"
              :key="file.name + idx"
              class="flex items-center gap-2 px-2 py-1.5 rounded border border-border bg-background"
            >
              <span class="font-mono flex-1 truncate">{{ file.name }}</span>
              <span class="text-muted-foreground shrink-0">{{ formatFileSize(file.size) }}</span>
              <button class="text-muted-foreground hover:text-red-600" @click="removeUpload(idx)">
                ✕
              </button>
            </li>
            <li v-if="!uploadedFiles.length" class="text-center text-muted-foreground py-8">
              No files added.
            </li>
          </ul>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/PageHeader.vue'
import InfoPopover from '@/components/InfoPopover.vue'
import TrainingCharts from '@/components/TrainingCharts.vue'
import UploadDropZone, { type UploadTab } from '@/components/UploadDropZone.vue'
import { UploadCloud } from 'lucide-vue-next'
import { api } from '@/api'
import { tracksFromVersions, type BackendModelVersion } from '@/lib/model-tracks'

interface ChartData {
  training_curve?: Array<{ epoch: number; loss: number; val_metric: number }>
  confusion_matrix?: { labels: string[]; values: number[][] }
  per_class?: Array<{ label: string; value: number }>
}

interface Version {
  id: number
  version_name: string
  is_active: boolean
  metrics: Record<string, number>
  samples: number
  trained_at: string
  training_duration_seconds: number
  parameters: Record<string, unknown>
  charts?: ChartData | null
}

interface ActiveJob {
  id: number
  version_name: string
  mode: string
  started_at: string
  estimated_total_seconds: number
  current_epoch: number
  total_epochs: number
  loss: number
  val_accuracy: number
}

interface DataPool {
  total_samples: number
  new_since_active: number
  by_class: Record<string, number>
}

interface Track {
  id: string
  label: string
  description: string
  kind: string
  metric_label: string
  active_version_id: number | null
  versions: Version[]
  data_pool: DataPool
  active_job: ActiveJob | null
}

interface HistoryEntry {
  id: number
  track_id: string
  track_label: string
  version_name: string
  samples_used: number
  epochs_total: number
  started_at: string
  duration_seconds: number | null
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'pending'
  main_metric_label: string
  main_metric_value: number | null
  initiated_by: string
  error_message?: string
}

const CLASS_COLORS: Record<string, string> = {
  fly: '#6b9bd2',
  bumblebee: '#e6a946',
  butterfly: '#c87bba',
  other: '#9aa3ab',
  insect: '#6b9bd2',
  background: '#9aa3ab',
}

const route = useRoute()
const loading = ref(true)
const loadError = ref('')
const tracks = ref<Track[]>([])
const history = ref<HistoryEntry[]>([])
const selectedTrackId = ref<string | null>(null)
const formMessage = ref('')
const expandedHistory = ref<Set<number>>(new Set())
const uploadedFiles = ref<Array<{ name: string; size: number }>>([])
const filesModalOpen = ref(false)

function clearUploads() {
  uploadedFiles.value = []
  filesModalOpen.value = false
}

const trainingUploadTab = ref('files')
const trainingUploadTabs: UploadTab[] = [
  {
    key: 'files',
    label: 'Files',
    mode: 'files',
    accept: '.jpg,.jpeg,.png,.zip',
  },
  {
    key: 'folder',
    label: 'Folder',
    mode: 'folder',
  },
]

function onTrainingUploadSelect(files: File[]) {
  for (const f of files) addFile(f)
}

const reviewDrawerOpen = ref(false)
const drawerFilter = ref<string>('all')

const settings = reactive({
  train_split: 80,
  val_split: 10,
  test_split: 10,
  epochs: 5,
  stratified: true,
})

// Classes the pollinator detector and group classifier predict. Binary has
// only insect/background and does not expose class_filter.
const POLLINATOR_PREDICTED_CLASSES = ['bumblebee', 'fly', 'butterfly', 'other']

// Valid YOLO input sizes (must be multiples of 32). Default 640 matches the
// existing train_yolo default; larger sizes help small insects in big frames
// at the cost of training time.
const IMG_SIZE_OPTIONS = [640, 960, 1280, 1536, 2048]

const imgSize = ref(640)
const classFilter = reactive(new Set<string>(POLLINATOR_PREDICTED_CLASSES))
// User-facing toggle for the aggregated training pool (reviewed + uploads).
// Disabled and forced off for the YOLO detector, which trains on full
// reviewed images rather than the mixed pool.
const useTrainingPool = ref(true)

function toggleClass(cls: string) {
  if (classFilter.has(cls)) classFilter.delete(cls)
  else classFilter.add(cls)
}

const previewMode = computed<string | null>(() => {
  const value = route.query.preview
  return typeof value === 'string' ? value : null
})

onMounted(async () => {
  if (previewMode.value) {
    const data = await loadPreview(previewMode.value)
    if (data) {
      tracks.value = data.tracks
      history.value = data.history
      if (tracks.value.length) selectedTrackId.value = tracks.value[0].id
      loading.value = false
      return
    }
  }
  await loadFromApi()
})

interface VersionMock extends Omit<Version, 'trained_at'> {
  trained_at_offset_seconds: number
}
interface ActiveJobMock extends Omit<ActiveJob, 'started_at'> {
  started_at_offset_seconds: number
}
interface TrackMock extends Omit<Track, 'versions' | 'active_job'> {
  versions: VersionMock[]
  active_job: ActiveJobMock | null
}
interface HistoryMock extends Omit<HistoryEntry, 'started_at'> {
  started_at_offset_seconds: number
}

async function loadPreview(_mode: string) {
  if (!import.meta.env.DEV) return null
  const { default: mocks } = await import('@/mocks/pollinator-models.json')
  const raw = (
    mocks as unknown as Record<
      string,
      { tracks: TrackMock[]; training_history: HistoryMock[] } | undefined
    >
  ).default
  if (!raw) return null
  const now = Date.now()
  const isoFromOffset = (offset: number): string => new Date(now + offset * 1000).toISOString()
  return {
    tracks: raw.tracks.map((t) => ({
      ...t,
      versions: t.versions.map((v) => ({
        ...v,
        trained_at: isoFromOffset(v.trained_at_offset_seconds),
      })),
      active_job: t.active_job
        ? { ...t.active_job, started_at: isoFromOffset(t.active_job.started_at_offset_seconds) }
        : null,
    })),
    history: raw.training_history.map((h) => ({
      ...h,
      started_at: isoFromOffset(h.started_at_offset_seconds),
    })),
  }
}

async function loadFromApi() {
  try {
    const res = await api('/api/analysis/models/?module=pollinators')
    if (!res.ok) {
      loadError.value = `HTTP ${res.status}`
      return
    }
    const versions: BackendModelVersion[] = await res.json()
    // Per-track data_pool counts come from a future /training/pool/ endpoint.
    // Stubbed to zero for now; sample/duration/charts come from completed
    // TrainingJob metadata once wired.
    tracks.value = tracksFromVersions(versions).map((t) => ({
      id: t.id,
      label: t.label,
      description: t.description,
      kind: t.kind,
      metric_label: t.metric_label,
      active_version_id: t.active_version_id,
      versions: t.versions.map((v) => ({
        ...v,
        samples: 0,
        training_duration_seconds: 0,
        charts: null,
      })),
      data_pool: { total_samples: 0, new_since_active: 0, by_class: {} },
      active_job: null,
    }))
    if (tracks.value.length && !selectedTrackId.value) {
      selectedTrackId.value = tracks.value[0].id
    }

    // Load training jobs in parallel — populates active_job per track
    // (resuming polling for in-flight jobs) and the history list below.
    await loadTrainingJobs(versions)
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

// API ↔ UI track id mapping (backend uses short forms, UI uses ModelKind).
const API_TO_UI_TRACK: Record<string, string> = {
  detector: 'detector',
  binary: 'binary_classifier',
  group: 'group_classifier',
}

interface BackendTrainingJobListEntry {
  id: number
  module: string
  name: string
  status: string
  config: Record<string, unknown>
  resulting_model: number | null
  image_count: number
  current_epoch: number
  total_epochs: number
  started_at: string
  completed_at: string | null
  error_message?: string
}

async function loadTrainingJobs(versions: BackendModelVersion[]) {
  let res: Response
  try {
    res = await api('/api/analysis/training/?module=pollinators')
  } catch {
    return
  }
  if (!res.ok) return
  const jobs: BackendTrainingJobListEntry[] = await res.json()

  // version_name lookup so completed history rows show the produced model.
  const versionNameById = new Map<number, string>(versions.map((v) => [v.id, v.version_name]))

  history.value = jobs.map((job): HistoryEntry => {
    const apiTrack = String(job.config?.track ?? '')
    const trackId = API_TO_UI_TRACK[apiTrack] ?? apiTrack
    const trackLabel = tracks.value.find((t) => t.id === trackId)?.label ?? apiTrack ?? 'Unknown'
    const duration =
      job.completed_at !== null
        ? Math.round(
            (new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000,
          )
        : null
    return {
      id: job.id,
      track_id: trackId,
      track_label: trackLabel,
      version_name:
        (job.resulting_model !== null && versionNameById.get(job.resulting_model)) ||
        `${apiTrack || 'job'}-#${job.id}`,
      samples_used: job.image_count,
      epochs_total: job.total_epochs,
      started_at: job.started_at,
      duration_seconds: duration,
      status: job.status as HistoryEntry['status'],
      main_metric_label: tracks.value.find((t) => t.id === trackId)?.metric_label ?? '',
      main_metric_value: null,
      initiated_by: '',
    }
  })

  // Resume polling for any running/pending jobs found server-side. Maps each
  // to its track's active_job slot and restarts the 2s poll loop.
  for (const job of jobs) {
    if (job.status !== 'running' && job.status !== 'pending') continue
    const apiTrack = String(job.config?.track ?? '')
    const trackId = API_TO_UI_TRACK[apiTrack]
    const track = tracks.value.find((t) => t.id === trackId)
    if (!track) continue
    track.active_job = jobToActiveJob(
      {
        id: job.id,
        status: job.status,
        current_epoch: job.current_epoch,
        total_epochs: job.total_epochs,
        started_at: job.started_at,
        metrics: {},
        resulting_model: job.resulting_model,
        error_message: job.error_message,
      },
      track,
    )
    startPolling(track.id, job.id)
  }
}

const selectedTrack = computed(
  () => tracks.value.find((t) => t.id === selectedTrackId.value) ?? null,
)

// Binary classifier predicts insect vs background; class_filter doesn't apply.
// img_size only matters for the YOLO detector.
const trackHasClassFilter = computed(
  () => selectedTrack.value?.id === 'detector' || selectedTrack.value?.id === 'group_classifier',
)
const trackHasImgSize = computed(() => selectedTrack.value?.id === 'detector')
// YOLO can't consume the aggregated pool (it includes uploaded crops without
// bbox labels). Force the checkbox off and disabled for the detector track.
const canUseTrainingPool = computed(() => selectedTrack.value?.id !== 'detector')
watch(canUseTrainingPool, (allowed) => {
  if (!allowed) useTrainingPool.value = false
})

const splitTotal = computed(() => settings.train_split + settings.val_split + settings.test_split)

const activeJobs = computed(() =>
  tracks.value.filter((t) => t.active_job !== null).map((track) => ({ track })),
)

// Any pollinator track currently has a running/pending job. Used to gate the
// Start button across tracks — concurrent training would contend for the
// shared GPU/CPU.
const anyJobActive = computed(() => tracks.value.some((t) => t.active_job !== null))

const canSubmit = computed(() => {
  if (!selectedTrack.value) return false
  if (anyJobActive.value) return false
  if (splitTotal.value !== 100) return false
  // Incremental retraining requires a source model to continue from.
  if (selectedTrack.value.active_version_id == null) return false
  return true
})

const submitBlockReason = computed<string>(() => {
  if (!selectedTrack.value) return ''
  if (anyJobActive.value) {
    const busy = tracks.value.find((t) => t.active_job !== null)
    return busy
      ? `Another training job is running (${busy.label}). Wait for it to finish.`
      : 'Another training job is running.'
  }
  if (splitTotal.value !== 100) {
    return `Splits sum to ${splitTotal.value}% (must equal 100).`
  }
  if (selectedTrack.value.active_version_id == null) {
    return `${selectedTrack.value.label} has no active version to retrain from.`
  }
  return ''
})

const totalPoolSamples = computed(() => {
  if (!selectedTrack.value) return 0
  return selectedTrack.value.data_pool.total_samples + uploadedFiles.value.length
})

function activeVersion(t: Track): Version | null {
  return t.versions.find((v) => v.is_active) ?? null
}
function activeMainMetric(t: Track): number | undefined {
  const v = activeVersion(t)
  if (!v) return undefined
  return v.metrics[t.metric_label] ?? Object.values(v.metrics)[0]
}
function formatMetric(value: number | undefined): string {
  if (value === undefined) return '—'
  return value.toFixed(2)
}
function classRows(t: Track) {
  const total = Object.values(t.data_pool.by_class).reduce((a, b) => a + b, 0) || 1
  return Object.entries(t.data_pool.by_class)
    .sort((a, b) => b[1] - a[1])
    .map(([cls, count]) => ({
      label: cls[0].toUpperCase() + cls.slice(1),
      count,
      percent: Math.round((count / total) * 100),
      color: CLASS_COLORS[cls] ?? '#9aa3ab',
    }))
}
function jobElapsed(j: ActiveJob): number {
  return Math.max(0, (Date.now() - new Date(j.started_at).getTime()) / 1000)
}
function jobRemaining(j: ActiveJob): number {
  return Math.max(0, j.estimated_total_seconds - jobElapsed(j))
}
function jobPercent(j: ActiveJob): number {
  if (!j.estimated_total_seconds) return 0
  return Math.min(100, Math.round((jobElapsed(j) / j.estimated_total_seconds) * 100))
}
function humanDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.round((seconds % 3600) / 60)
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}
function formatRelative(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

function statusClass(s: string): string {
  switch (s) {
    case 'completed':
      return 'bg-green-200 text-green-800'
    case 'running':
      return 'bg-blue-200 text-blue-800'
    case 'failed':
      return 'bg-red-200 text-red-800'
    case 'cancelled':
      return 'bg-muted text-muted-foreground'
    case 'pending':
      return 'bg-amber-200 text-amber-800'
    default:
      return 'bg-muted text-muted-foreground'
  }
}

// Backend track id mapping. UI uses ModelKind values (binary_classifier,
// group_classifier); the training endpoint's config.track expects the short
// form (binary, group). Keep this small map next to its only caller.
const UI_TO_API_TRACK: Record<string, string> = {
  detector: 'detector',
  binary_classifier: 'binary',
  group_classifier: 'group',
}

// Per-track polling intervals, keyed by track.id. Cleared on cancel/finish/unmount.
const pollIntervals: Map<string, number> = new Map()

interface BackendTrainingJob {
  id: number
  status: string
  current_epoch: number
  total_epochs: number
  started_at: string
  metrics: Record<string, unknown>
  resulting_model: number | null
  error_message?: string
}

// Read a scalar metric out of the backend's free-form metrics JSON. Shape
// varies per track (detector: {val: {mAP50}, test: {...}}, classifier: flat),
// so we probe a few likely keys and fall back to 0 if none match.
function pickMetric(metrics: Record<string, unknown>, keys: string[]): number {
  for (const k of keys) {
    const parts = k.split('.')
    let cur: unknown = metrics
    for (const p of parts) {
      if (cur && typeof cur === 'object' && p in (cur as Record<string, unknown>)) {
        cur = (cur as Record<string, unknown>)[p]
      } else {
        cur = undefined
        break
      }
    }
    if (typeof cur === 'number') return cur
  }
  return 0
}

function jobToActiveJob(job: BackendTrainingJob, track: Track): ActiveJob {
  // Estimate total seconds from elapsed/current epoch when we have one;
  // otherwise leave 0 (jobPercent/jobRemaining handle 0 gracefully).
  const elapsed = Math.max(0, (Date.now() - new Date(job.started_at).getTime()) / 1000)
  const estimated_total =
    job.current_epoch > 0 && job.total_epochs > 0
      ? Math.round((elapsed / job.current_epoch) * job.total_epochs)
      : 0
  return {
    id: job.id,
    version_name: `${track.id}-v${track.versions.length + 1} (in progress)`,
    mode: 'incremental',
    started_at: job.started_at,
    estimated_total_seconds: estimated_total,
    current_epoch: job.current_epoch,
    total_epochs: job.total_epochs,
    loss: pickMetric(job.metrics, ['loss', 'val.loss']),
    val_accuracy: pickMetric(job.metrics, ['acc', 'val_acc', 'macro_f1', 'val.mAP50']),
  }
}

function stopPolling(trackId: string) {
  const id = pollIntervals.get(trackId)
  if (id !== undefined) {
    clearInterval(id)
    pollIntervals.delete(trackId)
  }
}

function startPolling(trackId: string, jobId: number) {
  stopPolling(trackId)
  const id = window.setInterval(async () => {
    try {
      const res = await api(`/api/analysis/training/${jobId}/`)
      if (!res.ok) return
      const job: BackendTrainingJob = await res.json()
      const t = tracks.value.find((x) => x.id === trackId)
      if (!t) {
        stopPolling(trackId)
        return
      }
      if (job.status === 'running' || job.status === 'pending') {
        t.active_job = jobToActiveJob(job, t)
      } else {
        // Terminal: completed / failed / cancelled. Clear job slot and stop.
        t.active_job = null
        stopPolling(trackId)
        if (job.status === 'completed') {
          formMessage.value = `Training completed for ${t.label}.`
          // Refresh model list so the new version appears.
          await refreshModels()
        } else if (job.status === 'failed') {
          formMessage.value = `Training failed: ${job.error_message || 'unknown error'}`
        }
      }
    } catch {
      // transient network errors are silent; next tick will retry
    }
  }, 2000)
  pollIntervals.set(trackId, id)
}

async function refreshModels() {
  try {
    const res = await api('/api/analysis/models/?module=pollinators')
    if (!res.ok) return
    const versions: BackendModelVersion[] = await res.json()
    const rebuilt = tracksFromVersions(versions)
    // Merge: preserve any active_job + data_pool already on each track.
    for (const t of tracks.value) {
      const fresh = rebuilt.find((r) => r.id === t.id)
      if (fresh) {
        t.versions = fresh.versions.map((v) => ({
          ...v,
          samples: 0,
          training_duration_seconds: 0,
          charts: null,
        }))
        t.active_version_id = fresh.active_version_id
      }
    }
  } catch {
    // ignore — next manual reload will fetch again
  }
}

function cancelJob(track: Track) {
  // Client-side dismissal only. Backend has no cancel endpoint yet; the
  // job keeps running and produces a ModelVersion on completion.
  track.active_job = null
  stopPolling(track.id)
}

onUnmounted(() => {
  for (const id of pollIntervals.values()) clearInterval(id)
  pollIntervals.clear()
})

function toggleHistory(id: number) {
  const next = new Set(expandedHistory.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedHistory.value = next
}

function chartsForJob(job: HistoryEntry): ChartData | null {
  for (const t of tracks.value) {
    const v = t.versions.find((x) => x.version_name === job.version_name)
    if (v?.charts) return v.charts
  }
  return null
}

const CLASS_GLYPHS: Record<string, string> = {
  fly: '🪰',
  bumblebee: '🐝',
  butterfly: '🦋',
  other: '?',
  insect: '🪰',
  background: '·',
}

function addFile(f: File) {
  // Filter out non-image entries when a folder is dropped — folders often
  // contain stray .DS_Store, JSON, etc. Accept the extensions in the
  // <input accept> list.
  const name = f.name.toLowerCase()
  if (!/\.(jpe?g|png|zip)$/.test(name)) return
  uploadedFiles.value.push({ name: f.name, size: f.size })
}

function removeUpload(idx: number) {
  uploadedFiles.value.splice(idx, 1)
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function openReviewDrawer() {
  if (!selectedTrack.value) return
  drawerFilter.value = 'all'
  reviewDrawerOpen.value = true
}

// Per-run exclusion set. Click a sample card in the drawer to exclude it
// from this training job; default is everything included. Backed by a
// reactive Set so toggles re-render the grid.
//
// TODO(backend): wire this into the POST payload as `detection_ids` (or
// `image_ids` for the detector track) once /api/pollinator/training/pool/
// exposes real per-sample IDs. Today the drawer renders placeholder
// thumbnails with synthetic IDs, so the toggle is visual only.
const excludedSampleIds = reactive(new Set<string>())

function toggleSampleInclusion(id: string) {
  if (excludedSampleIds.has(id)) excludedSampleIds.delete(id)
  else excludedSampleIds.add(id)
}

function selectAllSamples() {
  excludedSampleIds.clear()
}

function deselectAllSamples() {
  for (const t of drawerThumbnails.value) excludedSampleIds.add(t.id)
}

const drawerIncludedCount = computed(
  () => drawerThumbnails.value.filter((t) => !excludedSampleIds.has(t.id)).length,
)

const drawerClasses = computed(() => {
  if (!selectedTrack.value) return [{ value: 'all', label: 'All' }]
  const classes = Object.keys(selectedTrack.value.data_pool.by_class)
  return [
    { value: 'all', label: 'All' },
    ...classes.map((c) => ({
      value: c,
      label: c[0].toUpperCase() + c.slice(1),
    })),
  ]
})

const drawerThumbnails = computed(() => {
  if (!selectedTrack.value) return []
  const balance = selectedTrack.value.data_pool.by_class
  const filter = drawerFilter.value
  const result: Array<{
    id: string
    label: string
    glyph: string
    color: string
    bg: string
  }> = []
  for (const [cls, count] of Object.entries(balance)) {
    if (filter !== 'all' && filter !== cls) continue
    const visible = Math.min(count, 30)
    for (let i = 0; i < visible; i++) {
      result.push({
        id: `${cls}-${i}`,
        label: cls,
        glyph: CLASS_GLYPHS[cls] ?? '?',
        color: CLASS_COLORS[cls] ?? '#9aa3ab',
        bg: (CLASS_COLORS[cls] ?? '#9aa3ab') + '14',
      })
    }
  }
  return result
})

async function startTraining() {
  if (!canSubmit.value || !selectedTrack.value) return
  const t = selectedTrack.value

  // Preview mode: keep the existing offline mock so the design preview still
  // works without a backend.
  if (previewMode.value) {
    t.active_job = {
      id: Date.now(),
      version_name: `${t.id}-${(t.versions.length + 1).toString().padStart(2, '0')} (in progress)`,
      mode: 'incremental',
      started_at: new Date().toISOString(),
      estimated_total_seconds: Math.round((t.data_pool.total_samples * settings.epochs) / 12),
      current_epoch: 0,
      total_epochs: settings.epochs,
      loss: 0,
      val_accuracy: 0,
    }
    return
  }

  const apiTrack = UI_TO_API_TRACK[t.id]
  if (!apiTrack) {
    formMessage.value = `Unknown track: ${t.id}`
    return
  }
  if (t.active_version_id == null) {
    formMessage.value = `${t.label} has no active version to retrain from.`
    return
  }

  formMessage.value = 'Submitting training job…'
  try {
    const res = await api('/api/pollinator/training/', {
      method: 'POST',
      body: JSON.stringify({
        name: `${t.id} retrain (${new Date().toISOString().slice(0, 10)})`,
        config: {
          track: apiTrack,
          from_model_version_id: t.active_version_id,
          epochs: settings.epochs,
          train_split: settings.train_split,
          val_split: settings.val_split,
          test_split: settings.test_split,
          stratified: settings.stratified,
          ...(trackHasClassFilter.value ? { class_filter: Array.from(classFilter) } : {}),
          ...(trackHasImgSize.value ? { img_size: imgSize.value } : {}),
        },
      }),
    })
    if (!res.ok) {
      formMessage.value = (await res.text()) || `HTTP ${res.status}`
      return
    }
    const job: BackendTrainingJob = await res.json()
    t.active_job = jobToActiveJob(job, t)
    startPolling(t.id, job.id)
    formMessage.value = ''
  } catch (e) {
    formMessage.value = e instanceof Error ? e.message : String(e)
  }
}
</script>

<style scoped>
.drawer-enter-active aside,
.drawer-leave-active aside {
  transition: transform 220ms ease;
}
.drawer-enter-from aside,
.drawer-leave-to aside {
  transform: translateX(100%);
}
.drawer-enter-active > div:first-child,
.drawer-leave-active > div:first-child {
  transition: opacity 220ms ease;
}
.drawer-enter-from > div:first-child,
.drawer-leave-to > div:first-child {
  opacity: 0;
}
</style>
