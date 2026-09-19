import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Dev server talks to the local backend directly, so VITE_API_URL can stay
    // '/api' in every environment.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.jsx',
    // Monaco pulls in web workers and a DOM API jsdom does not implement, so
    // the editor is stubbed in setup.js rather than loaded for every test.
    css: false,
  },
})
