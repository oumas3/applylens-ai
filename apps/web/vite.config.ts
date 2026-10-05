import { configDefaults, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  envDir: '../../',
  test: {
    environment: 'jsdom',
    setupFiles: './src/testSetup.ts',
    css: true,
    exclude: [...configDefaults.exclude, 'e2e/**'],
    pool: 'threads',
  },
})
