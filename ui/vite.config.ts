import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import federation from '@originjs/vite-plugin-federation'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    federation({
      name: 'integrationsUI',
      filename: 'remoteEntry.js',
      // Expose components for host applications to consume
      exposes: {
        // All-in-one federation export
        './federation': './src/federation.ts',
        // Content-only micro-frontend (recommended for embedding)
        './MicroFrontend': './src/MicroFrontend.tsx',
        // Provider for configuration injection
        './Provider': './src/providers/ConfigProvider.tsx',
        // Individual page components
        './IntegrationList': './src/pages/integrations/IntegrationList.tsx',
        './IntegrationDetail': './src/pages/integrations/IntegrationDetail.tsx',
        './SyncJobs': './src/pages/jobs/SyncJobs.tsx',
        './JobDetail': './src/pages/jobs/JobDetail.tsx',
        // API client for programmatic usage
        './apiClient': './src/api/apiClient.ts',
      },
      // Shared dependencies - host app can provide these
      shared: ['react', 'react-dom', 'react-router-dom', '@tanstack/react-query'],
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3001, // Different from import-export UI (3000) and host app (4000)
    cors: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    port: 3001,
    cors: true,
  },
  build: {
    modulePreload: false,
    target: 'esnext',
    minify: false,
    cssCodeSplit: false,
  },
})
