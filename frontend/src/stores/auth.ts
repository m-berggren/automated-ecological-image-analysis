import { defineStore } from 'pinia'
import { tokenManager } from '@/lib/token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: tokenManager.isSignedIn()
      ? {
          username: tokenManager.getUsername() ?? '',
          is_staff: tokenManager.isStaff(),
        }
      : (null as null | { username: string; is_staff: boolean }),
  }),

  getters: {
    isLoggedIn: (state) => !!state.user,
  },

  actions: {
    /** Call after login/register sets new tokens. */
    syncFromToken() {
      if (tokenManager.isSignedIn()) {
        this.user = {
          username: tokenManager.getUsername() ?? '',
          is_staff: tokenManager.isStaff(),
        }
      } else {
        this.user = null
      }
    },

    /** Legacy — kept for router guard. No HTTP call needed anymore. */
    async checkAuth() {
      this.syncFromToken()
    },

    async logout() {
      tokenManager.clear()
      this.user = null
    },
  },
})
