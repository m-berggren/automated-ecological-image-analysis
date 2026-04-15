<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <aside
      class="flex flex-col w-60 shrink-0 border-r border-border bg-surface"
    >
      <RouterLink
        to="/"
        class="flex items-center gap-2 px-5 h-16 border-b border-border"
      >
        <Sprout class="w-6 h-6 text-primary" />
        <span class="font-display font-bold text-xl tracking-tight">
          {{ appName }}
        </span>
      </RouterLink>

      <nav class="flex-1 py-4 px-2 space-y-0.5">
        <RouterLink
          v-for="item in modules"
          :key="item.to"
          :to="item.to"
          class="flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
          active-class="nav-active"
          :class="item.paused ? 'text-muted-foreground' : 'hover:bg-muted'"
        >
          <span class="flex items-center gap-3">
            <component :is="item.icon" class="w-4 h-4" />
            {{ item.label }}
          </span>
          <span
            v-if="item.paused"
            class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
          >
            paused
          </span>
        </RouterLink>
      </nav>

      <div class="border-t border-border p-3">
        <div v-if="auth.isLoggedIn" class="flex items-center justify-between">
          <div class="flex items-center gap-2 min-w-0">
            <div
              class="w-8 h-8 rounded-full bg-primary/15 text-primary font-semibold flex items-center justify-center shrink-0"
            >
              {{ initial }}
            </div>
            <span class="text-sm font-medium truncate">
              {{ auth.user?.username }}
            </span>
          </div>
          <button
            @click="handleLogout"
            class="p-1.5 rounded hover:bg-muted text-muted-foreground"
            title="Sign out"
          >
            <LogOut class="w-4 h-4" />
          </button>
        </div>
        <div v-else class="flex flex-col gap-1.5">
          <RouterLink
            to="/signin"
            class="w-full text-center px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90"
          >
            Sign in
          </RouterLink>
          <RouterLink
            to="/signup"
            class="w-full text-center px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted"
          >
            Create account
          </RouterLink>
        </div>
      </div>
    </aside>

    <main class="flex-1 min-w-0 flex flex-col">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Sprout,
  Microscope,
  Bug,
  Flower2,
  Sparkles,
  LogOut,
} from 'lucide-vue-next'

const auth = useAuthStore()
const router = useRouter()

const appName = 'Ecosia'

const modules = [
  { to: '/seeds', label: 'Seeds', icon: Microscope, paused: false },
  { to: '/pollinators', label: 'Pollinators', icon: Bug, paused: false },
  { to: '/pollen', label: 'Pollen', icon: Sparkles, paused: true },
  { to: '/flowers', label: 'Flowers', icon: Flower2, paused: true },
]

const initial = computed(() =>
  (auth.user?.username ?? '?').charAt(0).toUpperCase(),
)

async function handleLogout() {
  await auth.logout()
  router.push('/signin')
}
</script>

<style scoped>
.nav-active {
  background-color: color-mix(in srgb, var(--color-primary) 12%, transparent);
  color: var(--color-primary);
}
</style>
