import { createApp } from 'vue'
import './style.css'
import App from './App.vue'
import router from './router'

const el = document.getElementById('vue-app')
if (el) {
  createApp(App).use(router).mount(el)
}

const token = localStorage.getItem('token')

if (token) {
  //attach token to all requests
  window.fetch = ((originalFetch) => {
    return (url, options = {}) => {
      options.headers = {
        ...options.headers,
        Authorization: `Token ${token}`,
      }
      return originalFetch(url, options)
    }
  })(window.fetch)
}
