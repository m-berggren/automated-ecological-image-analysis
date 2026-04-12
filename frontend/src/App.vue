<script setup lang="ts"></script>

<template>
  <div>
    <RouterView />
  </div>
</template>

<!-- Checks the authetication status -->
<script setup lang="ts">
import { onMounted } from "vue"
import { useAuthStore } from "@/stores/auth"

const auth = useAuthStore()

onMounted(() => {
  auth.checkAuth()
})
</script>