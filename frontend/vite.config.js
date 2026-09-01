import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

const backendUrl = process.env.VITE_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || 'https://api.wah-lah.com'

export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.REACT_APP_BACKEND_URL': JSON.stringify(backendUrl),
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        '.js': 'jsx',
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    host: true,
  },
})
