<template>
  <div class="min-h-screen flex flex-col justify-center items-center px-6">
    <h2 class="text-3xl font-extrabold mb-8 text-green-900">Sign Up</h2>

    <form @submit.prevent="submitSignup" class="w-full max-w-sm">

      <!-- Username -->
      <input
        v-model="username"
        type="text"
        placeholder="Username"
        required
        class="mb-4 w-full p-3 rounded-md border border-green-300 focus:outline-none focus:ring-2 focus:ring-green-400"
      />

      <!-- Email -->
      <input
        v-model="email"
        type="email"
        placeholder="Email"
        required
        class="mb-4 w-full p-3 rounded-md border border-green-300 focus:outline-none focus:ring-2 focus:ring-green-400"
      />

      <!-- Password -->
      <div class="relative mb-2">
        <input
          v-model="password"
          :type="showPassword ? 'text' : 'password'"
          placeholder="Password"
          required
          class="w-full p-3 rounded-md border border-green-300 focus:outline-none focus:ring-2 focus:ring-green-400"
        />

        <span
          @click="showPassword = !showPassword"
          class="absolute right-3 top-3 cursor-pointer select-none"
        >
          👁
        </span>
      </div>

      <!-- Password Strength -->
      <div class="mb-4">
        <div class="h-2 w-full bg-gray-200 rounded">
          <div
            class="h-2 rounded transition-all"
            :class="strengthColor"
            :style="{ width: strengthWidth }"
          ></div>
        </div>
        <p class="text-sm mt-1 text-gray-600">{{ strengthText }}</p>
      </div>

      <!-- Confirm Password -->
      <input
        v-model="confirmPassword"
        :type="showPassword ? 'text' : 'password'"
        placeholder="Confirm Password"
        required
        class="mb-6 w-full p-3 rounded-md border border-green-300 focus:outline-none focus:ring-2 focus:ring-green-400"
      />

      <p v-if="passwordMismatch" class="text-red-600 text-sm mb-3">
        Passwords do not match
      </p>

      <button
        type="submit"
        class="w-full bg-green-700 text-white py-3 rounded-lg font-semibold hover:bg-green-600"
      >
        Create Account
      </button>
    </form>

    <p class="mt-4 text-green-800">
      Already have an account?
      <router-link to="/" class="underline hover:text-green-600">
        Log In
      </router-link>
    </p>

    <p v-if="errorMessage" class="mt-2 text-red-600 font-semibold">
      {{ errorMessage }}
    </p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')

const showPassword = ref(false)
const errorMessage = ref('')

/* Password Match */
const passwordMismatch = computed(() => {
  return confirmPassword.value && password.value !== confirmPassword.value
})

/* Password Strength */
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
      return 'Weak 🔴'
    case 2:
      return 'Medium 🟠'
    case 3:
      return 'Strong 🟡'
    case 4:
      return 'Very Strong 🟢'
    default:
      return ''
  }
})

const strengthWidth = computed(() => {
  return (strengthScore.value * 25) + '%'
})

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
      return 'bg-gray-300'
  }
})

async function submitSignup() {
  errorMessage.value = ''

  if (passwordMismatch.value) {
    errorMessage.value = 'Password does not match'
    return
  }

  try {
    const res = await fetch('http://localhost:8000/api/auth/register/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        email: email.value,
        password: password.value
      }),
    })

    const data = await res.json()

    if (res.ok) {
      router.push('/')
    } else {
      errorMessage.value = data.error || 'Signup failed'
    }
  } catch {
    errorMessage.value = 'Network error'
  }
}
</script>