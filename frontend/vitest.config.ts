import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      globals: false,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      include: ['src/test/**/*.{test,spec}.{ts,tsx}'],
      css: false,
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html', 'json-summary', 'lcov'],
        reportsDirectory: 'coverage',
        include: [
          'src/components/studio/**',
          'src/pages/studio/**',
          'src/services/studio.service.ts',
          'src/stores/useStudioStore.ts',
          'src/hooks/useStudioPersistence.ts',
          'src/types/studio/**',
          'src/utils/studio/**',
        ],
        exclude: [
          'src/**/*.{test,spec}.{ts,tsx}',
          'src/test/**',
          'src/main.tsx',
          'src/**/*.d.ts',
          'src/types/studio/**',
          'src/utils/studio/sourceIconMap.ts',
        ],
        thresholds: {
          statements: 50,
          branches: 40,
          functions: 50,
          lines: 50,
        },
      },
    },
  }),
)
