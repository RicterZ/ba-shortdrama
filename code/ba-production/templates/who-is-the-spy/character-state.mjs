export function characterState(entry, activeLine, highlightedSpeaker, heldEmotion, frame) {
  const speaking = activeLine?.speaker === entry.id;
  let emotion = speaking ? activeLine.emotion || entry.emotion : heldEmotion || entry.emotion;
  for (const cue of entry.emotionCues ?? []) {
    if (frame >= cue.startFrame) emotion = cue.emotion;
  }
  return {
    emotion,
    dimmed: Boolean(highlightedSpeaker) && highlightedSpeaker !== entry.id,
  };
}
