// SPDX-License-Identifier: AGPL-3.0-only
// Shy timing adapted from ba-archive emotionPlayer.ts / emotionOptions.ts.
// Native export bounds locate the skeleton origin inside the uncropped PNG.
export function bubbleGeometry(preset, spriteHeight, bounds, name) {
  if (!bounds || !(bounds.height > 0)) throw new Error('Bubble requires matching Spine bounds');
  const scale = spriteHeight / bounds.height;
  const calibration = bounds.bubbleAnchors?.[name] ?? (preset.images[0].startsWith('Emoticon_Balloon_') ? bounds.bubbleAnchors?.Dot : undefined);
  if (calibration) return {
    x: calibration.x * spriteHeight * bounds.imageWidth / bounds.imageHeight,
    y: calibration.y * spriteHeight,
    width: calibration.width * spriteHeight * bounds.imageWidth / bounds.imageHeight,
  };
  return {
    x: ((preset.offset.x - .8) * 540 - bounds.x) * scale,
    y: ((preset.offset.y - 1.2) * 1012 + bounds.y + bounds.height) * scale,
    // Dot never calls getRelativeScale: its balloon and children stay native.
    width: (preset.nativeWidth ?? preset.width * 540) * scale,
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
export function bubbleLayers(name, t, calibration) {
  const layer = (image, x = 0, y = 0, width = 1, scale = 1, angle = 0, opacity = 1) =>
    ({image, x, y, width, scale, angle, opacity});
  const anchored = (pose, x, y) => ({...pose, anchorX: x, anchorY: y});
  const out = (v) => 1 - Math.pow(1 - clamp(v), 5);
  const wave = (period) => Math.sin(t / period * Math.PI * 2);
  switch (name) {
    // Independent fallback: the real thought balloon, not Dot/ellipsis.
    // Upstream has no Think timeline; this entrance/hold is not official timing.
    case 'Think': return [layer(0, 0, -.03 * Math.sin(Math.PI * clamp(t)), 1, .8 + .2 * clamp(t / .1))];
    case 'Shy': {
      // Balloon anchor is the bottom-right. The mark's center is measured once
      // from that corner at the 0.8 start width, then both scale up together.
      const pose = sampleShy(t);
      const aspect = 255 / 198;
      return [
        anchored(layer(0, 1, 1, 1, pose.scale), 1, 1),
        anchored(layer(1, 1 - .65 * .8, 1 - .5 * .8 * aspect, 233 / 255, pose.scale, pose.angle), .5, .5),
      ];
    }
    case 'Heart':
      // heartImg.y uses the balloon width, not its height.
      return [layer(0), layer(1, .27, .16 * 255 / 198, .4, 1 + .2 * Math.max(0, wave(.5)))];
    case 'Upset':
      return [layer(0), {...anchored(layer(1, .5, .5, 173 / 255, 1, 6 * wave(.4)), .5, .5), scaleY: 1 - .2 * Math.abs(wave(.86))}];
    case 'Dot':
      // Source creates three 39px dots over the 255x198 balloon, positions
      // their container at (10%, 35%), then advances each dot by 2 widths.
      return [layer(0), ...[0, 1, 2].map((i) => layer(1, (calibration?.dotX ?? .1) + i * (calibration?.dotStep ?? 2 * 39 / 255), calibration?.dotY ?? .35, 39 / 255, 1, 0, clamp((t - .3 - i * .4) / .1)))];
    case 'Bulb':
      return [layer(0), anchored(layer(1, .5, 100 / 198, 83 / 255), .5, .5), anchored(layer(2, .5, 82 / 198, 130 / 255, 1.13, 0, clamp((t - .2) / .1)), .5, .5)];
    case 'Question':
    case 'Exclaim': {
      const peak = name === 'Question' ? 1.6 : 1.4;
      return [layer(0, 0, 0, 1, t < .2 ? 1 + (peak - 1) * clamp(t / .2) : peak - .2 * clamp((t - .2) / .1))];
    }
    case 'Chat': return [layer(0, 0, 0, 1, 1, -25 * Math.sin(Math.PI * clamp(t / .5)))];
    case 'Angry': return [0, 1, 2].map((i) => layer(0, 0, 0, 1, t < .4 ? 1 - .1 * Math.sin(Math.PI * t / .4) : 1 - .8 * clamp((t - .4) / .1), i * 120)).map((pose) => ({...pose, anchorX: .35, anchorY: -.05}));
    case 'Music': return [layer(0, -clamp(t / .9), .1 * wave(.5), 1, .7 + .3 * clamp(t / .1), -8 * wave(.5))];
    case 'Respond': return [-10, 23, 50].map((angle, i) => ({...layer(0, 0, 0, i === 1 ? 2 : 1.4, 1, angle, .2 + .8 * Math.abs(wave(.6))), anchorX: i === 1 ? 1.5 : 1.8, anchorY: 0}));
    // Upstream does getRelativeScale(sprite, options) / 0.5, so the first star's
    // rest width is 0.08*540/0.5. The other two are 0.9 and 0.6 of that width.
    case 'Twinkle': return [[0, 0, 1], [.7, -.6, .9], [.8, .6, .6]].map(([x, y, w], i) => anchored(layer(0, x, y * 121 / 134, w, 1 + ([1.2, 1.15, .9][i] - 1) * (.5 - .5 * Math.cos(t / [.5, .6, .4][i] * Math.PI * 2))), .5, .5));
    case 'Sweat': return [layer(0, 0, clamp(t / .4) * 74 / 114), layer(1, 1, (-.5 + 2.3 * 46 / 74 * clamp(t / .4)) * 74 / 114, 46 / 74)];
    case 'Surprise': return [anchored(layer(0, 0, -.08 * Math.sin(Math.PI * clamp(t / .3)), 1, .7 + .3 * clamp(t / .3), -10), .5, 1), anchored(layer(1, 1.05, 0, 103 / 60, .7 + .3 * clamp(t / .3), 15), .5, 1)].map((p, i) => ({...p, scaleY: i ? .3 + .7 * clamp(t / .3) : 1}));
    case 'Sad': return [0, 1, 2].map((i) => ({...layer(0, i * 30 / 88, ([0, 30, -30][i] + 35 * clamp((t - i / 6 - 1 / 15) / (4 / 15))) / 160, 28 / 88, 1, 0, clamp((t - i / 6) * 15)), scaleY: .5 + .5 * clamp((t - i / 6 - 1 / 15) / (4 / 15))}));
    // Steam, Tear and Zzz never call getRelativeScale. Their box is the source
    // texture in spine pixels; animation scale is the Pixi scale, not a second fit.
    case 'Steam': return [anchored(layer(0, 0, 0, 1, .6 + .3 * clamp((t - 14 / 60) / (21 / 60)), 0, t < 14 / 60 ? 0 : 1 - clamp((t - 35 / 60) / (8 / 60))), 1.4, 1.5), anchored(layer(0, 0, 0, 1, .1 + .6 * clamp(t / (14 / 60)), -30, 1 - clamp((t - 14 / 60) / (12 / 60))), 1.4, 1.5)];
    case 'Sigh': return [anchored(layer(0, 0, 0, 1, .3 + .6 * out((t - 2 / 60) / (33 / 60)), 0, clamp(t / (2 / 60)) * (1 - clamp((t - 47 / 60) / (11 / 60)))), 1, -.2)];
    case 'Tear': return [anchored(layer(0, 0, 30 / 87, 1, .5 + .5 * out((t - 12 / 60) / (13 / 60)), 0, clamp((t - 12 / 60) / (3 / 60)) * (1 - clamp((t - 57 / 60) / (4 / 60)))), 1, 0), anchored(layer(1, 0, 0, 52 / 68, .6 + .4 * out((t - 7 / 60) / (12 / 60)), 0, clamp(t / (7 / 60)) * (1 - clamp((t - 32 / 60) / (15 / 60)))), 1, 0)];
    case 'Zzz': return [0, 1, 2].map((i) => layer(0, [0, -80, -190][i] / 92, [0, -30, 7][i] / 94, 1, [.8, .9, 1][i], [15, 5, -15][i], t >= [0, 53 / 60, 101 / 60][i] ? 1 : 0));
    default: throw new Error(`Unsupported bubble: ${name}`);
  }
}

export function bubbleOpacity(seconds, duration) {
  if (seconds < 0 || seconds >= duration) return 0;
  return Math.min(1, (duration - seconds) / .1);
}
