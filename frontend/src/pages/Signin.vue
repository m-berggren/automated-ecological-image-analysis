<template>
  <div class="min-h-screen flex items-center justify-center bg-background px-6">
    <div class="w-full max-w-sm">
      <div class="flex items-center gap-2 justify-center mb-8">
        <Sprout class="w-6 h-6 text-primary" />
        <span class="font-display font-bold text-xl tracking-tight">Ecosia</span>
      </div>
      <div class="rounded-xl border border-border bg-surface p-8 shadow-sm">
        <h1 class="font-display font-semibold text-lg mb-1">Sign in</h1>
        <p class="text-sm text-muted-foreground mb-6">
          Access the ecological image analysis tool.
        </p>
        <SignInForm />
      </div>
      <p class="text-sm text-muted-foreground text-center mt-6">
        Don't have an account?
        <RouterLink to="/signup" class="text-primary font-medium hover:underline">
          Create one
        </RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Sprout } from 'lucide-vue-next'
import SignInForm from '@/components/SignInForm.vue'
</script>
