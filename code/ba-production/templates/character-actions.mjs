// SPDX-License-Identifier: AGPL-3.0-only
// Adapted to frame sampling from ba-archive; see THIRD_PARTY_NOTICES.md.
export const ACTION_NAMES = ['jump', 'hophop', 'greeting', 'shake', 'stiff', 'closeup', 'falldownL', 'falldownR', 'hide'];
const clamp = (x) => Math.max(0, Math.min(1, x));
const ease = (x) => 1 - (1 - clamp(x)) ** 2;
const tween = (t, start, duration, from, to) => from + (to - from) * ease((t - start) / duration);

// x/y are fractions of the sprite dimensions, not of the viewport.
export function sampleAction(name, seconds) {
  if (!ACTION_NAMES.includes(name)) throw new Error(`Unknown character action: ${name}`);
  const pose = { x: 0, y: 0, angle: 0, scale: 1, opacity: 1, origin: 'bottom center' };
  if (seconds < 0) return pose;
  if (name === 'hide') pose.opacity = 0;
  if (name === 'closeup') pose.scale = 1.5;
  if (name === 'jump' || name === 'hophop') {
    const count = name === 'hophop' ? 2 : 1;
    if (seconds < count * 0.25) {
      const u = (seconds % 0.25) / 0.25;
      pose.y = -(name === 'hophop' ? 0.05 : 0.03) * Math.sin(Math.PI * u);
    }
  }
  if (name === 'greeting' && seconds < 0.4) {
    pose.y = 0.04 * Math.sin(Math.PI * seconds / 0.4);
  }
  if (name === 'shake' || name === 'stiff') {
    const count = name === 'shake' ? 3 : 5;
    if (seconds < count * 0.08) {
      pose.x = (name === 'shake' ? 0.03 : 0.01) * Math.sin(2 * Math.PI * seconds / 0.08);
    }
  }
  if (name === 'falldownL' || name === 'falldownR') {
    const direction = name === 'falldownL' ? -1 : 1;
    pose.origin = '40% 50%';
    pose.x = direction * tween(seconds, 0, 0.5, 0, 0.13);
    pose.y = tween(seconds, 0.8, 0.55, 0, 0.6);
    if (seconds < 0.4) pose.angle = tween(seconds, 0, 0.4, 0, 10);
    else if (seconds < 0.8) pose.angle = tween(seconds, 0.4, 0.4, 10, 0);
    else if (seconds < 1.25) pose.angle = 0;
    else if (seconds < 1.36) pose.angle = tween(seconds, 1.25, 0.11, 0, -3);
    else if (seconds < 1.47) pose.angle = tween(seconds, 1.36, 0.11, -3, 0);
    else pose.angle = tween(seconds, 1.47, 0.4, 0, 10);
    pose.angle *= direction;
    if (seconds >= 1.87) pose.opacity = 0;
  }
  return pose;
}

export function sampleActions(cues, frame, fps) {
  if (!(fps > 0)) throw new Error('fps must be positive');
  let pose = sampleAction('jump', -1);
  // Latest cue replaces the previous preset, including persistent hide/closeup.
  const cue = [...(cues ?? [])].filter((c) => c.startFrame <= frame)
    .sort((a, b) => a.startFrame - b.startFrame).at(-1);
  if (cue) pose = sampleAction(cue.name, (frame - cue.startFrame) / fps);
  return pose;
}
