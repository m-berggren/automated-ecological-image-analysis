<template>
  <div class="min-h-screen flex items-center justify-center bg-background px-6">
    <div class="w-full max-w-sm">
      <div class="flex items-center gap-2 justify-center mb-8">
        <Sprout class="w-6 h-6 text-primary" />
        <span class="font-display font-bold text-xl tracking-tight">Ecosia</span>
      </div>
      <div class="relative rounded-xl border border-border bg-surface p-8 shadow-sm">
        <ThemeToggle class="absolute top-2 right-2" />
        <h1 class="font-display font-semibold text-lg mb-1">Create account</h1>
        <p class="text-sm text-muted-foreground mb-6">
          Register to start working with the image analysis modules.
        </p>
        <RegistrationForm />
      </div>
      <p class="text-sm text-muted-foreground text-center mt-6">
        Already have an account?
        <RouterLink to="/signin" class="text-primary font-medium hover:underline">
          Sign in
        </RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Sprout } from 'lucide-vue-next'
import RegistrationForm from '@/components/RegistrationForm.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
</script>
