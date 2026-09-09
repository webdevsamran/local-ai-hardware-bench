import js from '@eslint/js'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'dist-ssr', 'node_modules', 'coverage'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // Build-time Node scripts, not browser code.
    files: ['scripts/**/*.mjs'],
    languageOptions: {
      globals: { process: 'readonly', console: 'readonly' },
    },
  },
  {
    files: ['**/*.{ts,tsx}'],
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
)