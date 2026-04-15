import { createRouter, createWebHistory } from 'vue-router'
import AppShell from '@/components/AppShell.vue'
import Seeds from '@/pages/Seeds.vue'
import Pollinators from '@/pages/Pollinators.vue'
import Pollen from '@/pages/Pollen.vue'
import Flowers from '@/pages/Flowers.vue'
import NotFound from '@/pages/NotFound.vue'
import Signup from '@/pages/Signup.vue'
import Signin from '@/pages/Signin.vue'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/signin', component: Signin, meta: { public: true } },
    { path: '/signup', component: Signup, meta: { public: true } },
    {
      path: '/',
      component: AppShell,
      children: [
        { path: '', redirect: '/seeds' },
        { path: 'seeds', component: Seeds },
        { path: 'pollinators', component: Pollinators },
        { path: 'pollen', component: Pollen },
        { path: 'flowers', component: Flowers },
      ],
    },
    { path: '/:pathMatch(.*)*', component: NotFound },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const auth = useAuthStore()
  if (auth.user === null) await auth.checkAuth()
  if (!auth.isLoggedIn) return { path: '/signin', query: { next: to.fullPath } }
  return true
})

export default router
