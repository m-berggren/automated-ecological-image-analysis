<template>
  <div class="flex min-h-screen bg-background text-foreground">
    <aside
      class="flex flex-col w-60 shrink-0 border-r border-border bg-surface h-screen sticky top-0"
    >
      <RouterLink to="/" class="flex items-center gap-2 px-5 h-16 border-b border-border">
        <Sprout class="w-6 h-6 text-primary" />
        <span class="font-display font-bold text-xl tracking-tight">
          {{ appName }}
        </span>
      </RouterLink>

      <nav class="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
        <div v-for="item in modules" :key="item.to">
          <component
            :is="item.children ? 'button' : RouterLink"
            :to="item.to"
            @click="item.children ? onParentClick(item) : null"
            class="w-full flex items-center justify-between gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors text-left"
            :class="[
              isModuleActive(item) ? 'nav-active' : 'hover:bg-muted',
              item.paused ? 'text-muted-foreground' : '',
            ]"
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
            <ChevronDown
              v-else-if="item.children"
              class="w-3.5 h-3.5 text-muted-foreground transition-transform"
              :class="{ '-rotate-90': !isModuleExpanded(item) }"
            />
          </component>

          <div v-if="item.children && isModuleExpanded(item)" class="mt-0.5 ml-7 space-y-0.5">
            <RouterLink
              v-for="child in item.children"
              :key="child.to"
              :to="child.to"
              class="flex items-center justify-between px-3 py-1.5 rounded-md text-sm transition-colors"
              :class="[
                isChildActive(child)
                  ? 'nav-active'
                  : isChildDisabled(child)
                    ? 'text-muted-foreground/60 cursor-not-allowed pointer-events-none'
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted',
              ]"
            >
              {{ child.label }}
            </RouterLink>
          </div>
        </div>
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
import { computed, reactive } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Sprout, Microscope, Bug, Flower2, Sparkles, LogOut, ChevronDown } from 'lucide-vue-next'

interface ChildItem {
  to: string
  label: string
  staffOnly?: boolean
}
interface ModuleItem {
  to: string
  label: string
  icon: unknown
  paused?: boolean
  children?: ChildItem[]
}

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const appName = 'Ecosia'

const modules: ModuleItem[] = [
  {
    to: '/seeds',
    label: 'Seeds',
    icon: Microscope,
    children: [
      { to: '/seeds/upload', label: 'Upload' },
      { to: '/seeds/runs', label: 'Runs' },
      { to: '/seeds/training', label: 'Training' },
      { to: '/seeds/models', label: 'Models', staffOnly: true },
      { to: '/seeds/export', label: 'Export' },
    ],
  },
  {
    to: '/pollinators',
    label: 'Pollinators',
    icon: Bug,
    children: [
      { to: '/pollinators/upload', label: 'Upload' },
      { to: '/pollinators/runs', label: 'Runs' },
      { to: '/pollinators/training', label: 'Training' },
      { to: '/pollinators/models', label: 'Models' },
    ],
  },
  { to: '/pollen', label: 'Pollen', icon: Sparkles, paused: true },
  { to: '/flowers', label: 'Flowers', icon: Flower2, paused: true },
]

const expandedOverride = reactive<Record<string, boolean>>({})

function isModuleActive(item: ModuleItem) {
  return route.path === item.to || route.path.startsWith(item.to + '/')
}
function isModuleExpanded(item: ModuleItem) {
  if (item.to in expandedOverride) return expandedOverride[item.to]
  return isModuleActive(item)
}
function isChildDisabled(child: ChildItem) {
  return !!child.staffOnly && !auth.user?.is_staff
}
function isChildActive(child: ChildItem) {
  return route.path === child.to
}
function onParentClick(item: ModuleItem) {
  if (!item.children) return
  if (isModuleActive(item)) {
    expandedOverride[item.to] = !isModuleExpanded(item)
    return
  }
  const first = item.children.find((c) => !isChildDisabled(c))
  if (first) router.push(first.to)
  expandedOverride[item.to] = true
}

const initial = computed(() => (auth.user?.username ?? '?').charAt(0).toUpperCase())

async function handleLogout() {
  await auth.logout()
  router.push('/signin')
}
</script>

<style scoped>
.nav-active {
  background-color: color-mix(in srgb, var(--color-primary) 22%, transparent);
  color: var(--color-primary);
}
</style>
