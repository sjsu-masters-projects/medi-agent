import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const extractor = path.join(root, 'scripts/extract-spanish-review.mjs');

function fixture(source, run) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'spanish-review-'));
  const file = path.join(directory, 'copy.ts');
  try {
    fs.writeFileSync(file, source);
    return run(path.relative(root, file));
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

function extract(file) {
  return JSON.parse(execFileSync(process.execPath, [extractor, file], { encoding: 'utf8' }));
}

test('pairs nested literals without executing application code', () => {
  fixture(`throw new Error('not executable');
    const english = { nested: { label: 'Hello' } } as const;
    const spanish = { nested: { label: 'Hola' } } as const;`, file => {
    const [row] = extract(file);
    assert.equal(row.key, 'copy.nested.label');
    assert.equal(row.en, 'Hello');
    assert.equal(row.es, 'Hola');
    assert.equal(row.line, 3);
  });
});

test('preserves dynamic placeholders and both conditional branches', () => {
  fixture('const en = { count: (n: number) => n === 1 ? `${n} item` : `${n} items` };\n' +
    'const es = { count: (n: number) => n === 1 ? `${n} elemento` : `${n} elementos` };', file => {
    const [row] = extract(file);
    assert.match(row.en, /\$\{n\} items/);
    assert.match(row.es, /\$\{n\} elementos/);
    assert.match(row.es, /n === 1/);
  });
});

test('finds locale objects and returned locale branches', () => {
  fixture(`const copy = { 'en-US': { title: 'First' }, 'es-MX': { title: 'Primero' } };
    function labels(locale) { return locale === 'es-MX' ? { second: 'Segundo' } : { second: 'Second' }; }`, file => {
    const rows = extract(file);
    assert.deepEqual(rows.map(row => row.es), ['Primero', 'Segundo']);
  });
});

test('missing English pairing fails rather than silently skipping a draft', () => {
  fixture("const en = {}; const es = { label: 'Hola' };", file => {
    const result = spawnSync(process.execPath, [extractor, file], { encoding: 'utf8' });
    assert.notEqual(result.status, 0);
    assert.match(result.stderr, /no English counterpart/);
  });
});
