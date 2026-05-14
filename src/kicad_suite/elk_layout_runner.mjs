#!/usr/bin/env node

import process from 'node:process';

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString('utf8');
}

async function loadElk() {
  try {
    const mod = await import('elkjs/lib/elk.bundled.js');
    return mod.default ?? mod;
  }
  catch {
    const mod = await import('elkjs');
    return mod.default ?? mod;
  }
}

async function main() {
  const raw = await readStdin();
  const payload = JSON.parse(raw);
  const ELK = await loadElk();
  const elk = new ELK();
  const layout = await elk.layout(payload);
  process.stdout.write(JSON.stringify(layout));
}

main().catch((error) => {
  process.stderr.write(String(error?.message ?? error));
  process.exitCode = 1;
});

