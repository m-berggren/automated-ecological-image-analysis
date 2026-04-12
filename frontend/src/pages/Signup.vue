<template>
  <div class="min-h-screen">
    <BlobDecoration />
    <SideBoxes />
    <NavBar />
      <RegistrationForm class="mt-10 mx-auto max-w-md" />


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
