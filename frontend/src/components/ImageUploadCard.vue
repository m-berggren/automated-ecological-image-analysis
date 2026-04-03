<!-- Author: Claudia Sevilla -->
<!-- Ported from Lovable's React prototype -->

<template>
  <section class="relative z-10 max-w-3xl mx-auto px-6 md:px-12 py-8">
    <div class="relative w-full max-w-lg mx-auto">

      <!-- Upload Zone -->
      <div
        v-if="!image"
        @dragover.prevent="isDragOver = true"
        @dragleave="isDragOver = false"
        @drop="handleDrop"
        @click="fileInputRef?.click()"
        :class="cn(
          'relative cursor-pointer border-2 border-dashed rounded-2xl p-12 text-center transition-all duration-300',
          isDragOver
            ? 'border-accent bg-accent/10 scale-[1.02]'
            : 'border-border hover:border-primary/40 hover:bg-card/80'
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
      </div>

      <!-- Image Preview -->
      <div
        v-if="image"
        class="relative rounded-xl overflow-hidden bg-card border border-border"
      >
        <!-- Clear button -->
        <button
          @click="clear"
          class="absolute top-3 right-3 z-20 w-8 h-8 rounded-full bg-foreground/80 flex items-center justify-center hover:bg-foreground transition-colors"
        >
          <X class="w-4 h-4 text-background" />
        </button>

        <img :src="image" alt="Uploaded" class="w-full h-auto object-cover" />
      </div>

    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Upload, X } from 'lucide-vue-next'
import { cn } from '@/lib/utils'

const image = ref<string | null>(null)
const isDragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

const handleFile = (file: File) => {
  if (!file.type.startsWith('image/')) return

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
}
</script>