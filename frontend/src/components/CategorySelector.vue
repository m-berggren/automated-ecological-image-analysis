<!-- Author: Claudia Sevilla -->
<!-- Buttons ported from Lovable's React prototype -->
<template>
  <section class="relative z-10 max-w-5xl mx-auto px-6 md:px-12 pb-4">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 justify-center">
      <button
        v-for="cat in categories"
        :key="cat.id"
        @click="$emit('update:modelValue', cat.id)"
        :class="cn(
          'group relative flex flex-col items-center gap-2 px-6 py-5 border-2 transition-all duration-300 w-full',
          modelValue === cat.id
            ? 'border-primary bg-primary/5 shadow-lg shadow-primary/10'
            : 'border-border bg-card/60 hover:border-primary/30 hover:bg-card'
        )"
      >
        <div :class="cn(
          'w-10 h-10 rounded-xl flex items-center justify-center transition-colors',
          modelValue === cat.id ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'
        )">
          <component :is="cat.icon" class="w-5 h-5" />
        </div>
        <span :class="cn(
          'font-semibold text-sm',
          modelValue === cat.id ? 'text-foreground' : 'text-muted-foreground'
        )">
          {{ cat.label }}
        </span>
        <span class="text-xs text-muted-foreground">{{ cat.desc }}</span>
        <BoundingBoxDecor
          v-if="modelValue === cat.id"
          :color="cat.accentColor"
          class="w-full h-full top-0 left-0 opacity-40"
        />
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Bug, Flower2, Leaf, Sprout } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import BoundingBoxDecor from '@/components/BoundingBoxDecor.vue'

type Category = 'pollinator' | 'pollen' | 'seeds' | 'flowers'

defineProps<{
  modelValue: Category
}>()

defineEmits<{
  'update:modelValue': [value: Category]
}>()

const categories = [
  { id: 'pollinator' as Category, label: 'Pollinators', icon: Bug, desc: 'Identify species', accentColor: 'lime' as const },
  { id: 'pollen' as Category, label: 'Pollen', icon: Leaf, desc: 'Count pollen', accentColor: 'orange' as const },
  { id: 'seeds' as Category, label: 'Seeds', icon: Sprout, desc: 'Count seeds', accentColor: 'cyan' as const },
  { id: 'flowers' as Category, label: 'Flowers', icon: Flower2, desc: 'Identify flowers', accentColor: 'pink' as const },
]
</script>