import { defineStore } from "pinia"
import { api } from "../api"

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: null as null | { username: string }
  }),

  getters: {
    isLoggedIn: (state) => !!state.user
  },

  actions: {
    async checkAuth() {
      try {
        const res = await api("/api/auth/me/")

        if (!res.ok) {
          this.user = null
          return
        }

        const data = await res.json()
        this.user = data.user ?? null
      } catch (err) {
        this.user = null
        console.error("Auth check failed:", err)
      }
    },

    async logout() {
      await api("/api/auth/logout/", { method: "POST" })

      localStorage.removeItem("token")
      this.user = null
    }
  }
})