<template>
  <form @submit.prevent="submitSignup" class="space-y-4">
    <div>
      <label for="signup-username" class="block text-sm font-medium mb-1.5">Username</label>
      <input
        id="signup-username"
        v-model="username"
        type="text"
        required
        autocomplete="username"
        class="w-full px-3 py-2 rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
      />
    </div>
    <div>
      <label for="signup-email" class="block text-sm font-medium mb-1.5">Email</label>
      <input
        id="signup-email"
        v-model="email"
        type="email"
        required
        autocomplete="email"
        class="w-full px-3 py-2 rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
      />
    </div>
    <div>
      <label for="signup-password" class="block text-sm font-medium mb-1.5">Password</label>
      <div class="relative">
        <input
          id="signup-password"
          v-model="password"
          :type="showPassword ? 'text' : 'password'"
          required
          autocomplete="new-password"
          class="w-full px-3 py-2 pr-10 rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
        />
        <button
          type="button"
          @click="showPassword = !showPassword"
          class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
          :aria-label="showPassword ? 'Hide password' : 'Show password'"
        >
          <component :is="showPassword ? EyeOff : Eye" class="w-4 h-4" />
        </button>
      </div>
      <div v-if="password" class="mt-2">
        <div class="h-1 w-full bg-muted rounded overflow-hidden">
          <div
            class="h-full transition-all"
            :class="strengthColor"
            :style="{ width: strengthWidth }"
          />
        </div>
        <p class="text-xs mt-1 text-muted-foreground">{{ strengthText }}</p>
      </div>
    </div>
    <div>
      <label for="signup-confirm" class="block text-sm font-medium mb-1.5">Confirm password</label>
      <input
        id="signup-confirm"
        v-model="confirmPassword"
        :type="showPassword ? 'text' : 'password'"
        required
        autocomplete="new-password"
        class="w-full px-3 py-2 rounded-md border border-border bg-background focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary"
      />
      <p v-if="passwordMismatch" class="text-xs text-red-600 mt-1.5">Passwords do not match</p>
    </div>
    <button
      type="submit"
      class="w-full bg-primary text-primary-foreground py-2.5 rounded-md font-medium hover:bg-primary/90 transition-colors"
    >
      Create account
    </button>
    <p v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</p>
  </form>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Eye, EyeOff } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { tokenManager } from '@/lib/token'
import { API_BASE_URL } from '@/lib/config'
const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const showPassword = ref(false)
const errorMessage = ref('')

const passwordMismatch = computed(
  () => !!confirmPassword.value && password.value !== confirmPassword.value,
)

const strengthScore = computed(() => {
  let score = 0
  if (password.value.length >= 8) score++
  if (/[A-Z]/.test(password.value)) score++
  if (/[0-9]/.test(password.value)) score++
  if (/[^A-Za-z0-9]/.test(password.value)) score++
  return score
})

const strengthText = computed(() => {
  switch (strengthScore.value) {
    case 0:
    case 1:
      return 'Weak'
    case 2:
      return 'Medium'
    case 3:
      return 'Strong'
    case 4:
      return 'Very strong'
    default:
      return ''
  }
})

const strengthWidth = computed(() => `${strengthScore.value * 25}%`)

const strengthColor = computed(() => {
  switch (strengthScore.value) {
    case 1:
      return 'bg-red-500'
    case 2:
      return 'bg-orange-500'
    case 3:
      return 'bg-yellow-500'
    case 4:
      return 'bg-green-500'
    default:
      return 'bg-muted'
  }
})

async function submitSignup() {
  errorMessage.value = ''
  if (passwordMismatch.value) {
    errorMessage.value = 'Passwords do not match'
    return
  }
  try {
    const res = await fetch(`${API_BASE_URL}/api/auth/register/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        email: email.value,
        password: password.value,
      }),
    })
    const data = await res.json()
    if (res.ok) {
      tokenManager.set(data.access, data.refresh)
      auth.syncFromToken()
      router.push('/')
    } else {
      errorMessage.value = data.error || 'Signup failed'
    }
  } catch {
    errorMessage.value = 'Network error'
  }
}
</script>
