import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts')) return 'vendor-echarts'
          if (id.includes('node_modules/element-plus') || id.includes('node_modules/@element-plus')) return 'vendor-element'
          if (id.includes('node_modules/vue') || id.includes('node_modules/pinia')) return 'vendor-vue'
          if (id.includes('node_modules/axios') || id.includes('node_modules/dayjs')) return 'vendor-utils'
        }
      }
    }
  }
})
