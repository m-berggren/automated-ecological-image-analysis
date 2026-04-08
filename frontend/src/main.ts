import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'

const el = document.getElementById('vue-app')
if (el) {
  createApp(App).use(router).mount(el)
}
