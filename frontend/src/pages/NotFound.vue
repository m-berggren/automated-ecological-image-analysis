<template>
  <div class="min-h-screen flex items-center justify-center bg-background px-6">
    <div class="max-w-md text-center space-y-6">
      <div class="space-y-2">
        <h1 class="text-6xl font-bold tracking-tight text-primary">404</h1>
        <h2 class="text-2xl font-semibold">Page not found</h2>
      </div>

      <div class="flex items-center justify-center gap-3">
        <button
          @click="$router.back()"
          class="px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted transition"
        >
          Go back
        </button>
      </div>
    </div>
  </div>
</template>