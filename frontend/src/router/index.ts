import { createRouter, createWebHistory } from 'vue-router'
import AppShell from '@/components/AppShell.vue'
import SeedsUpload from '@/pages/SeedsUpload.vue'
import SeedsRuns from '@/pages/SeedsRuns.vue'
import SeedsExport from '@/pages/SeedsExport.vue'
import SeedsModels from '@/pages/SeedsModels.vue'
import PollinatorsUpload from '@/pages/PollinatorsUpload.vue'
import PollinatorsRuns from '@/pages/PollinatorsRuns.vue'
import PollinatorsDetect from '@/pages/PollinatorsDetect.vue'
import PollinatorsReview from '@/pages/PollinatorsReview.vue'
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
        { path: '', redirect: '/seeds/upload' },
        { path: 'seeds', redirect: '/seeds/upload' },
        { path: 'seeds/upload', component: SeedsUpload },
        { path: 'seeds/runs', component: SeedsRuns },
        { path: 'seeds/export', component: SeedsExport },
        { path: 'seeds/models', component: SeedsModels, meta: { staffOnly: true } },
        { path: 'pollinators', redirect: '/pollinators/upload' },
        { path: 'pollinators/upload', component: PollinatorsUpload },
        { path: 'pollinators/runs', component: PollinatorsRuns },
        { path: 'pollinators/runs/:id/detect', component: PollinatorsDetect },
        { path: 'pollinators/runs/:id/review', component: PollinatorsReview },
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
