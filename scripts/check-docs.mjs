#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function headingText(source) {
  let insideTag = false;
  let text = '';
  for (const character of source) {
    if (character === '<') insideTag = true;
    else if (character === '>') insideTag = false;
    else if (!insideTag) text += character;
  }
  return text;
}

export function headings(source) {
  const counts = new Map();
  const ids = new Set();
  for (const line of withoutFences(source).split('\n')) {
    const match = line.match(/^ {0,3}#{1,6}\s+(.+?)\s*#*$/);
    if (!match) continue;
    const slug = headingText(match[1]).replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
      .toLowerCase().replace(/[^\p{L}\p{N}\p{M}\s_-]/gu, '').replace(/ /g, '-');
    const count = counts.get(slug) ?? 0;
    ids.add(count ? `${slug}-${count}` : slug);
    counts.set(slug, count + 1);
  }
  for (const match of source.matchAll(/<(?:a|h[1-6])\s+[^>]*(?:id|name)=["']([^"']+)["']/g)) ids.add(match[1]);
  return ids;
}

function withoutFences(source) {
  let fence;
  return source.split('\n').map(line => {
    const match = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (match) {
      if (!fence) fence = match[1];
      else if (match[1][0] === fence[0] && match[1].length >= fence.length) fence = undefined;
      return '';
    }
    return fence ? '' : line;
  }).join('\n');
}

export function checkDocument(file, base = root) {
  const absolute = path.resolve(base, file);
  if (!fs.existsSync(absolute)) return [`${file}: missing document`];
  const source = fs.readFileSync(absolute, 'utf8');
  const prose = withoutFences(source);
  const targets = [...prose.matchAll(/\]\(<?([^\s)>]+)>?(?:\s+"[^"]*")?\)/g)].map(m => m[1]);
  targets.push(...[...prose.matchAll(/^\[[^\]]+\]:\s*<?([^\s>]+)>?/gm)].map(m => m[1]));
  targets.push(...[...prose.matchAll(/<img\s+[^>]*src=["']([^"']+)["']/g)].map(m => m[1]));
  const errors = [];
  for (const target of new Set(targets)) {
    if (/^(?:[a-z][a-z0-9+.-]*:|\/)/i.test(target)) continue;
    const [relative, fragment] = target.split('#', 2);
    let destination;
    try { destination = path.resolve(path.dirname(absolute), decodeURIComponent(relative.split('?')[0] || path.basename(absolute))); }
    catch { errors.push(`${file}: invalid URL ${target}`); continue; }
    if (!fs.existsSync(destination)) { errors.push(`${file}: missing link ${target}`); continue; }
    if (fragment && /\.md$/i.test(destination)) {
      const ids = headings(fs.readFileSync(destination, 'utf8'));
      let id;
      try { id = decodeURIComponent(fragment); } catch { id = fragment; }
      if (!ids.has(id)) errors.push(`${file}: missing heading ${target}`);
    }
  }
  const fences = source.split('\n').filter(line => /^ {0,3}(`{3,}|~{3,})/.test(line));
  if (fences.length % 2) errors.push(`${file}: unclosed code fence`);
  return errors;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  let files = process.argv.slice(2);
  if (files.length === 1 && files[0] === '--all') {
    files = execFileSync('git', ['ls-files'], { cwd: root, encoding: 'utf8' }).trim().split('\n')
      .filter(file => file.endsWith('.md') && fs.existsSync(path.join(root, file)));
  }
  if (!files.length) files.push('README.md', 'CONTRIBUTING.md', 'AGENTS.md', 'docs/README.md');
  const errors = files.flatMap(file => checkDocument(file));
  errors.forEach(error => console.error(error));
  console.log(`Checked ${files.length} documentation files; ${errors.length} link or fence errors.`);
  process.exitCode = errors.length ? 1 : 0;
}
