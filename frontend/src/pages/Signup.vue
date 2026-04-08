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
      <p
        class="text-muted-foreground text-sm md:text-base lg:text-lg max-w-xl mx-auto font-body leading-relaxed"
      >
        Upload images of pollinators or pollen samples. Our models identify species and count
        specimens in seconds.
      </p>
      <RegistrationForm class="mt-10 mx-auto max-w-md" />
    </section>

    <!-- Footer -->
    <footer class="relative z-10 border-t border-border mt-20 py-6 px-6 text-center">
      <p class="text-xs text-muted-foreground font-body">
        Ecosia • Automated Ecological Image Analysis
      </p>
    </footer>
  </div>
</template>

<script setup lang="ts">
import NavBar from '../components/NavBar.vue'
import BlobDecoration from '../components/BlobDecoration.vue'
import TypingTitle from '../components/TypingTitle.vue'
import BoundingBoxDecor from '../components/BoundingBoxDecor.vue'
import RegistrationForm from '../components/RegistrationForm.vue'

import SideBoxes from '../components/SideBoxes.vue'
</script>
