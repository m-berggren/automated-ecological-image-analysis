<template>
  <div class="flex h-screen bg-background text-foreground overflow-hidden">
    <aside
      class="flex flex-col shrink-0 border-r border-border bg-surface transition-[width] duration-150"
      :class="collapsed ? 'w-14' : 'w-58'"
    >
      <div
        class="flex items-center h-16 border-b border-border"
        :class="collapsed ? 'justify-center px-2' : 'px-3 gap-2'"
      >
        <RouterLink to="/" class="flex items-center gap-2 min-w-0">
          <Sprout class="w-6 h-6 text-primary shrink-0" />
          <span v-if="!collapsed" class="font-display font-bold text-xl tracking-tight truncate">
            {{ appName }}
          </span>
        </RouterLink>
        <button
          v-if="!collapsed"
          @click="toggleCollapsed"
          class="ml-auto p-1 rounded hover:bg-muted text-muted-foreground shrink-0"
          title="Collapse sidebar"
        >
          <ChevronLeft class="w-4 h-4" />
        </button>
      </div>

      <nav class="flex-1 py-4 space-y-0.5" :class="collapsed ? 'px-1.5' : 'px-2'">
        <div v-for="item in modules" :key="item.to">
          <component
            :is="item.children ? 'button' : RouterLink"
            :to="item.to"
            @click="item.children ? onParentClick(item) : null"
            class="w-full flex items-center gap-3 py-2 rounded-lg text-sm font-medium transition-colors text-left"
            :class="[
              collapsed ? 'justify-center px-0' : 'justify-between px-3',
              isModuleActive(item) && !item.children ? 'nav-active' : 'hover:bg-muted',
              item.paused ? 'text-muted-foreground' : '',
            ]"
            :title="collapsed ? item.label : ''"
          >
            <span class="flex items-center gap-3 min-w-0">
              <component :is="item.icon" class="w-4 h-4 shrink-0" />
              <span v-if="!collapsed" class="truncate">{{ item.label }}</span>
            </span>
            <template v-if="!collapsed">
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
            </template>
          </component>

          <!-- Child rows only render when the sidebar is expanded. In
               collapsed mode, clicking the parent navigates to its first
               child instead (see onParentClick). -->
          <div
            v-if="!collapsed && item.children && isModuleExpanded(item)"
            class="mt-0.5 ml-7 space-y-0.5"
          >
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

      <div class="border-t border-border p-3 space-y-2">
        <div v-if="auth.isLoggedIn">
          <div class="flex items-center" :class="collapsed ? 'justify-center' : 'justify-between'">
            <div class="flex items-center gap-2 min-w-0">
              <div
                class="w-8 h-8 rounded-full bg-primary/15 text-primary font-semibold flex items-center justify-center shrink-0"
                :title="collapsed ? (auth.user?.username ?? '') : ''"
              >
                {{ initial }}
              </div>
              <span v-if="!collapsed" class="text-sm font-medium truncate">
                {{ auth.user?.username }}
              </span>
            </div>
            <button
              v-if="!collapsed"
              @click="handleLogout"
              class="p-1.5 rounded hover:bg-muted text-muted-foreground"
              title="Sign out"
            >
              <LogOut class="w-4 h-4" />
            </button>
          </div>
          <button
            v-if="collapsed"
            @click="handleLogout"
            class="mt-2 w-full p-1.5 rounded hover:bg-muted text-muted-foreground flex justify-center"
            title="Sign out"
          >
            <LogOut class="w-4 h-4" />
          </button>
        </div>
        <div v-else class="flex flex-col gap-1.5">
          <RouterLink
            v-if="!collapsed"
            to="/signin"
            class="w-full text-center px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90"
          >
            Sign in
          </RouterLink>
          <RouterLink
            v-if="!collapsed"
            to="/signup"
            class="w-full text-center px-3 py-1.5 rounded-md text-sm font-medium border border-border hover:bg-muted"
          >
            Create account
          </RouterLink>
        </div>
        <button
          v-if="collapsed"
          @click="toggleCollapsed"
          class="w-full p-1.5 rounded hover:bg-muted text-muted-foreground flex justify-center"
          title="Expand sidebar"
        >
          <ChevronRight class="w-4 h-4" />
        </button>
      </div>
    </aside>

    <main class="flex-1 min-w-0 min-h-0 flex flex-col">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  Sprout,
  Microscope,
  Bug,
  LogOut,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
} from 'lucide-vue-next'

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

// Sidebar collapse state, persisted across reloads. Stored as '1'/'0' to
// avoid any JSON-parse surprises if a manual edit goes through.
const COLLAPSED_KEY = 'sidebar:collapsed'
const collapsed = ref(
  typeof localStorage !== 'undefined' && localStorage.getItem(COLLAPSED_KEY) === '1',
)
watch(collapsed, (v) => {
  try {
    localStorage.setItem(COLLAPSED_KEY, v ? '1' : '0')
  } catch {
    // localStorage may be unavailable (private mode quotas, etc); ignore.
  }
})
function toggleCollapsed() {
  collapsed.value = !collapsed.value
}

const modules: ModuleItem[] = [
  {
    to: '/seeds',
    label: 'Seeds',
    icon: Microscope,
    children: [
      { to: '/seeds/upload', label: 'Upload' },
      { to: '/seeds/runs', label: 'Runs' },
      { to: '/seeds/training', label: 'Training' },
      { to: '/seeds/models', label: 'Models' },
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
      { to: '/pollinators/settings', label: 'Settings' },
    ],
  },
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
  const wasExpanded = isModuleExpanded(item)
  for (const m of modules) {
    if (m.children && m.to !== item.to) expandedOverride[m.to] = false
  }
  if (wasExpanded) {
    expandedOverride[item.to] = false
    return
  }
  expandedOverride[item.to] = true
  const first = item.children.find((c) => !isChildDisabled(c))
  if (first && route.path !== first.to) router.push(first.to)
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
