import tsParser from '@typescript-eslint/parser';
import tsPlugin from '@typescript-eslint/eslint-plugin';

export default [{
  ignores: ['dist/**', 'local/**', 'node_modules/**', 'src/core/generated-reference.ts', 'src/core/generated-extras.ts', 'src/core/editor-reference.ts'],
}, {
  files: ['src/**/*.ts'],
  languageOptions: {
    parser: tsParser,
    parserOptions: {project: './tsconfig.json', tsconfigRootDir: import.meta.dirname},
  },
  plugins: {'@typescript-eslint': tsPlugin},
  rules: {
    'constructor-super': 'error',
    'for-direction': 'error',
    'getter-return': 'error',
    'no-async-promise-executor': 'error',
    'no-constant-binary-expression': 'error',
    'no-dupe-else-if': 'error',
    'no-duplicate-case': 'error',
    'no-fallthrough': 'error',
    'no-self-assign': 'error',
    'no-unreachable': 'error',
    'no-unsafe-finally': 'error',
    'prefer-const': 'error',
    'eqeqeq': ['error', 'always'],
    '@typescript-eslint/consistent-type-imports': 'error',
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/no-floating-promises': 'error',
    '@typescript-eslint/no-misused-promises': 'error',
    '@typescript-eslint/only-throw-error': 'error',
    '@typescript-eslint/use-unknown-in-catch-callback-variable': 'error',
  },
}];
