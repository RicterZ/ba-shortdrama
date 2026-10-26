// Freeze character action presets into a keyframe table for the Bcut exporter.
// Usage: node scripts/freeze_action_keyframes.mjs > templates/character-action-keyframes.json
import {ACTION_NAMES, sampleAction} from '../templates/character-actions.mjs';

const RATE = 60;
const LENGTH = 2;
const round = (value) => Math.round(value * 1e5) / 1e5;
const table = {rate: RATE, presets: {}};
for (const name of ACTION_NAMES) {
  const keys = [];
  for (let step = 0; step <= RATE * LENGTH; step += 1) {
    const pose = sampleAction(name, step / RATE);
    const [ox, oy] = pose.origin === 'bottom center' ? [0.5, 1] :
      pose.origin.split(' ').map((part) => parseFloat(part) / 100);
    keys.push([round(pose.x), round(pose.y), round(pose.angle), round(pose.scale), round(pose.opacity), ox, oy]);
  }
  table.presets[name] = keys;
}
process.stdout.write(JSON.stringify(table) + '\n');
