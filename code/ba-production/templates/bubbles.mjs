// SPDX-License-Identifier: AGPL-3.0-only
// Shy timing adapted from ba-archive emotionPlayer.ts / emotionOptions.ts.
// The PNG adapter uses the same centered 1080 x 2024 reference plane as
// the upstream 540 / 1012 half-extents, not viewport-relative magic offsets.
export function bubbleGeometry(preset, spriteHeight) {
  const scale = spriteHeight / 2024;
  return {
    x: (preset.offset.x - .8) * 540 * scale,
    y: (preset.offset.y - 1.2) * 1012 * scale,
    width: preset.width * 540 * scale,
  };
}

export function sampleShy(seconds) {
  const visible = seconds >= 0 && seconds < 1;
  const scale = 0.8 + 0.2 * Math.max(0, Math.min(1, seconds / 0.1));
  let angle = 0;
  if (seconds >= 0.1 && seconds < 0.9) {
    const t = seconds - 0.1;
    const u = (t % 0.4) / 0.2;
    const from = t < 0.4 ? 0 : -10;
    angle = u < 1 ? from + (13 - from) * u : 13 - 23 * (u - 1);
  } else if (seconds >= 0.9) angle = -10;
  return {scale, angle, opacity: visible ? Math.min(1, (1 - seconds) / 0.1) : 0};
}

const clamp = (v) => Math.max(0, Math.min(1, v));
// Layer coordinates are relative to the effect box. Curves approximate the
// upstream multi-sprite timeline; they are not game-frame-exact recordings.
export function bubbleLayers(name, t) {
  const layer = (image, x = 0, y = 0, width = 1, scale = 1, angle = 0, opacity = 1) =>
    ({image, x, y, width, scale, angle, opacity});
  const wave = (period) => Math.sin(t / period * Math.PI * 2);
  switch (name) {
    // Independent fallback: the real thought balloon, not Dot/ellipsis.
    // Upstream has no Think timeline; this entrance/hold is not official timing.
    case 'Think': return [layer(0, 0, -.03 * Math.sin(Math.PI * clamp(t)), 1, .8 + .2 * clamp(t / .1))];
    case 'Shy': {
      const pose = sampleShy(t);
      return [layer(0, 0, 0, 1, pose.scale), layer(1, .18, .15, .55, pose.scale, pose.angle)];
    }
    case 'Heart':
      return [layer(0), layer(1, .27, .16, .4, 1 + .2 * Math.max(0, wave(.5)))];
    case 'Upset':
      return [layer(0), layer(1, .2, .15, .6, 1 - .2 * Math.abs(wave(.86)), 6 * wave(.4))];
    case 'Dot':
      return [layer(0), ...[0, 1, 2].map((i) => layer(1, .1 + i * .25, .35, .1, 1, 0, clamp((t - .3 - i * .4) / .1)))];
    case 'Bulb':
      return [layer(0, 0, 0, 1, .7 + .3 * clamp(t / .2)), layer(1, .3, .18, .4), layer(2, .25, .08, .5, 1, 0, clamp((t - .2) / .1))];
    case 'Question':
    case 'Exclaim': {
      const peak = name === 'Question' ? 1.6 : 1.4;
      return [layer(0, 0, 0, 1, t < .2 ? 1 + (peak - 1) * clamp(t / .2) : peak - .2 * clamp((t - .2) / .1))];
    }
    case 'Chat': return [layer(0, 0, 0, 1, 1, -25 * Math.sin(Math.PI * clamp(t / .5)))];
    case 'Angry': return [0, 1, 2].map((i) => layer(0, 0, 0, 1, t < .4 ? 1 - .1 * Math.sin(Math.PI * t / .4) : 1 - .8 * clamp((t - .4) / .1), i * 120));
    case 'Music': return [layer(0, -clamp(t / .9), .1 * wave(.5), 1, .7 + .3 * clamp(t / .1), -8 * wave(.5))];
    case 'Respond': return [-10, 23, 50].map((angle, i) => layer(0, i * .25, 0, i === 1 ? .5 : .35, 1, angle, .2 + .8 * Math.abs(wave(.6))));
    case 'Twinkle': return [[0, .3, .4], [.45, 0, .36], [.5, .6, .24]].map(([x, y, w], i) => layer(0, x, y, w, 1 + .2 * Math.sin(t / [.5, .6, .4][i] * Math.PI * 2)));
    case 'Sweat': return [layer(0, 0, clamp(t / .4) * .4, .45), layer(1, .5, -.2 + clamp(t / .4) * .9, .35)];
    case 'Surprise': return [layer(0, -.1 * clamp(t / .3), -.1 * Math.sin(Math.PI * clamp(t / .3)), .4, .7 + .3 * clamp(t / .3), -10), layer(1, .5, 0, .4, .7 + .3 * clamp(t / .3), 15)];
    case 'Sad': return [0, 1, 2].map((i) => layer(0, i * .25, .2 * clamp((t - i / 6) / .3), .25, .5 + .5 * clamp((t - i / 6) / .3), 0, clamp((t - i / 6) * 15)));
    case 'Steam': return [layer(0, 0, 0, .6, .1 + .6 * clamp(t), -30), layer(0, .4, -.1, .6, .6 + .3 * clamp(t))];
    case 'Sigh': return [layer(0, .2 * clamp(t), .1 * clamp(t), 1, .3 + .6 * clamp(t))];
    case 'Tear': return [layer(0, 0, .2, 1, .5 + .5 * clamp(t)), layer(1, 0, 0, 1, .6 + .4 * clamp(t))];
    case 'Zzz': return [0, 1, 2].map((i) => layer(0, .6 - i * .3, -.1 * i, .3 + i * .05, 1, 15 - i * 15, clamp((t - i * .15) / .15)));
    default: throw new Error(`Unsupported bubble: ${name}`);
  }
}

export function bubbleOpacity(seconds, duration) {
  if (seconds < 0 || seconds >= duration) return 0;
  return Math.min(1, (duration - seconds) / .1);
}
