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
  for (const [name, preset] of Object.entries(presets)) {
    if (preset.images[0].startsWith('Emoticon_Balloon_')) assert.deepEqual(bubbleGeometry(preset, h, bounds, name), g);
    else assert.ok(bubbleGeometry(preset, h, bounds, name).width < g.width);
  }
  for (const key of ['x', 'y', 'width']) assert.ok(Math.abs(zoom[key] - g[key] * 1.5) < 1e-8);
  const dots = bubbleLayers('Dot', .8, anchors.Dot);
  assert.ok(Math.abs((dots[2].x - dots[1].x) * g.width - 47) < .1);
});
test('Angry and Respond retain upstream pivots instead of rotating at CSS center', () => {
  assert.deepEqual(bubbleLayers('Angry', .1).map(p => [p.anchorX, p.anchorY]), [[.35, -.05], [.35, -.05], [.35, -.05]]);
  assert.deepEqual(bubbleLayers('Respond', .1).map(p => p.anchorX), [1.8, 1.5, 1.8]);
});
test('review fixes retain native image ratios, independent scale axes and timed phases', () => {
  const sweat = bubbleLayers('Sweat', .2);
  assert.equal(sweat[1].width, 46 / 74);
  const surprise = bubbleLayers('Surprise', .3);
  assert.equal(surprise[1].width, 103 / 60);
  assert.equal(surprise[1].scaleY, 1);
  const sigh = bubbleLayers('Sigh', .4)[0];
  assert.equal(sigh.x, 0);
  assert.equal(sigh.y, 0);
  assert.equal(sigh.anchorX, 1);
  assert.equal(sigh.anchorY, -.2);
  assert.equal(bubbleLayers('Sigh', 1)[0].opacity, 0);
  assert.equal(bubbleLayers('Steam', 1).reduce((sum, p) => sum + p.opacity, 0), 0);
  assert.equal(bubbleLayers('Steam', 0)[1].scale, 0.1);
  assert.equal(bubbleLayers('Steam', 0)[0].opacity, 0);
  assert.deepEqual(bubbleLayers('Zzz', .2).map(p => p.opacity), [1, 0, 0]);
  assert.deepEqual(bubbleLayers('Zzz', 1).map(p => p.opacity), [1, 1, 0]);
  assert.deepEqual(bubbleLayers('Zzz', 1.9).map(p => p.opacity), [1, 1, 1]);
  assert.ok(presets.Zzz.seconds > 1.9);
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

test('Steam, Tear and Zzz keep upstream pixel size instead of width*540', () => {
  assert.equal(presets.Steam.nativeWidth, 191);
  assert.equal(presets.Tear.nativeWidth, 68);
  assert.equal(presets.Zzz.nativeWidth, 92);
  assert.equal(presets.Zzz.aspectRatio, 92 / 94);
  const bounds = {x: -530, y: -1025, width: 1050, height: 2453, imageWidth: 822, imageHeight: 1920};
  for (const name of ['Steam', 'Zzz', 'Tear']) {
    const preset = presets[name];
    const g = bubbleGeometry(preset, bounds.height, bounds, name);
    assert.equal(g.x, (preset.offset.x - .8) * 540 - bounds.x);
    assert.equal(g.y, (preset.offset.y - 1.2) * 1012 + bounds.y + bounds.height);
    assert.equal(g.width, preset.nativeWidth);
  }
  const steam = bubbleLayers('Steam', 14 / 60);
  assert.equal(steam[1].scale, 0.7);
  assert.equal(steam[1].angle, -30);
  assert.deepEqual([steam[1].anchorX, steam[1].anchorY], [1.4, 1.5]);
  assert.equal(steam[0].scale, 0.6);
  const tear = bubbleLayers('Tear', 0);
  assert.equal(tear[0].y, 30 / 87);
  assert.equal(tear[0].width, 1);
  assert.equal(tear[0].scale, 0.5);
  assert.deepEqual([tear[0].anchorX, tear[0].anchorY], [1, 0]);
  assert.equal(tear[1].width, 52 / 68);
  assert.equal(tear[1].scale, 0.6);
  const zzz = bubbleLayers('Zzz', 1.9);
  assert.deepEqual(zzz.map(layer => layer.x), [0, -80 / 92, -190 / 92]);
  assert.deepEqual(zzz.map(layer => layer.y), [0, -30 / 94, 7 / 94]);
  assert.deepEqual(zzz.map(layer => layer.width), [1, 1, 1]);
  assert.deepEqual(zzz.map(layer => layer.scale), [.8, .9, 1]);
  assert.deepEqual(zzz.map(layer => layer.angle), [15, 5, -15]);
});

test('Twinkle rest size includes the upstream divide-by-0.5', () => {
  assert.equal(presets.Twinkle.nativeWidth, 0.08 * 540 / 0.5);
  const layers = bubbleLayers('Twinkle', 0);
  assert.deepEqual(layers.map((layer) => layer.width), [1, .9, .6]);
  assert.deepEqual(layers.map((layer) => layer.x), [0, .7, .8]);
  assert.deepEqual(layers.map((layer) => layer.y), [0, -.6 * 121 / 134, .6 * 121 / 134]);
  assert.deepEqual(layers.map((layer) => [layer.anchorX, layer.anchorY]), [[.5, .5], [.5, .5], [.5, .5]]);
  for (const layer of layers) assert.ok(Math.abs(layer.scale - 1) < 1e-12);
  const peak = bubbleLayers('Twinkle', .25)[0];
  assert.ok(Math.abs(peak.scale - 1.2) < 1e-12);
});

test('icons inside balloons keep the upstream center instead of a corner offset', () => {
  const aspect = 255 / 198;
  const heart = bubbleLayers('Heart', 0)[1];
  assert.equal(heart.x, .27);
  assert.equal(heart.y, .16 * 255 / 198);
  assert.equal(heart.width, .4);
  const shy = bubbleLayers('Shy', .2);
  assert.deepEqual([shy[0].anchorX, shy[0].anchorY], [1, 1]);
  assert.equal(shy[1].x, 1 - .65 * .8);
  assert.equal(shy[1].y, 1 - .5 * .8 * aspect);
  assert.equal(shy[1].width, 233 / 255);
  assert.deepEqual([shy[1].anchorX, shy[1].anchorY], [.5, .5]);
  const upset = bubbleLayers('Upset', .2)[1];
  assert.equal(upset.x, .5);
  assert.equal(upset.y, .5);
  assert.equal(upset.width, 173 / 255);
  assert.deepEqual([upset.anchorX, upset.anchorY], [.5, .5]);
  assert.equal(presets.Upset.nativeWidth, 255);
  const bulb = bubbleLayers('Bulb', .4);
  assert.equal(bulb[1].x, .5);
  assert.equal(bulb[1].y, 100 / 198);
  assert.equal(bulb[1].width, 83 / 255);
  assert.deepEqual([bulb[1].anchorX, bulb[1].anchorY], [.5, .5]);
  assert.equal(bulb[2].y, 82 / 198);
  assert.equal(bulb[2].width, 130 / 255);
  assert.equal(bulb[2].scale, 1.13);
  assert.equal(presets.Bulb.nativeWidth, 255);
});

test('standalone symbols use the upstream pivot, anchor and native box', () => {
  const chat = bubbleLayers('Chat', .25)[0];
  assert.equal(chat.anchorX, .2 * 540 * 1.3 / 147);
  assert.equal(chat.anchorY, .2 * 540 / 147);
  assert.deepEqual([bubbleLayers('Question', 0)[0].anchorX, bubbleLayers('Question', 0)[0].anchorY], [.5, 1]);
  assert.equal(bubbleLayers('Exclaim', 0)[0].anchorX, undefined);
  assert.equal(presets.Sad.nativeWidth, 88);
  assert.equal(bubbleLayers('Sad', 0)[1].x, 30 / 88);
  assert.equal(bubbleLayers('Sad', 0)[0].width, 28 / 88);
  assert.equal(presets.Sigh.nativeWidth, 141);
  const surprise = bubbleLayers('Surprise', 0);
  assert.equal(surprise[0].angle, 0);
  assert.equal(surprise[1].x, 1.5 * .7);
  assert.equal(surprise[1].angle, 0);
  const music = bubbleLayers('Music', .5)[0];
  assert.ok(Math.abs(music.x + .35) < 1e-12);
  const angry = bubbleLayers('Angry', .2)[0];
  assert.equal(angry.scale, .9);
  assert.ok(Math.abs(angry.scale * angry.scaleY - 1) < 1e-12);
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
