import { build } from 'esbuild';
import { rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';

const webDir = resolve('web');
const outdir = resolve(webDir, 'assets');
if (!outdir.startsWith(`${webDir}${sep}`)) {
    throw new Error('Asset output must remain inside web/');
}
await rm(outdir, { recursive: true, force: true });

await build({
    entryPoints: [resolve(webDir, 'js/app.js'), resolve(webDir, 'js/api_docs.js')],
    absWorkingDir: process.cwd(),
    outdir,
    entryNames: '[name]',
    assetNames: 'files/[name]-[hash]',
    bundle: true,
    minify: true,
    target: ['es2022'],
    format: 'esm',
    platform: 'browser',
    loader: {
        '.eot': 'file',
        '.svg': 'file',
        '.ttf': 'file',
        '.woff': 'file',
        '.woff2': 'file',
    },
});

// A small classic script applies the theme synchronously in the document head.
await build({
    entryPoints: [resolve(webDir, 'js/color_theme.js')],
    absWorkingDir: process.cwd(),
    outdir,
    bundle: true,
    minify: true,
    target: ['es2022'],
    format: 'iife',
    platform: 'browser',
});
