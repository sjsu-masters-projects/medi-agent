// Parse copy declarations without executing application modules or importing secrets.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const require = createRequire(path.join(root, 'apps/clinician-portal/package.json'));
const ts = require('typescript');
const rows = [];

for (const file of process.argv.slice(2)) {
  const source = ts.createSourceFile(file, fs.readFileSync(path.join(root, file), 'utf8'), ts.ScriptTarget.Latest, true);
  const variables = new Map();
  function unwrap(node) {
    while (node && (ts.isAsExpression(node) || ts.isParenthesizedExpression(node) || ts.isSatisfiesExpression(node))) node = node.expression;
    if (node && ts.isIdentifier(node) && variables.has(node.text)) return unwrap(variables.get(node.text));
    return node;
  }
  function properties(node) {
    node = unwrap(node);
    if (!node || !ts.isObjectLiteralExpression(node)) return null;
    return new Map(node.properties.filter(ts.isPropertyAssignment).map(p => [p.name.text ?? p.name.getText(source), p.initializer]));
  }
  function text(node) {
    node = unwrap(node);
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
    return node.getText(source).replace(/\s+/g, ' ');
  }
  function pair(en, es, key) {
    const ep = properties(en), sp = properties(es);
    if (ep && sp) {
      for (const [name, value] of sp) {
        if (name === 'locale') continue;
        if (!ep.has(name)) throw new Error(`${file}:${key}.${name} has no English counterpart`);
        pair(ep.get(name), value, `${key}.${name}`);
      }
      return;
    }
    const line = source.getLineAndCharacterOfPosition(unwrap(es).getStart(source)).line + 1;
    rows.push({ file, line, key, en: text(en), es: text(es) });
  }
  function collect(node) {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) variables.set(node.name.text, node.initializer);
    ts.forEachChild(node, collect);
  }
  collect(source);
  const english = variables.get('english') ?? variables.get('en');
  const spanish = variables.get('spanish') ?? variables.get('es');
  if (properties(english) && properties(spanish)) pair(english, spanish, 'copy');
  function visit(node) {
    if (ts.isObjectLiteralExpression(node)) {
      const props = properties(node);
      if (props?.has('en-US') && props.has('es-MX') && properties(props.get('en-US'))) {
        // Separate en/es declarations were already collected above.
        if (!english) pair(props.get('en-US'), props.get('es-MX'), node.parent.name?.getText(source) ?? 'locales');
      }
    }
    if (ts.isReturnStatement(node) && node.expression && ts.isConditionalExpression(node.expression)) {
      const value = node.expression;
      if (/locale\s*===\s*["']es-MX["']/.test(value.condition.getText(source)) && properties(value.whenTrue) && properties(value.whenFalse)) {
        let parent = node.parent;
        while (parent && !ts.isFunctionDeclaration(parent)) parent = parent.parent;
        pair(value.whenFalse, value.whenTrue, parent?.name?.text ?? 'localeCopy');
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
}
console.log(JSON.stringify(rows));
