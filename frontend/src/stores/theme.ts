import { defineStore } from 'pinia'

export type Theme = 'light' | 'dark' | 'green'
const ORDER: Theme[] = ['light', 'dark', 'green']
const STORAGE_KEY = 'theme'

function isTheme(v: unknown): v is Theme {
  return v === 'light' || v === 'dark' || v === 'green'
}

export const useThemeStore = defineStore('theme', {
  state: () => {
    const stored = localStorage.getItem(STORAGE_KEY)
    return { current: (isTheme(stored) ? stored : 'light') as Theme }
  },

  actions: {
    apply() {
      const root = document.documentElement
      root.classList.remove('theme-light', 'theme-dark', 'theme-green')
      root.classList.add(`theme-${this.current}`)
      localStorage.setItem(STORAGE_KEY, this.current)
    },
    cycle() {
      const idx = ORDER.indexOf(this.current)
      this.current = ORDER[(idx + 1) % ORDER.length]
      this.apply()
    },
  },
})
