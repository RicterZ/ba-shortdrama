// SPDX-License-Identifier: AGPL-3.0-only
// Shy timing adapted from ba-archive emotionPlayer.ts / emotionOptions.ts.
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
