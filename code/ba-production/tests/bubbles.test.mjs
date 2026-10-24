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
