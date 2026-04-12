import { createApp } from 'vue'
import { createPinia } from 'pinia'
import './style.css'
import App from './App.vue'
import router from './router'


const el = document.getElementById('vue-app')
if (el) {
  const app = createApp(App)

  const pinia = createPinia()

  app.use(pinia)
  app.use(router)

  app.mount(el)
}


