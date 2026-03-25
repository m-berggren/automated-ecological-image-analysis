import { createApp } from 'vue'
import App from './App.vue'

const el = document.getElementById('vue-app')
if (el) {
  createApp(App).mount(el)
}
