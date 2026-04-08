<!-- Author: Claudia Sevilla -->
<!-- Design ported from Lovable's React prototype -->

<template>
  <section class="relative z-10 max-w-5xl mx-auto px-6 md:px-12 py-2">
    <div class="relative w-full mx-auto flex flex-col gap-4">

      <!-- Upload Zone -->
      <div
        v-if="!image"
        @dragover.prevent="isDragOver = true"
        @dragleave="isDragOver = false"
        @drop="handleDrop"
        @click="fileInputRef?.click()"
        :class="cn(
          'relative cursor-pointer border-2 border-dashed rounded-2xl p-6 md:p-8 text-center transition-all duration-300',
          isDragOver
            ? 'border-accent bg-accent/10 scale-[1.02]'
            : 'border-border bg-white/50 hover:border-primary/40 hover:bg-card/80'
        )"
      >
        <input
          ref="fileInputRef"
          type="file"
          accept="image/*"
          class="hidden"
          @change="handleInputChange"
        />
        <div class="flex flex-col items-center gap-4">
          <div class="w-16 h-16 rounded-full bg-secondary flex items-center justify-center">
            <Upload class="w-7 h-7 text-primary" />
          </div>
          <div>
            <p class="font-semibold text-foreground">Drop your image here</p>
            <p class="text-sm text-muted-foreground mt-1">or click to browse • JPG, PNG, WEBP</p>
          </div>
        </div>
        <BoundingBoxDecor color="lime" className="w-17 h-10 top-3 right-4 opacity-30" />
        <BoundingBoxDecor color="pink" className="w-12 h-8 bottom-4 left-5 opacity-20" />
      </div>


      <!-- File Preview -->
      <div
        v-if="image"
        class="relative rounded-xl bg-white/70 border border-border px-4 py-3 md:py-5 flex items-center gap-4"
      >
        <!-- Thumbnail -->
        <img :src="image" alt="Preview" class="w-16 h-16 rounded-lg object-cover shrink-0" />

        <!-- File info -->
        <div class="flex flex-col gap-0.5 flex-1 min-w-0">
          <p class="text-sm font-semibold text-foreground truncate">{{ fileName }}</p>
          <p class="text-xs text-muted-foreground">{{ fileSize }}</p>
        </div>

        <!-- Clear button -->
        <button
          @click="clear"
          class="w-8 h-8 rounded-full bg-foreground/10 flex items-center justify-center hover:bg-foreground/20 transition-colors shrink-0"
        >
          <X class="w-4 h-4 text-foreground" />
        </button>
      </div>

      <!-- TODO: Clicking must only be allowed after user has Signed Up / Logged In -->
      <!-- Analyse Button: takes you to results page-->
      <button
        v-if="image"
        class="w-full py-3 mt-2 md:mt-6 rounded-xl bg-primary text-primary-foreground font-semibold text-sm hover:bg-primary/90 transition-colors"
      >
        Analyse Image
      </button>

    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Upload, X } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import BoundingBoxDecor from './BoundingBoxDecor.vue'

const image = ref<string | null>(null)
const fileName = ref('')
const fileSize = ref('')
const isDragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

const handleFile = (file: File) => {
  if (!file.type.startsWith('image/')) return
  fileName.value = file.name
  fileSize.value = formatSize(file.size)
  const reader = new FileReader()
  reader.onload = (e) => {
    image.value = e.target?.result as string
  }
  reader.readAsDataURL(file)
}

const handleDrop = (e: DragEvent) => {
  e.preventDefault()
  isDragOver.value = false
  const file = e.dataTransfer?.files[0]
  if (file) handleFile(file)
}

const handleInputChange = (e: Event) => {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) handleFile(file)
}

const clear = () => {
  image.value = null
  fileName.value = ''
  fileSize.value = ''
}
</script>