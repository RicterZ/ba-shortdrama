import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {buildSync} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

const require = createRequire(import.meta.url);
const video = {width: 1280, height: 720, fps: 30, durationInFrames: 90};

for (const template of ['official', 'who-is-the-spy']) {
  const code = buildSync({
    entryPoints: [fileURLToPath(new URL(`../templates/${template}/index.tsx`, import.meta.url))],
    bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external',
  }).outputFiles[0].text;

  for (const kind of template === 'who-is-the-spy' ? ['speech', 'thought'] : ['speech']) {
    for (const audio of ['', 'audio/line.wav']) {
      test(`${template} ${kind}: ${audio ? 'voiced' : 'silent'} line keeps caption, timing and correct click behavior`, () => {
        let root;
        const sources = [];
        const sequences = [];
        const line = {kind, id: 'L1', speaker: 'c', outfit: 'default', emotion: 'default',
          text: 'Caption', from: 0, durationInFrames: 60, audio};
        const scene = {episode: {...video, style: {caption_style: 'meme'}}, characters: {}, ui: {sfx: {click: 'audio/click.wav'}},
          shots: [{id: 'S1', from: 0, durationInFrames: 90, background: '#fff',
            camera: 'static', focus: 'c', characters: [{id: 'c', x: 0.5}], lines: [line]}]};
        const pass = ({children}) => React.createElement(React.Fragment, null, children);
        const transitions = Object.assign(pass, {Sequence: pass, Transition: () => null});
        const remotion = {...require('remotion'),
          registerRoot: (component) => { root = component; },
          Composition: ({component}) => React.createElement(component, scene),
          AbsoluteFill: pass,
          useVideoConfig: () => video,
          useCurrentFrame: () => 30,
          Sequence: ({children, ...props}) => { sequences.push(props); return pass({children}); },
          staticFile: (src) => {
            assert.notEqual(src, '', 'must not resolve an empty media address');
            return `/static/${src}`;
          },
          Audio: ({src}) => { sources.push(src); return null; },
        };
        // Execute the real TSX tree, replacing only Remotion's browser/timeline boundary.
        const load = (id) => id === 'remotion' ? remotion
          : id === '@remotion/transitions' ? {...require(id), TransitionSeries: transitions}
          : require(id);
        new Function('require', 'module', 'exports', code)(load, {exports: {}}, {});
        const html = renderToStaticMarkup(React.createElement(root));
        assert.ok(html.includes(line.text));
        assert.deepEqual(sources, [...(audio ? [`/static/${audio}`] : []),
          ...(kind === 'speech' ? ['/static/audio/click.wav'] : [])]);
        if (template === 'who-is-the-spy') {
          assert.equal(html.includes('brightness(0.46)'), kind === 'thought');
          assert.equal(html.includes('rotate(-1deg)'), kind === 'thought');
          assert.equal(html.includes('rotate(-1.2deg)'), kind === 'speech');
        }
        assert.ok(sequences.some((s) => s.name === 'audio-L1'
          && s.from === line.from && s.durationInFrames === line.durationInFrames));
      });
    }
  }
}
