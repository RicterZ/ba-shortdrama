import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {bgmVolume} from '../templates/who-is-the-spy/bgm.mjs';

const base = {volume: 0.6, fadeInFrames: 0, fadeOutFrames: 0};

test('BGM loop uses an absolute volume timeline past the first loop', () => {
  const source = readFileSync(new URL('../templates/who-is-the-spy/index.tsx', import.meta.url), 'utf8');
  assert.match(source, /src=\{staticFile\(bgm.src\)\}[\s\S]*?loopVolumeCurveBehavior="extend"/);
  const bgm = {...base, muteRanges: [{from: 1200, durationInFrames: 90}]};
  assert.equal(bgmVolume(bgm, 3000, 300), 0.6);
  assert.equal(bgmVolume(bgm, 3000, 1200), 0);
  assert.equal(bgmVolume(bgm, 3000, 1290), 0.6);
  assert.equal(bgmVolume(bgm, 3000, 2100), 0.6);
});

test('later mute takes precedence over an earlier resume fade regardless of order', () => {
  const ranges = [{from: 0, durationInFrames: 100}, {from: 105, durationInFrames: 100}];
  for (const muteRanges of [ranges, [...ranges].reverse()]) {
    const bgm = {...base, resumeFadeFrames: 30, muteRanges};
    assert.equal(bgmVolume(bgm, 1000, 110), 0);
    assert.equal(bgmVolume(bgm, 1000, 205), 0);
    assert.equal(bgmVolume(bgm, 1000, 220), 0.3);
    assert.equal(bgmVolume(bgm, 1000, 235), 0.6);
  }
});

test('resume fade preserves the episode fade envelope', () => {
  const bgm = {...base, fadeInFrames: 100, fadeOutFrames: 100,
    resumeFadeFrames: 100, muteRanges: [{from: 0, durationInFrames: 25}]};
  assert.equal(bgmVolume(bgm, 1000, 50), 0.075);
  assert.equal(bgmVolume(bgm, 1000, 950), 0.3);
  assert.equal(bgmVolume(bgm, 1000, 1000), 0);
});
