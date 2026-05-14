import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import process from 'node:process';
import { spawnSync } from 'node:child_process';

const currentDir = dirname(fileURLToPath(import.meta.url));
const repoScript = resolve(currentDir, '../../../scripts/server_text_to_kicad.py');

if (!existsSync(repoScript)) {
  console.error(`Pipeline script not found: ${repoScript}`);
  console.error('Run from repository root with: npm run text-to-kicad');
  process.exit(1);
}

const python = process.platform === 'win32' ? 'python' : 'python3';
const result = spawnSync(python, [repoScript], {
  stdio: 'inherit',
  env: process.env,
});

if (typeof result.status === 'number') {
  process.exit(result.status);
}
process.exit(1);
