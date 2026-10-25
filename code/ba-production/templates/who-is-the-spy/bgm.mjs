export const bgmVolume = (bgm, total, frame) => {
  const fadeIn = bgm.fadeInFrames ?? 45;
  const fadeOut = bgm.fadeOutFrames ?? 75;
  const head = fadeIn > 0 ? Math.min(1, frame / fadeIn) : 1;
  const tail = fadeOut > 0 ? Math.min(1, Math.max(0, total - frame) / fadeOut) : 1;
  const level = (bgm.volume ?? 0.15) * Math.max(0, Math.min(head, tail));
  let gain = 1;
  const resume = bgm.resumeFadeFrames ?? 0;
  for (const range of bgm.muteRanges ?? []) {
    const end = range.from + range.durationInFrames;
    if (frame >= range.from && frame < end) return 0;
    if (resume > 0 && frame >= end && frame < end + resume) {
      gain = Math.min(gain, (frame - end) / resume);
    }
  }
  return level * gain;
};
