<!-- Author: Claudia Sevilla -->

<template>
  <nav class="relative z-10 flex items-center justify-between px-6 md:px-12 py-5">
    <RouterLink to="/" class="flex items-center gap-2 mt-2">
      <Sprout class="w-5 h-5 md:w-7 md:h-7 text-primary" />
      <span class="font-display font-bold text-2xl md:text-4xl text-foreground tracking-tight">
        ecosia
      </span>
    </RouterLink>
    <div v-if="!auth.isLoggedIn" class="flex items-center gap-2 mt-2">
      <RouterLink
        to="/signin"
        class="px-4 py-1.5 rounded-lg text-sm font-semibold bg-secondary text-secondary-foreground hover:bg-secondary/70 transition-colors"
      >
        Sign In
      </RouterLink>
      <RouterLink
        to="/signup"
        class="px-4 py-1.5 rounded-lg text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/80 transition-colors"
      >
        Sign Up
      </RouterLink>
    </div>
    <!-- Logged in -->
    <div v-else class="relative group mt-2">

      <!-- Username -->
      <div class="cursor-pointer px-4 py-2 rounded-lg font-semibold hover:bg-muted">
        {{ auth.user?.username }} ▾
      </div>

      <!-- Dropdown -->
      <div
        class="absolute right-0 top-full w-40 bg-white text-black rounded-lg shadow-lg
               opacity-0 invisible group-hover:opacity-100 group-hover:visible
               transition duration-150"
      >
        <button
          @click="logout"
          class="block w-full text-left px-4 py-2 hover:bg-gray-100"
        >
          Logout
        </button>
      </div>

    </div>
  </nav>
</template>

<script setup lang="ts">
import { Sprout } from 'lucide-vue-next'
import { useAuthStore } from "../stores/auth"
import { useRouter } from "vue-router"


const auth = useAuthStore()
const router = useRouter()


async function logout() {
  await auth.logout()
  router.push("/signin")
}
</script>
