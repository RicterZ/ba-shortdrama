"""Template-independent, frame-based audio events consumed by the Bcut writer."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class AudioEvent:
    src: str
    start: int
    end: int
    track: int = 0
    volume: float = 1
    loop: bool = False
    trim_in: int = 0
    fade_in: int = 0
    fade_out: int = 0
    # When set, the clip ends at round(start) + round(span), matching a fixed tick count.
    span_frames: int | None = None

    def validate(self, total):
        if not isinstance(self.src, str) or not self.src:
            raise ValueError("Audio source is required")
        if any(not isinstance(v, int) or isinstance(v, bool) or v < 0
               for v in (self.start, self.end, self.track, self.trim_in, self.fade_in, self.fade_out)):
            raise ValueError("Invalid audio frame range or track")
        if self.span_frames is not None and (
                not isinstance(self.span_frames, int) or isinstance(self.span_frames, bool) or self.span_frames <= 0):
            raise ValueError("Invalid audio span")
        if not self.start < self.end <= total or not math.isfinite(self.volume) or self.volume < 0:
            raise ValueError("Invalid audio duration or volume")
