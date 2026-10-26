// Render the production components themselves, retaining separate transparent layers.
import {bundle} from '@remotion/bundler';
import {renderFrames, selectComposition, openBrowser} from '@remotion/renderer';
import {readFileSync, writeFileSync, existsSync, mkdirSync, rmSync} from 'node:fs';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const [requestPath] = process.argv.slice(2);
const request = JSON.parse(readFileSync(requestPath, 'utf8'));
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const {scene, raws, assets, scratch, layers, transitions = [], layerRanges = {}} = request;
const concurrency = Number(request.concurrency || process.env.BCUT_RENDER_CONCURRENCY || 4);
if (!Number.isInteger(concurrency) || concurrency < 1) throw new Error('Invalid render concurrency');
mkdirSync(assets, {recursive: true});
mkdirSync(scratch, {recursive: true});
const template = scene.episode.template || 'official';
if (!/^[a-zA-Z0-9_-]+$/.test(template)) throw new Error('Invalid template name');
if (!existsSync(path.join(root, `templates/${template}/bcut.py`))) throw new Error('Missing Bcut processor');
const serveUrl = await bundle({entryPoint: path.join(root, `templates/${template}/index.tsx`),
  publicDir: raws, outDir: path.join(scratch, 'bundle'), rootDir: root});
const chrome = process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const browserExecutable = existsSync(chrome) ? chrome : undefined;
const browser = await openBrowser('chrome', {browserExecutable});
const spans = [];
try {
  const jobs = request.jobs || [...layers.flatMap(layer => (layerRanges[layer] || [[0, scene.episode.durationInFrames]])
    .map(([start, end]) => ({layer, start, end}))),
    ...transitions.map(([start, end]) => ({layer: 'transition', start, end}))];
  const staticCache = new Map();
  const compositions = new Map();
  for (const {layer, start, end, staticKey} of jobs) {
    if (staticKey && staticCache.has(staticKey)) {
      spans.push({layer, label: layer, startFrame: start, endFrame: end, name: staticCache.get(staticKey)});
      continue;
    }
    console.log(`Bcut: rendering ${layer} frames ${start}-${end - 1} (${staticKey ? '1 constant-state frame' : `${end - start} frames`}, concurrency ${concurrency})`);
    const inputProps = {...scene, bcutLayer: ['transition', 'reference'].includes(layer) ? undefined : layer};
    let composition = compositions.get(layer);
    if (!composition) {
      composition = await selectComposition({serveUrl, id: 'BAEpisode', inputProps,
        puppeteerInstance: browser});
      compositions.set(layer, composition);
    }
    const frames = new Map();
    let lastLog = Date.now();
    await renderFrames({serveUrl, composition, inputProps, puppeteerInstance: browser,
      outputDir: null, imageFormat: 'png', muted: true, concurrency, frameRange: [start, staticKey ? start : end - 1],
      onStart: () => {}, onFrameUpdate: (count) => {
        if (Date.now() - lastLog > 10000) {
          console.log(`Bcut: ${layer} ${count}/${composition.durationInFrames}`);
          lastLog = Date.now();
        }
      },
      onFrameBuffer: (buffer, frame) => {
        const hash = createHash('sha256').update(buffer).digest('hex');
        const name = `layer-${hash}.png`;
        const target = path.join(assets, name);
        if (!existsSync(target)) writeFileSync(target, buffer);
        frames.set(frame, name);
      },
    });
    if (staticKey) {
      const name = frames.get(start);
      if (!name) throw new Error(`Missing ${layer} representative frame ${start}`);
      staticCache.set(staticKey, name);
      spans.push({layer, label: layer, startFrame: start, endFrame: end, name});
      continue;
    }
    let previous;
    for (let frame = start; frame < end; frame++) {
      if (!['transition', 'reference'].includes(layer) && transitions.some(([a, b]) => a <= frame && frame < b)) {
        previous = undefined;
        continue;
      }
      const name = frames.get(frame);
      if (!name) throw new Error(`Missing ${layer} frame ${frame}`);
      if (previous?.name === name) previous.endFrame = frame + 1;
      else {
        previous = {layer, label: layer, startFrame: frame, endFrame: frame + 1, name};
        spans.push(previous);
      }
    }
  }
  writeFileSync(request.result, JSON.stringify(spans));
} finally {
  await browser.close({silent: true});
  rmSync(path.join(scratch, 'bundle'), {recursive: true, force: true});
}
