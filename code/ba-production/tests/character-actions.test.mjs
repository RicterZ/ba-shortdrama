import assert from 'node:assert/strict';
import {test} from 'node:test';
import {ACTION_NAMES, sampleAction, sampleActions} from '../templates/character-actions.mjs';

test('all presets have finite, deterministic poses at arbitrary seek positions', () => {
  for (const name of ACTION_NAMES) {
    for (const t of [-1, 0, 0.125, 0.4, 0.8, 1.3, 1.87, 10]) {
      const pose = sampleAction(name, t);
      assert.deepEqual(pose, sampleAction(name, t));
      for (const key of ['x', 'y', 'angle', 'scale', 'opacity']) assert.ok(Number.isFinite(pose[key]));
    }
  }
});
test('falls mirror, persist hidden, and do not depend on playback history', () => {
  for (const t of [0.2, 0.6, 1, 1.3, 1.6, 2]) {
    const left = sampleAction('falldownL', t);
    const right = sampleAction('falldownR', t);
    assert.equal(left.x, -right.x);
    assert.equal(left.angle, -right.angle);
    assert.equal(left.y, right.y);
  }
  assert.equal(sampleAction('falldownL', 2).opacity, 0);
  assert.equal(sampleAction('falldownR', -1).opacity, 1);
});
test('transient actions settle; latest timed cue replaces persistent state', () => {
  for (const name of ['jump', 'hophop', 'greeting', 'shake', 'stiff']) {
    assert.equal(sampleAction(name, 2).x, 0);
    assert.equal(sampleAction(name, 2).y, 0);
  }
  const cues = [{name: 'jump', startFrame: 60}, {name: 'hide', startFrame: 30}];
  assert.equal(sampleActions(cues, 29, 30).opacity, 1);
  assert.equal(sampleActions(cues, 30, 30).opacity, 0);
  assert.equal(sampleActions(cues, 60, 30).opacity, 1);
  assert.deepEqual(sampleActions(cues, 90, 30), sampleActions(cues, 180, 60));
  assert.throws(() => sampleAction('typo', 0));
  assert.throws(() => sampleActions([], 0, 0));
});
