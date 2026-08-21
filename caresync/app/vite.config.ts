import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// El puerto 5173 es el que Terraform pone en la lista de CORS del API
// (`local.origenes_cors`). Cambiarlo aquí exige cambiarlo allí.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
  build: {
    outDir: 'dist',
    sourcemap: true,
    // Un solo bundle: la aplicación tiene cuatro vistas y dividir en trozos
    // añadiría peticiones sin ahorrar nada apreciable.
    chunkSizeWarningLimit: 900,
  },
});
