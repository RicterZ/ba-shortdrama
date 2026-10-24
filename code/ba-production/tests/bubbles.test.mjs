import assert from 'node:assert/strict';
import {test} from 'node:test';
import {sampleShy} from '../templates/bubbles.mjs';
test('Shy starts at 0.8, grows, shakes twice and fades without playback state', () => {
  assert.equal(sampleShy(-1).opacity, 0);
  assert.equal(sampleShy(0).scale, 0.8);
  assert.equal(sampleShy(0.1).scale, 1);
  assert.ok(Math.abs(sampleShy(0.3).angle - 13) < 1e-8);
  assert.ok(Math.abs(sampleShy(0.7).angle - 13) < 1e-8);
  assert.ok(Math.abs(sampleShy(0.95).opacity - 0.5) < 1e-8);
  assert.equal(sampleShy(1).opacity, 0);
  assert.deepEqual(sampleShy(0.3), sampleShy(0.3));
});

import {readFileSync} from 'node:fs';
import {bubbleLayers, bubbleOpacity} from '../templates/bubbles.mjs';
const presets = JSON.parse(readFileSync(new URL('../templates/bubble-presets.json', import.meta.url)));
test('all 20 bubbles sample valid image layers and disappear at end', () => {
  assert.equal(Object.keys(presets).length, 20);
  for (const [name, preset] of Object.entries(presets)) {
    for (const t of [0, .1, .3, .6, .9, preset.seconds - .01]) {
      const layers = bubbleLayers(name, t);
      assert.ok(layers.length > 0);
      assert.deepEqual(layers, bubbleLayers(name, t));
      for (const layer of layers) {
        assert.ok(preset.images[layer.image]);
        for (const key of ['x', 'y', 'width', 'scale', 'angle', 'opacity']) assert.ok(Number.isFinite(layer[key]), `${name}.${key}`);
        assert.ok(layer.opacity >= 0 && layer.opacity <= 1);
      }
    }
    assert.equal(bubbleOpacity(-1, preset.seconds), 0);
    assert.equal(bubbleOpacity(preset.seconds, preset.seconds), 0);
  }
  assert.deepEqual(presets.Think.images, ['Emoticon_Balloon_T.png']);
  assert.notDeepEqual(presets.Think.images, presets.Dot.images);
});

import {bubbleGeometry} from '../templates/bubbles.mjs';
test('geometry uses upstream fixed offsets and texture width, scales uniformly', () => {
  for (const preset of Object.values(presets)) {
    const g = bubbleGeometry(preset, 2024);
    assert.equal(g.x, (preset.offset.x - .8) * 540);
    assert.equal(g.y, (preset.offset.y - 1.2) * 1012);
    assert.equal(g.width, preset.width * 540);
    const half = bubbleGeometry(preset, 1012);
    assert.equal(half.x, g.x / 2);
    assert.equal(half.y, g.y / 2);
    assert.equal(half.width, g.width / 2);
  }
  assert.equal(presets.Shy.width, .46);
  assert.deepEqual(presets.Shy.offset, {x: .5, y: .06});
  assert.equal(presets.Twinkle.width, .08);
});
