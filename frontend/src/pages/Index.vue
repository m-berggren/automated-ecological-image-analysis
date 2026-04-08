<!-- Author: Claudia Sevilla -->

<template>
  <div class="min-h-screen">
  <BlobDecoration />
    <SideBoxes />
    <NavBar />

    <!-- Hero Section -->
    <section class="relative z-10 pt-8 md:pt-12 pb-8 px-6 md:px-12 max-w-3xl mx-auto text-center">
      <div class="relative inline-block mb-4 md:mb-6">
        <TypingTitle />
        <BoundingBoxDecor color="pink" class="w-20 h-8 -top-3 -right-6 opacity-40" />
        <BoundingBoxDecor color="cyan" class="w-14 h-6 -bottom-2 -left-4 opacity-30" />
      </div>
      <p class="text-muted-foreground text-sm md:text-base lg:text-lg max-w-xl mx-auto font-body leading-relaxed">
        Upload images of pollinators or pollen samples. Our models identify species and count specimens in seconds.
      </p>
    </section>

    <!-- Stats Section -->
    <section class="relative z-10 max-w-5xl mx-auto px-6 md:px-12 py-4">
      <div class="grid grid-cols-3 divide-x divide-border/40 border border-border/40 rounded-2xl overflow-hidden bg-white/40 backdrop-blur-sm">
        <div
          v-for="stat in stats"
          :key="stat.label"
          class="flex flex-col items-center gap-2 py-6 px-4"
        >
          <div :class="`w-10 h-10 rounded-full flex items-center justify-center ${stat.iconBg}`">
            <component :is="stat.icon" :class="`w-5 h-5 ${stat.iconColor}`" />
          </div>
          <div class="text-center">
            <div :class="`font-display font-bold text-3xl md:text-4xl leading-none ${stat.valueColor}`">{{ stat.value }}</div>
            <div class="text-xs text-muted-foreground uppercase tracking-widest mt-1">{{ stat.label }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Category Intro 01 -->
    <section class="relative z-10 max-w-5xl mx-auto px-6 md:px-12 pt-12 pb-2 text-left">
      <div class="flex flex-col md:flex-row items-start md:items-end justify-between gap-4 border-b border-border/40 pb-6">
        <div class="flex items-end gap-6">
          <span class="font-display font-bold text-6xl md:text-8xl text-primary/10 leading-none select-none">01</span>
          <div>
            <h2 class="font-display font-bold text-2xl md:text-3xl text-foreground leading-tight">
              Pick your category
            </h2>
            <p class="text-sm text-muted-foreground font-body mt-1">
              What are you analysing today?
            </p>
          </div>
        </div>
        <div class="flex items-center gap-2 text-xs text-muted-foreground font-body animate-bbox-pulse">
          <span class="w-2 h-2 rounded-full bg-bbox-lime inline-block" />
          Model Ready
        </div>
      </div>
    </section>

    <!-- Choose Category Buttons -->
    <CategorySelector v-model="activeCategory" />

    <!-- Upload Section 02 -->
    <section class="relative z-10 max-w-5xl mx-auto px-6 md:px-12 pt-12 pb-2 text-left">
      <div class="flex flex-col md:flex-row items-start md:items-end justify-between gap-4 border-b border-border/40 pb-6">
        <div class="flex items-end gap-6">
          <span class="font-display font-bold text-6xl md:text-8xl text-primary/10 leading-none select-none">02</span>
          <div>
            <h2 class="font-display font-bold text-2xl md:text-3xl text-foreground leading-tight">
              Upload your image
            </h2>
            <p class="text-sm text-muted-foreground font-body mt-1">
              JPG, PNG or WEBP
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- Image Upload Card -->
    <ImageUploadCard :type="activeCategory" />

    <!-- Footer -->
    <footer class="relative z-10 border-t border-border mt-20 py-6 px-6 text-center">
      <p class="text-xs text-muted-foreground font-body">
        Ecosia • Automated Ecological Image Analysis
      </p>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import NavBar from '../components/NavBar.vue'
import BlobDecoration from '../components/BlobDecoration.vue'
import TypingTitle from '../components/TypingTitle.vue'
import BoundingBoxDecor from '../components/BoundingBoxDecor.vue';
import CategorySelector from '../components/CategorySelector.vue';
import ImageUploadCard from '../components/ImageUploadCard.vue';

import { Locate, Clock, CheckCheck } from 'lucide-vue-next'
import SideBoxes from '../components/SideBoxes.vue';

type Category = 'pollinator' | 'pollen' | 'seeds' | 'flowers'
const activeCategory = ref<Category>('pollinator')
const stats = [
  { value: '50+', label: 'Pollinator species', icon: Locate, iconBg: 'bg-eco-mint', iconColor: 'text-eco-forest', valueColor: 'text-eco-forest' },
  { value: '< 3s', label: 'Analysis time', icon: Clock, iconBg: 'bg-blue-100', iconColor: 'text-blue-600', valueColor: 'text-blue-600' },
  { value: '95%', label: 'Accuracy', icon: CheckCheck, iconBg: 'bg-lime-100', iconColor: 'text-lime-700', valueColor: 'text-lime-700' },
]

</script>