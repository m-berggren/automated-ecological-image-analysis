import { createRouter, createWebHistory } from 'vue-router'
import Index from '@/pages/Index.vue'
import NotFound from '@/pages/NotFound.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Index },
    { path: '/:pathMatch(.*)*', component: NotFound },
  ],
})

export default router