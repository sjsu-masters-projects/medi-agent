import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { checkDocument, headings } from '../check-docs.mjs';

test('headings preserve Unicode, repeated separators and duplicate suffixes', () => {
  assert.deepEqual([...headings('# Overview\n## Overview\n## Español: setup\n## One / two')],
    ['overview', 'overview-1', 'español-setup', 'one--two']);
  assert.deepEqual([...headings('# <strong>Overview</strong>\n## <<em>Nested</em>')],
    ['overview', 'nested']);
});

test('code examples do not create anchors', () => {
  assert.deepEqual([...headings('```sh\n# Not a heading\n```\n# Real')], ['real']);
});

test('links resolve from the document location and preserve explicit anchors', t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mediagent-doc-links-'));
  t.after(() => {
    for (const file of ['index.md', 'target.md']) fs.unlinkSync(path.join(directory, file));
    fs.rmdirSync(directory);
  });
  fs.writeFileSync(path.join(directory, 'target.md'), '# Target\n<a id="manual"></a>');
  fs.writeFileSync(path.join(directory, 'index.md'), '# Index\n[Target](target.md#target)\n[Manual](target.md#manual)\n[Self](#index)\n[Web](https://example.com)');
  assert.deepEqual(checkDocument('index.md', directory), []);
  fs.appendFileSync(path.join(directory, 'index.md'), '\n[Missing](missing.md)\n[Heading](target.md#absent)\n```');
  assert.equal(checkDocument('index.md', directory).length, 3);
});
