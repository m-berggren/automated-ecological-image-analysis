<template>
  <form @submit.prevent="submitSignin" class="space-y-4">
    <div>
      <label for="signin-username" class="block text-sm font-medium mb-1.5">Username</label>
      <input
        id="signin-username"
        v-model="username"
        type="text"
        required
        autocomplete="username"
        class="w-full px-3 py-2 rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
      />
    </div>
    <div>
      <label for="signin-password" class="block text-sm font-medium mb-1.5">Password</label>
      <input
        id="signin-password"
        v-model="password"
        type="password"
        required
        autocomplete="current-password"
        class="w-full px-3 py-2 rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
      />
    </div>
    <button
      type="submit"
      class="w-full bg-primary text-primary-foreground py-2.5 rounded-md font-medium hover:bg-primary/90 transition-colors"
    >
      Sign in
    </button>
    <p v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</p>
  </form>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { tokenManager } from '@/lib/token'
import { API_BASE_URL } from '@/lib/config'
const router = useRouter()
const route = useRoute()
const username = ref('')
const password = ref('')
const errorMessage = ref('')
const auth = useAuthStore()

async function submitSignin() {
  errorMessage.value = ''
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        password: password.value,
      }),
    })
    const data = await res.json()
    if (res.ok) {
      tokenManager.set(data.access, data.refresh)
      auth.syncFromToken()
      const next = typeof route.query.next === 'string' ? route.query.next : '/'
      router.push(next)
    } else {
      errorMessage.value = data.detail || 'Invalid credentials'
    }
  } catch {
    errorMessage.value = 'Network error'
  }
}
</script>
