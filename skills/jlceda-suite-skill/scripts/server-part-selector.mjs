#!/usr/bin/env node

import process from 'node:process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const skillDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(skillDir, '..', '..', '..');
const scriptPath = path.join(repoRoot, 'scripts', 'server-part-selector.ts');
const tsNodeCli = path.join(repoRoot, 'node_modules', 'ts-node', 'dist', 'bin.js');
const { spawn } = await import('node:child_process');
const child = spawn(process.execPath, [tsNodeCli, '--files', scriptPath], { cwd: repoRoot, stdio: 'inherit', env: process.env });
child.on('exit', (code) => { process.exitCode = code ?? 1; });
child.on('error', (error) => { console.error('Failed to start server-part-selector.ts'); console.error(error); process.exitCode = 1; });
