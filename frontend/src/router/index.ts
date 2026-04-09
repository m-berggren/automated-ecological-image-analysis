import { createRouter, createWebHistory } from 'vue-router'
import Index from '@/pages/Index.vue'
import NotFound from '@/pages/NotFound.vue'
import Signup from '@/pages/Signup.vue'
import Signin from '@/pages/Signin.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Index },
    { path: '/signup', component: Signup },
    { path: '/signin', component: Signin },
    { path: '/:pathMatch(.*)*', component: NotFound },
  ],
})

export default router
