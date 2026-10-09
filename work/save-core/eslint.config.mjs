import editorConfig from '../save-editor/eslint.config.mjs';

// Share the same typed rules while resolving this package's own TS project.
export default editorConfig.map(config => config.languageOptions ? {
  ...config,
  languageOptions: {
    ...config.languageOptions,
    parserOptions: {project: './tsconfig.json', tsconfigRootDir: import.meta.dirname},
  },
} : config);
