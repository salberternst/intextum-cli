import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

const output = '../src/intextum_cli/static/vendor';
await mkdir(output, { recursive: true });
await build({
  stdin: {
    contents: "import * as components from '@docling/docling-components'; import { iterateDocumentItems } from '@docling/docling-core'; globalThis.intextumDocling = { components, iterateDocumentItems };",
    resolveDir: process.cwd(),
  },
  outfile: `${output}/docling-components.js`,
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: ['es2022'],
  minify: true,
  treeShaking: false,
  legalComments: 'eof',
});
const licenses = [];
for (const name of ['@docling/docling-components', '@docling/docling-core', 'lit', 'lit-html', 'lit-element', '@lit/reactive-element', '@lit/task']) {
  const folder = `node_modules/${name}`;
  const pkg = JSON.parse(await readFile(`${folder}/package.json`, 'utf8'));
  let license;
  for (const file of ['LICENSE', 'LICENSE.md']) {
    try { license = await readFile(`${folder}/${file}`, 'utf8'); break; } catch {}
  }
  if (!license && name.startsWith('@docling/')) license = await readFile('licenses/docling-ts-MIT.txt', 'utf8');
  if (!license) throw new Error(`License missing for ${name}`);
  licenses.push(`${name} ${pkg.version}\n${license}`);
}
await writeFile(`${output}/LICENSES.txt`, licenses.join('\n\n-----\n\n'));
