import antfu from '@antfu/eslint-config';

export default antfu({
  stylistic: {
    semi: true,
    indent: 2,
  },
  rules: {
    'ts/no-explicit-any': 'warn',
    'no-empty': ['warn', { allowEmptyCatch: false }],
    'max-params': ['warn', 6],
    'max-lines': ['warn', { max: 600, skipBlankLines: true, skipComments: true }],
    'no-new-func': 'warn',
    'no-console': ['warn', { allow: ['warn', 'error'] }],
  },
});
