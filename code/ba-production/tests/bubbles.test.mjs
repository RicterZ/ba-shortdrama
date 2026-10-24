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
test('Yuuka screenshot anchor matches measured screen coordinates and scales with PNG', () => {
  const registry = JSON.parse(readFileSync(new URL('../templates/bubble-calibrations.json', import.meta.url)));
  const anchors = Object.values(registry)[0].anchors;
  const bounds = {height: 2453, imageWidth: 822, imageHeight: 1920, bubbleAnchors: anchors};
  const h = 1920 * 1.08174715;
  const g = bubbleGeometry(presets.Dot, h, bounds, 'Dot');
  assert.ok(Math.abs(g.x + 1542.61420 - 1647) < .01);
  assert.ok(Math.abs(g.y + 66.47091 - 260) < .01);
  assert.ok(Math.abs(g.width - 193.8) < .01);
  const zoom = bubbleGeometry(presets.Dot, h * 1.5, bounds, 'Dot');
  for (const key of ['x', 'y', 'width']) assert.ok(Math.abs(zoom[key] - g[key] * 1.5) < 1e-8);
  const dots = bubbleLayers('Dot', .8, anchors.Dot);
  assert.ok(Math.abs((dots[2].x - dots[1].x) * g.width - 47) < .1);
});
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
test('geometry maps native Spine origin into PNG and scales without a guessed center', () => {
  const bounds = {x: -1052.9828, y: -723.978, width: 1769.9822, height: 2054.978};
  for (const preset of Object.values(presets)) {
    const g = bubbleGeometry(preset, bounds.height, bounds);
    assert.equal(g.x, (preset.offset.x - .8) * 540 - bounds.x);
    assert.equal(g.y, (preset.offset.y - 1.2) * 1012 + bounds.y + bounds.height);
    assert.equal(g.width, preset.nativeWidth ?? preset.width * 540);
    const half = bubbleGeometry(preset, bounds.height / 2, bounds);
    assert.equal(half.x, g.x / 2);
    assert.equal(half.y, g.y / 2);
    assert.equal(half.width, g.width / 2);
  }
  assert.throws(() => bubbleGeometry(presets.Shy, 600));
  assert.equal(presets.Shy.width, .46);
});

test('Dot keeps the official balloon-to-character size ratio and native dot spacing', () => {
  assert.equal(presets.Dot.nativeWidth, 255);
  assert.equal(presets.Dot.aspectRatio, 255 / 198);
  const layers = bubbleLayers('Dot', .8);
  assert.equal(layers[1].width, 39 / 255);
  assert.equal(layers[1].y, .35);
  assert.equal(layers[2].x, .1 + 78 / 255);
  assert.equal(layers[3].x, .1 + 156 / 255);
  assert.ok(layers[1].opacity > .99);
  assert.ok(layers[2].opacity > .99);
  assert.equal(layers[3].opacity, 0);
});
