import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('/node_modules/pdfjs-dist/')) return 'pdf-preview';
          if (id.includes('/node_modules/@codemirror/') || id.includes('/node_modules/@lezer/')) return 'code-editor';
          if (/node_modules\/(yjs|y-protocols|y-codemirror\.next|lib0)\//.test(id)) return 'collaboration';
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
});
