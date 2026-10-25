import test from 'node:test';
import assert from 'node:assert/strict';
import {characterState} from '../templates/who-is-the-spy/character-state.mjs';

test('speaker highlight does not advance or hold the speaking emotion', () => {
  const entry = {id: 'c', emotion: 'calm'};
  const line = {speaker: 'c', emotion: 'shocked'};
  assert.deepEqual(characterState(entry, undefined, 'c', undefined, 0), {emotion: 'calm', dimmed: false});
  assert.equal(characterState(entry, line, 'c', undefined, 18).emotion, 'shocked');
  assert.equal(characterState(entry, undefined, 'c', undefined, 70).emotion, 'calm');
  assert.equal(characterState(entry, undefined, 'other', undefined, 70).dimmed, true);
});

test('held expressions and timed cues still work without an active line', () => {
  const entry = {id: 'c', emotion: 'calm', emotionCues: [{startFrame: 80, emotion: 'blush'}]};
  assert.equal(characterState(entry, undefined, 'other', 'shocked', 70).emotion, 'shocked');
  assert.equal(characterState(entry, {speaker: 'c', emotion: 'shocked'}, 'c', undefined, 80).emotion, 'blush');
  assert.equal(characterState(entry, undefined, 'c', undefined, 80).emotion, 'blush');
});
