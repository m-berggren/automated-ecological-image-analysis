<template>
  <div class="min-h-screen flex flex-col justify-center items-center px-6">
    <h2 class="text-3xl font-extrabold mb-8 text-green-900">Sign Up</h2>
    <form @submit.prevent="submitSignup" class="w-full max-w-sm">
      <input
        v-model="username"
        type="text"
        placeholder="Username"
        required
        class="mb-4 w-full p-3 rounded-md border border-green-300 focus:outline-none focus:ring-2 focus:ring-green-400"
      />
      <input
        v-model="password"
        type="password"
        placeholder="Password"
        required
        class="mb-6 w-full p-3 rounded-md border border-green-300 focus:outline-none focus:ring-2 focus:ring-green-400"
      />
      <button
        type="submit"
        class="w-full bg-green-700 text-white py-3 rounded-lg font-semibold hover:bg-green-600"
      >
        Create Account
      </button>
    </form>
    <p class="mt-4 text-green-800">
      Already have an account?
      <router-link to="/" class="underline hover:text-green-600">Log In</router-link>
    </p>
    <p v-if="errorMessage" class="mt-2 text-red-600 font-semibold">{{ errorMessage }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('')
const password = ref('')
const errorMessage = ref('')

async function submitSignup() {
  errorMessage.value = ''
  try {
    const res = await fetch('http://localhost:8000/api/auth/register/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username.value,
        password: password.value,
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
