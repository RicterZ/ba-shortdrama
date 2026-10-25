import React from 'react';
import {sampleActions} from '../character-actions.mjs';
import {bubbleLayers, bubbleOpacity, bubbleGeometry} from '../bubbles.mjs';
import bubblePresets from '../bubble-presets.json';
import {
  AbsoluteFill,
  Audio,
  Composition,
  Easing,
  Img,
  Sequence,
  interpolate,
  registerRoot,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {linearTiming, TransitionSeries} from '@remotion/transitions';
import type {TransitionPresentation} from '@remotion/transitions';
import {fade} from '@remotion/transitions/fade';
import {slide} from '@remotion/transitions/slide';
import type {SlideDirection} from '@remotion/transitions/slide';
import {wipe} from '@remotion/transitions/wipe';
import type {WipeDirection} from '@remotion/transitions/wipe';
import {flip} from '@remotion/transitions/flip';
import type {FlipDirection} from '@remotion/transitions/flip';
import {clockWipe} from '@remotion/transitions/clock-wipe';
import {iris} from '@remotion/transitions/iris';
import {none} from '@remotion/transitions/none';

type Palette = Record<string, string>;

type SceneDef = {
  id: string;
  name: string;
  renderer: string;
  variant: string;
  lighting: string;
  image?: string | null;
  palette: Palette;
};

type Outfit = {
  name: string;
  spineBounds?: {x: number; y: number; width: number; height: number; imageWidth: number; imageHeight: number; bubbleAnchors?: Record<string, {x: number; y: number; width: number; dotX?: number; dotY?: number; dotStep?: number}>};
  sprites: Record<string, string>;
  fallbacks?: string[];
};

type CharacterData = {
  name: string;
  color: string;
  club?: string;
  school?: string;
  default_outfit: string;
  voice?: { provider?: string; model?: string; voice_id?: string };
  outfits: Record<string, Outfit>;
};

type Line = {
  id: string;
  speaker: string;
  outfit: string;
  emotion: string;
  text: string;
  from: number;
  durationInFrames: number;
  /** Optional: stills/review scenes may carry captions without audio. */
  audio?: string;
};

type SfxConfig = {
  click?: string;
  select?: string;
  hover?: string;
};

type ButtonDef = {
  label: string;
  x?: number;
  y?: number;
  width?: number;
  pressFrame?: number;
  variant?: 'primary' | 'secondary';
};

type ChoiceDef = {
  prompt?: string;
  options: string[];
  selected?: number;
  /** Frames (relative to the owning shot) before the list appears. */
  fromFrame?: number;
  /** Frame (relative to the owning shot) where the selected option is confirmed. */
  selectFrame?: number;
  /** Frame (relative to the owning shot) where the list disappears. */
  hideFrame?: number;
};

type CharacterMotion = {
  fromX?: number;
  toX?: number;
  fromBottom?: number;
  toBottom?: number;
  fromScale?: number;
  toScale?: number;
  startFrame?: number;
  endFrame?: number;
  ease?: 'linear' | 'ease-in-out';
  /** Split the move into this many hops: each hop springs forward and lands. */
  hops?: number;
  /** Height of each hop as a fraction of the frame; default 0.05. */
  hopLift?: number;
};

type CharacterTurn = {
  /** Direction the sprite faces after the turn. */
  to: 'left' | 'right';
  /** Frame relative to the shot where the turn starts. */
  startFrame: number;
  durationInFrames: number;
};

type TransitionType = 'fade' | 'slide' | 'wipe' | 'flip' | 'clock-wipe' | 'iris' | 'none';

/** Transition entering a shot. prepare.py resolves it; `null` means a hard cut. */
type ShotTransition = {
  type: TransitionType;
  durationInFrames: number;
  direction?: string;
  easing?: 'linear' | 'ease-in-out';
  perspective?: number;
  shouldFadeOutExitingScene?: boolean;
};

type CharacterLabel = {
  text: string;
  /** normal = blue chip, secret = pink chip. */
  tone?: 'normal' | 'secret';
  rotate?: number;
};

type Shot = {
  id: string;
  from: number;
  durationInFrames: number;
  transition?: ShotTransition | null;
  scene?: SceneDef | null;
  background?: { type?: string; value?: string; path?: string };
  camera: string;
  /** Character held in the spotlight: others and the room dim around them. */
  focus?: string | null;
  /** Inner monologue. Only shown after the shot's last line ends. */
  monologue?: { speaker: string; text: string; audio?: string | null } | null;
  /** Vote result tags shown on the characters after the last line. */
  voteTags?: Array<{ speaker: string; text: string }> | null;
  /** One-shot system voice (vote announcer) played at the start of the shot. */
  systemVoice?: string | null;
  characters: Array<{
    id: string;
    outfit: string;
    x: number;
    bottom: number;
    height: number;
    scale: number;
    entrance: string;
    exit: string;
    emotion: string;
    /** Word tag above the head (meme overlay). */
    label?: CharacterLabel;
    /** Keep the emotion of this character's last spoken line instead of reverting. */
    holdEmotion?: boolean;
    /** Timed expression changes that do not wait for the character's next line. */
    emotionCues?: Array<{ emotion: string; startFrame: number }>;
    actions?: Array<{ name: string; startFrame: number }>;
    bubbles?: Array<{ name: keyof typeof bubblePresets; startFrame: number; sound?: boolean; images?: string[]; balloon?: string; image?: string; audio?: string }>;
    facing?: 'left' | 'right';
    turns?: CharacterTurn[];
    motion?: CharacterMotion | null;
  }>;
  lines: Line[];
  choices?: ChoiceDef;
  buttons?: ButtonDef[];
};

type Scene = {
  schema_version: number;
  episode: {
    id: string;
    title: string;
    width: number;
    height: number;
    fps: number;
    durationInFrames: number;
    style?: { accent?: string; font_family?: string; caption_style?: 'ba' | 'meme' };
    subtitle?: { max_chars_per_line?: number; max_lines?: number };
  };
  characters: Record<string, CharacterData>;
  ui?: {
    kit?: string;
    sfx?: SfxConfig;
    lineClick?: boolean;
    lineClickVolume?: number;
  };
  intro?: { durationInFrames: number; kicker?: string; title?: string; subtitle?: string };
  bgm?: {
    src: string;
    volume?: number;
    loop?: boolean;
    fadeInFrames?: number;
    fadeOutFrames?: number;
  } | null;
  shots: Shot[];
};

const fallbackScene: Scene = {
  schema_version: 2,
  episode: {
    id: 'empty',
    title: '',
    width: 1280,
    height: 720,
    fps: 30,
    durationInFrames: 30,
    style: { accent: '#e78caf', font_family: 'PingFang SC' },
  },
  characters: {},
  shots: [],
};

const clamp = {
  extrapolateLeft: 'clamp' as const,
  extrapolateRight: 'clamp' as const,
};

// ── Transitions ─────────────────────────────────────────────────────────────

// The presentation components all take presentation-specific props, so they are
// widened to a common shape here; each branch passes only its own props.
type Presentation = TransitionPresentation<Record<string, unknown>>;

const transitionPresentation = (
  transition: ShotTransition,
  width: number,
  height: number,
): Presentation => {
  switch (transition.type) {
    case 'slide':
      return slide({
        direction: transition.direction as SlideDirection | undefined,
      }) as unknown as Presentation;
    case 'wipe':
      return wipe({
        direction: transition.direction as WipeDirection | undefined,
      }) as unknown as Presentation;
    case 'flip':
      return flip({
        direction: transition.direction as FlipDirection | undefined,
        perspective: transition.perspective,
      }) as unknown as Presentation;
    case 'clock-wipe':
      return clockWipe({width, height}) as unknown as Presentation;
    case 'iris':
      return iris({width, height}) as unknown as Presentation;
    case 'none':
      return none() as unknown as Presentation;
    case 'fade':
    default:
      return fade({
        shouldFadeOutExitingScene: transition.shouldFadeOutExitingScene,
      }) as unknown as Presentation;
  }
};

const transitionTiming = (transition: ShotTransition) =>
  linearTiming({
    durationInFrames: transition.durationInFrames,
    easing: transition.easing === 'ease-in-out' ? Easing.inOut(Easing.ease) : Easing.linear,
  });

// ── Audio helpers ───────────────────────────────────────────────────────────

const Sfx: React.FC<{
  src?: string;
  from: number;
  durationInFrames?: number;
  volume?: number;
}> = ({ src, from, durationInFrames = 12, volume = 0.5 }) => {
  if (!src) return null;
  return (
    <Sequence from={Math.max(0, Math.round(from))} durationInFrames={durationInFrames}>
      <Audio src={staticFile(src)} volume={volume} />
    </Sequence>
  );
};

// ── Scene backdrop ──────────────────────────────────────────────────────────

// Backgrounds are static: no Ken Burns drift, the shot's `camera` is the only
// thing that may move the frame.
const ImageStage: React.FC<{ scene: SceneDef }> = ({ scene }) => {
  const p = scene.palette;
  const lighting = scene.lighting || 'day';

  return (
    <AbsoluteFill style={{ background: p.ink || '#1a2028', overflow: 'hidden' }}>
      {scene.image ? (
        <Img
          src={staticFile(scene.image)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            filter:
              lighting === 'monitor'
                ? 'saturate(0.9) brightness(0.82)'
                : lighting === 'lamp'
                  ? 'saturate(0.95) brightness(0.9)'
                  : 'saturate(1.02)',
          }}
        />
      ) : (
        <AbsoluteFill
          style={{
            background: `radial-gradient(80% 70% at 55% 45%, ${p.wallTop || '#2b3442'} 0%, ${
              p.wallBottom || '#171d27'
            } 60%, ${p.ink || '#0c1118'} 100%)`,
          }}
        />
      )}

      {/* 光线统一：冷光 / 台灯 / 自然光 */}
      <AbsoluteFill
        style={{
          background:
            lighting === 'monitor'
              ? 'linear-gradient(180deg, rgba(90,140,190,0.22), rgba(10,18,30,0.42))'
              : lighting === 'lamp'
                ? 'linear-gradient(180deg, rgba(255,180,110,0.20), rgba(40,24,40,0.34))'
                : 'linear-gradient(180deg, rgba(255,240,215,0.10), rgba(30,40,55,0.14))',
          mixBlendMode: 'soft-light',
        }}
      />

      {/* 暗角与顶部压暗，保证字幕/水印可读 */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(75% 65% at 50% 42%, rgba(0,0,0,0) 42%, rgba(6,10,16,0.22) 72%, rgba(6,10,16,0.55) 100%)',
        }}
      />
      <AbsoluteFill
        style={{
          background: 'linear-gradient(180deg, rgba(6,10,16,0.28), rgba(6,10,16,0) 22%)',
        }}
      />
    </AbsoluteFill>
  );
};

const GradientBackground: React.FC<{ background?: Shot['background'] }> = ({ background }) => {
  if (background?.type === 'image' && background.path) {
    return (
      <AbsoluteFill>
        <Img
          src={staticFile(background.path)}
          style={{ width: '100%', height: '100%', objectFit: 'cover' }}
        />
      </AbsoluteFill>
    );
  }
  return (
    <AbsoluteFill
      style={{ background: background?.value || 'linear-gradient(125deg,#e4f7f5,#fbe6ed)' }}
    />
  );
};

const SceneBackdrop: React.FC<{ shot: Shot }> = ({ shot }) => {
  if (shot.scene?.renderer === 'image-stage') {
    return <ImageStage scene={shot.scene} />;
  }
  return <GradientBackground background={shot.background} />;
};

// ── Characters ──────────────────────────────────────────────────────────────

const CharacterFigure: React.FC<{
  entry: Shot['characters'][number];
  data: CharacterData;
  activeLine?: Line;
  /** Emotion of this character's latest line at or before the current frame. */
  heldEmotion?: string;
  shadowColor: string;
  shotDuration: number;
}> = ({ entry, data, activeLine, heldEmotion, shadowColor, shotDuration }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const action = sampleActions(entry.actions, frame, fps);
  const latestBubble = [...(entry.bubbles ?? [])].filter((cue) => cue.startFrame <= frame)
    .sort((a, b) => a.startFrame - b.startFrame).at(-1);
  if (!data) return null;

  const outfit = data.outfits[entry.outfit] || data.outfits[data.default_outfit];
  if (!outfit) return null;
  const isSpeaking = activeLine?.speaker === entry.id;
  const isDimmed = Boolean(activeLine) && !isSpeaking;
  // Latest timed expression cue wins — it can interrupt a spoken line, e.g. a
  // blush that lands one beat into a denial. Otherwise a speaking line's
  // emotion, then the held emotion, then the shot's standing face.
  let cued: string | undefined;
  for (const cue of entry.emotionCues ?? []) {
    if (frame >= cue.startFrame) cued = cue.emotion;
  }
  const spoken = isSpeaking
    ? activeLine?.emotion || entry.emotion
    : heldEmotion || entry.emotion;
  const emotion = cued || spoken;
  const sprites = outfit.sprites || {};
  const sprite = sprites[emotion] || sprites.default;
  if (!sprite) return null;

  const entrance = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 16 });
  let tx = 0;

  // Blocking: characters can slide between marks inside a shot. The slide is a
  // pure translation; there is no walk cycle or step bob.
  const motion = entry.motion;
  let px = entry.x;
  let ground = entry.bottom;
  let lift = 0;
  let poseScale = entry.scale;
  if (motion) {
    const start = motion.startFrame ?? 0;
    const end = Math.max(start + 1, motion.endFrame ?? shotDuration);
    const fromX = motion.fromX ?? entry.x;
    const toX = motion.toX ?? entry.x;
    const fromBottom = motion.fromBottom ?? entry.bottom;
    const toBottom = motion.toBottom ?? entry.bottom;
    const fromScale = motion.fromScale ?? entry.scale;
    const toScale = motion.toScale ?? entry.scale;
    const hops = Math.max(0, Math.floor(motion.hops ?? 0));
    if (hops > 1) {
      // Hop block: the distance is split into equal jumps. Each jump eases out
      // along x and lifts in a sine arc, so the character lands and takes off
      // again instead of gliding between marks.
      const span = end - start;
      const hopLength = span / hops;
      const local = Math.min(span, Math.max(0, frame - start)) / hopLength;
      const index = Math.min(hops - 1, Math.floor(local));
      const u = frame >= end ? 1 : local - index;
      const eased = u * u * (3 - 2 * u);
      const t = (index + eased) / hops;
      px = interpolate(t, [0, 1], [fromX, toX]);
      ground = interpolate(t, [0, 1], [fromBottom, toBottom]);
      poseScale = interpolate(t, [0, 1], [fromScale, toScale]);
      lift = Math.sin(Math.PI * u) * (motion.hopLift ?? 0.05);
    } else {
      const raw = interpolate(frame, [start, end], [0, 1], clamp);
      const t = motion.ease === 'linear' ? raw : raw * raw * (3 - 2 * raw);
      px = interpolate(t, [0, 1], [fromX, toX]);
      ground = interpolate(t, [0, 1], [fromBottom, toBottom]);
      poseScale = interpolate(t, [0, 1], [fromScale, toScale]);
    }
  }
  const pBottom = ground + lift;

  if (entry.entrance === 'slide-in-right') {
    tx = interpolate(entrance, [0, 1], [Math.max(180, height * 0.35), 0]);
  } else if (entry.entrance === 'slide-in-left') {
    tx = interpolate(entrance, [0, 1], [-Math.max(180, height * 0.35), 0]);
  }

  // Facing: "right" keeps the sprite as drawn, "left" mirrors it. A turn
  // animates the mirror across scaleX so the character visibly turns around.
  let flip = entry.facing === 'left' ? -1 : 1;
  for (const turn of entry.turns ?? []) {
    const target = turn.to === 'left' ? -1 : 1;
    const start = turn.startFrame ?? 0;
    const duration = Math.max(1, turn.durationInFrames ?? 6);
    if (frame < start) break;
    if (frame >= start + duration) {
      flip = target;
      continue;
    }
    const raw = (frame - start) / duration;
    const eased = raw * raw * (3 - 2 * raw);
    flip += (target - flip) * eased;
  }

  // No idle bob, breathing pulse or speaking shake: BA sprites stand still.

  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: `${px * 100}%`,
          bottom: `${ground * 100}%`,
          width: `${entry.height * 34 * (1 - lift * 6)}%`,
          height: `${entry.height * 5}%`,
          transform: 'translateX(-50%)',
          borderRadius: '50%',
          background: shadowColor,
          opacity: (1 - lift * 5) * action.opacity,
          filter: 'blur(14px)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: `${px * 100}%`,
          bottom: `${pBottom * 100}%`,
          height: `${entry.height * 100}%`,
          width: outfit.spineBounds ? height * entry.height * outfit.spineBounds.imageWidth / outfit.spineBounds.imageHeight : 'max-content',
          transform: `translateX(-50%) translate(${tx}px, 0px) translate(${action.x * 100}%, ${action.y * 100}%) scale(${poseScale * action.scale}) rotate(${action.angle}deg) scaleX(${flip})`,
          transformOrigin: action.origin,
          opacity: (entry.entrance === 'fade-in' ? entrance : 1) * action.opacity,
        }}
      >
        <Img src={staticFile(sprite)} style={{height: '100%', width: 'auto', display: 'block', filter: isDimmed
          ? 'brightness(0.66) saturate(0.82) drop-shadow(0 10px 22px rgba(20,30,45,0.20))'
          : 'drop-shadow(0 16px 30px rgba(20,30,45,0.22))'}} />
      {(entry.bubbles ?? []).map((cue, index) => {
        const seconds = (frame - cue.startFrame) / fps;
        const preset = bubblePresets[cue.name];
        const opacity = bubbleOpacity(seconds, preset.seconds);
        const spriteHeight = height * entry.height;
        const geometry = bubbleGeometry(preset, spriteHeight, outfit.spineBounds, cue.name);
        const images = cue.images ?? [cue.balloon, cue.image];
        return <React.Fragment key={index}>
          {cue.sound !== false && cue.audio ? <Sequence from={cue.startFrame}><Audio src={staticFile(cue.audio)} volume={0.5} /></Sequence> : null}
          {cue === latestBubble && opacity > 0 ? (
            <div style={{
              position: 'absolute',
              left: geometry.x,
              top: geometry.y,
              width: geometry.width,
              aspectRatio: preset.aspectRatio ?? 1,
              opacity,
              transform: cue.name === 'Shy' && !outfit.spineBounds?.bubbleAnchors?.Dot ? 'translate(-100%, -100%)' : undefined,
            }}>
              {bubbleLayers(cue.name, seconds, outfit.spineBounds?.bubbleAnchors?.[cue.name]).map((layer, i) => images[layer.image] ? <Img key={i} src={staticFile(images[layer.image]!)} style={{position: 'absolute', width: `${layer.width * 100}%`, left: `${layer.x * 100}%`, top: `${layer.y * 100}%`, opacity: layer.opacity, transformOrigin: '0 0', transform: `rotate(${layer.angle}deg) scale(${layer.scale}, ${layer.scale * (layer.scaleY ?? 1)}) translate(${-(layer.anchorX ?? 0) * 100}%, ${-(layer.anchorY ?? 0) * 100}%)`}} /> : null)}
            </div>
          ) : null}
        </React.Fragment>;
      })}
      </div>
    </>
  );
};

// ── Blue Archive UI kit ─────────────────────────────────────────────────────
//
// Reference: in-game story UI captured from Blue Archive (JP).
// - dialogue: bottom scrim, inline name + club, hairline separator, cyan next arrow
// - choices: light faceted rounded bars with dark text (not navy panels)
// - buttons: white / yellow skewed pills with italic dark labels
// - click effect: expanding dashed halo + diamond sparks (BASpark / ba-click-fx)

const ClickBurst: React.FC<{ x: number; y: number; startFrame: number }> = ({
  x,
  y,
  startFrame,
}) => {
  const frame = useCurrentFrame();
  const t = frame - startFrame;
  if (t < 0 || t > 16) return null;
  const p = t / 16;
  const ease = 1 - Math.pow(1 - p, 3);
  const radius = 12 + ease * 58;
  const opacity = 1 - p;
  const glowScale = 0.6 + ease * 1.15;
  const sparks = Array.from({ length: 10 }, (_, index) => {
    const angle = (index / 10) * Math.PI * 2 + 0.3;
    const distance = 12 + ease * 64;
    return {
      key: index,
      x: Math.cos(angle) * distance,
      y: Math.sin(angle) * distance,
      opacity: opacity,
    };
  });

  return (
    <div
      style={{
        position: 'absolute',
        left: `${x * 100}%`,
        top: `${y * 100}%`,
        width: 0,
        height: 0,
        pointerEvents: 'none',
        zIndex: 40,
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: -60,
          top: -60,
          width: 120,
          height: 120,
          borderRadius: '50%',
          background:
            'radial-gradient(circle, rgba(165,238,255,0.6) 0%, rgba(120,210,255,0.18) 42%, rgba(120,210,255,0) 72%)',
          transform: `scale(${glowScale})`,
          opacity: opacity * 0.85,
        }}
      />
      <svg
        width={160}
        height={160}
        viewBox="-80 -80 160 160"
        style={{ position: 'absolute', left: -80, top: -80, overflow: 'visible' }}
      >
        <circle
          r={radius}
          fill="none"
          stroke="#9beeff"
          strokeWidth={3}
          strokeDasharray="8 7"
          opacity={opacity}
          transform={`rotate(${t * 7})`}
        />
        <circle
          r={radius * 0.62}
          fill="none"
          stroke="#ffffff"
          strokeWidth={2}
          opacity={opacity * 0.85}
        />
        <circle r={6 + (1 - p) * 10} fill="#ffffff" opacity={Math.max(0, 1 - p * 2.5) * 0.9} />
        {sparks.map((spark, index) => (
          <rect
            key={spark.key}
            x={spark.x - 3.5}
            y={spark.y - 3.5}
            width={7}
            height={7}
            fill={index % 2 ? '#9beeff' : '#ffffff'}
            opacity={spark.opacity}
            transform={`rotate(45 ${spark.x} ${spark.y})`}
          />
        ))}
      </svg>
    </div>
  );
};

const StoryChrome: React.FC = () => {
  const { height } = useVideoConfig();
  const pillHeight = height * 0.042;
  const pillWidth = height * 0.108;
  const base: React.CSSProperties = {
    width: pillWidth,
    height: pillHeight,
    transform: 'skewX(-9deg)',
    borderRadius: 3,
    border: '1.5px solid rgba(255,255,255,0.9)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'Arial, Helvetica, sans-serif',
    fontStyle: 'italic',
    fontWeight: 900,
    fontSize: pillHeight * 0.55,
    letterSpacing: 1.2,
    color: '#22344a',
    filter: 'drop-shadow(0 3px 6px rgba(0,0,0,0.25))',
  };
  return (
    <div
      style={{
        position: 'absolute',
        top: height * 0.024,
        right: height * 0.04,
        display: 'flex',
        gap: height * 0.012,
        zIndex: 35,
      }}
    >
      <div
        style={{
          ...base,
          background: 'linear-gradient(180deg,#ffe874,#ffd21f)',
          boxShadow: '0 0 20px rgba(255,215,60,0.55)',
        }}
      >
        <span style={{ transform: 'skewX(9deg)' }}>AUTO</span>
      </div>
      <div
        style={{
          ...base,
          background: 'linear-gradient(180deg,#fdfcf9,#ece9e2)',
        }}
      >
        <span style={{ transform: 'skewX(9deg)' }}>MENU</span>
      </div>
    </div>
  );
};

const BAButton: React.FC<{ btn: ButtonDef; sfx?: string }> = ({ btn, sfx }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const primary = btn.variant === 'primary';
  const pressFrame = btn.pressFrame;
  const press =
    pressFrame != null
      ? spring({
          frame: frame - pressFrame,
          fps,
          config: { damping: 12, stiffness: 240, mass: 0.6 },
          durationInFrames: 16,
        })
      : 0;
  const scale =
    pressFrame != null ? interpolate(press, [0, 0.35, 1], [1, 0.93, 1], clamp) : 1;
  const glow =
    pressFrame != null ? interpolate(press, [0, 0.3, 1], [0, 0.95, 0], clamp) : 0;
  const x = btn.x ?? 0.5;
  const y = btn.y ?? 0.5;
  const width = (btn.width ?? 0.22) * 100;

  return (
    <>
      <div
        style={{
          position: 'absolute',
          left: `${x * 100}%`,
          top: `${y * 100}%`,
          width: `${width}%`,
          height: height * 0.075,
          transform: `translate(-50%,-50%) skewX(-9deg) scale(${scale})`,
          transformOrigin: 'center',
          filter: 'drop-shadow(0 6px 12px rgba(0,0,0,0.28))',
          zIndex: 30,
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: primary
              ? 'linear-gradient(180deg,#ffe771,#ffd21f)'
              : 'linear-gradient(180deg,#fdfcf9,#ece9e2)',
            border: '2px solid rgba(255,255,255,0.92)',
            borderRadius: 4,
            boxShadow:
              'inset 0 -3px 0 rgba(0,0,0,0.12), inset 0 2px 0 rgba(255,255,255,0.85)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transform: 'skewX(9deg)',
            fontFamily: 'Arial, Helvetica, sans-serif',
            fontStyle: 'italic',
            fontWeight: 900,
            fontSize: height * 0.034,
            letterSpacing: 1.5,
            color: primary ? '#3a2a00' : '#22344a',
          }}
        >
          {btn.label}
        </div>
        {glow > 0 ? (
          <div
            style={{
              position: 'absolute',
              inset: -3,
              borderRadius: 6,
              border: `2px solid ${primary ? '#fff3b0' : '#c5ecff'}`,
              opacity: glow,
              boxShadow: `0 0 24px ${primary ? 'rgba(255,220,80,0.85)' : 'rgba(140,220,255,0.85)'}`,
            }}
          />
        ) : null}
        {pressFrame != null ? (
          <div style={{ position: 'absolute', inset: 0, transform: 'skewX(9deg)' }}>
            <ClickBurst x={0.5} y={0.5} startFrame={pressFrame} />
          </div>
        ) : null}
      </div>
      {pressFrame != null ? (
        <Sfx src={sfx} from={pressFrame} durationInFrames={12} volume={0.55} />
      ) : null}
    </>
  );
};

// 游戏内的固定打字速度：15 字 / 1s。
const TYPEWRITER_CHARS_PER_SECOND = 15;
// 台词出现后略等两帧再开始出字，避免和对话框一起“闪”出来。
const TYPEWRITER_START_FRAMES = 2;

const DialogueBox: React.FC<{
  speaker: string;
  text: string;
  character?: CharacterData;
  prompt?: boolean;
  lineFrame: number;
}> = ({ speaker, text, character, prompt, lineFrame }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const appear = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 10 });
  const textOpacity = interpolate(frame, [0, 6], [0, 1], clamp);
  const blink = 0.4 + 0.6 * Math.abs(Math.sin(frame / 10));
  const glyphs = Array.from(text);
  const framesPerGlyph = fps / TYPEWRITER_CHARS_PER_SECOND;
  const visibleGlyphs = Math.min(
    glyphs.length,
    Math.max(0, Math.floor((lineFrame - TYPEWRITER_START_FRAMES) / framesPerGlyph) + 1),
  );
  const typing = visibleGlyphs < glyphs.length;

  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      {/* 底部压暗，不画面板：游戏内只有一层逐渐加深的 scrim */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: height * 0.42,
          background:
            'linear-gradient(to top, rgba(4,10,17,0.88) 0%, rgba(4,10,17,0.58) 34%, rgba(4,10,17,0.20) 68%, rgba(4,10,17,0) 100%)',
          opacity: appear,
        }}
      />

      {/* 姓名 + 社团 */}
      <div
        style={{
          position: 'absolute',
          left: '9%',
          right: '9%',
          bottom: height * 0.27,
          display: 'flex',
          alignItems: 'baseline',
          gap: height * 0.018,
          opacity: appear,
          transform: `translateY(${interpolate(appear, [0, 1], [8, 0], clamp)}px)`,
        }}
      >
        <div
          style={{
            fontSize: height * 0.043,
            fontWeight: 700,
            letterSpacing: 1.5,
            color: '#ffffff',
            textShadow: '0 2px 12px rgba(0,0,0,0.65)',
            whiteSpace: 'nowrap',
          }}
        >
          {character?.name || speaker}
        </div>
        {character?.club ? (
          <div
            style={{
              fontSize: height * 0.036,
              fontWeight: 600,
              letterSpacing: 1,
              color: '#7fd8ff',
              textShadow: '0 2px 10px rgba(0,0,0,0.55)',
              whiteSpace: 'nowrap',
            }}
          >
            {character.club}
          </div>
        ) : null}
      </div>

      {/* 细分割线 */}
      <div
        style={{
          position: 'absolute',
          left: '9%',
          right: '9%',
          bottom: height * 0.25,
          height: 1,
          background:
            'linear-gradient(90deg, rgba(255,255,255,0.58), rgba(255,255,255,0.42) 72%, rgba(255,255,255,0.16))',
          opacity: appear,
        }}
      />

      {/* 台词 */}
      <div
        style={{
          position: 'absolute',
          left: '9%',
          right: '9%',
          top: height * 0.76,
          fontSize: height * 0.038,
          lineHeight: 1.55,
          letterSpacing: 0.5,
          color: '#ffffff',
          whiteSpace: 'pre-wrap',
          opacity: textOpacity,
          textShadow: '0 2px 10px rgba(0,0,0,0.7)',
        }}
      >
        {glyphs.slice(0, visibleGlyphs).join('')}
      </div>

      {/* 右下闪烁的青色三角：台词打完才出现，提示可以继续 */}
      {prompt || typing ? null : (
        <div
          style={{
            position: 'absolute',
            right: '9.6%',
            bottom: height * 0.07,
            width: 0,
            height: 0,
            borderLeft: `${height * 0.013}px solid transparent`,
            borderRight: `${height * 0.013}px solid transparent`,
            borderTop: `${height * 0.017}px solid #6fe3ff`,
            opacity: blink,
            filter: 'drop-shadow(0 0 10px rgba(99,217,255,0.9))',
          }}
        />
      )}
    </AbsoluteFill>
  );
};

const ChoiceBox: React.FC<{
  choices: ChoiceDef;
  sfx?: SfxConfig;
}> = ({ choices, sfx }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const from = Math.max(0, choices.fromFrame ?? 0);
  const select = Math.max(from, choices.selectFrame ?? from + 30);
  const hide = Math.max(select + 1, choices.hideFrame ?? select + 22);
  if (frame < from || frame >= hide) return null;

  const local = frame - from;
  const fade = interpolate(frame, [hide - 8, hide], [1, 0], clamp);
  const selected = choices.selected ?? 0;
  const selectedNow = frame >= select;
  // Reference choice bars are shallow parallelograms, not rounded buttons.
  const optionWidth = width * 0.70;
  const optionHeight = height * 0.09;
  const gap = height * 0.035;
  const baseTop = height * (choices.options.length >= 3 ? 0.22 : 0.28);
  const selectedY =
    (baseTop + selected * (optionHeight + gap) + optionHeight / 2) / height;

  return (
    <div style={{ position: 'absolute', inset: 0, opacity: fade, zIndex: 25 }}>
      {choices.options.map((option, index) => {
        const top = baseTop + index * (optionHeight + gap);
        const enter = spring({
          frame: local - index * 3,
          fps,
          config: { damping: 18, stiffness: 160 },
          durationInFrames: 14,
        });
        return (
          <div
            key={`${index}-${option}`}
            style={{
              position: 'absolute',
              left: '50%',
              top,
              width: optionWidth,
              height: optionHeight,
              transform: `translateX(-50%) translateY(${interpolate(
                enter,
                [0, 1],
                [14, 0],
                clamp,
              )}px)`,
              opacity: enter,
            }}
          >
            <div
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: height * 0.004,
                transform: 'skewX(-10deg)',
                background: 'linear-gradient(90deg,#c9e2ec 0%,#f5f7f6 32%,#f5f7f6 68%,#c9e2ec 100%)',
                border: `${height * 0.004}px solid #f8fbfc`,
                boxShadow: '0 2px 2px rgba(30,50,65,0.16)',
                overflow: 'hidden',
              }}
            >
              <svg width="100%" height="100%" viewBox="0 0 1000 100" preserveAspectRatio="none"
                style={{ position: 'absolute', inset: 0 }}>
                {[0, 55, 110, 835, 890, 945].map((x, i) => (
                  <polygon key={x} points={`${x},100 ${x + 55},0 ${x + 110},100`}
                    fill={i % 2 ? '#ffffff' : '#a5d1e1'} opacity={0.18} />
                ))}
              </svg>
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: `0 ${height * 0.032}px`,
                  fontSize: height * 0.040,
                  transform: 'skewX(10deg)',
                  fontWeight: 400,
                  letterSpacing: 0.5,
                  color: '#1f2e3b',
                  textAlign: 'center',
                }}
              >
                {option}
              </div>
            </div>
          </div>
        );
      })}

      <Sfx src={sfx?.hover} from={from} durationInFrames={10} volume={0.28} />
      <Sfx src={sfx?.select} from={select} durationInFrames={12} volume={0.65} />
      {selectedNow ? (
        <ClickBurst x={0.5 - 0.35} y={selectedY} startFrame={select} />
      ) : null}
    </div>
  );
};

const Intro: React.FC<{ intro: NonNullable<Scene['intro']>; scene: Scene }> = ({
  intro,
  scene,
}) => {
  const frame = useCurrentFrame();
  const { height } = useVideoConfig();
  const duration = intro.durationInFrames;
  const fadeOut = interpolate(frame, [duration - 14, duration], [1, 0], clamp);
  const bandIn = interpolate(frame, [2, 14], [0, 1], clamp);
  const kickerIn = interpolate(frame, [6, 18], [0, 1], clamp);
  const titleIn = interpolate(frame, [10, 26], [0, 1], clamp);
  const subtitleIn = titleIn;
  const firstShot = scene.shots[0];
  const bandTop = height * 0.38;
  const bandHeight = height * 0.24;

  return (
    <AbsoluteFill style={{ opacity: fadeOut, overflow: 'hidden', background: '#071019' }}>
      {firstShot ? (
        <AbsoluteFill style={{ opacity: 0.38, filter: 'blur(3px) brightness(0.72)' }}>
          <SceneBackdrop shot={firstShot} />
        </AbsoluteFill>
      ) : null}
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(4,10,18,0.55) 0%, rgba(4,10,18,0.42) 48%, rgba(4,10,18,0.68) 100%)',
        }}
      />

      {/* 全宽浅蓝标题带：BA 章节/话数标题卡 */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: bandTop,
          height: bandHeight,
          overflow: 'hidden',
          opacity: bandIn,
          transformOrigin: 'center',
          boxShadow:
            'inset 0 1px 0 rgba(255,255,255,0.6), inset 0 -1px 0 rgba(120,160,190,0.28)',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(180deg,#f3fafe 0%,#dcecf7 48%,#c4daea 100%)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: '26%',
            clipPath: 'polygon(0 100%, 0 0, 100% 100%)',
            background: 'rgba(255,255,255,0.45)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: '18%',
            top: 0,
            bottom: 0,
            width: '16%',
            clipPath: 'polygon(0 0, 100% 0, 0 100%)',
            background: 'rgba(120,170,205,0.16)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            right: 0,
            top: 0,
            bottom: 0,
            width: '24%',
            clipPath: 'polygon(100% 0, 100% 100%, 0 0)',
            background: 'rgba(140,180,210,0.22)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            right: '12%',
            top: 0,
            bottom: 0,
            width: '14%',
            clipPath: 'polygon(30% 0, 100% 0, 100% 100%, 0 100%)',
            background: 'rgba(255,255,255,0.28)',
          }}
        />

        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: height * 0.014,
          }}
        >
          <div
            style={{
              opacity: kickerIn,
              fontSize: height * 0.032,
              fontWeight: 800,
              letterSpacing: 0,
              color: '#2d4a6b',
              fontFamily: 'Arial, Helvetica, sans-serif',
            }}
          >
            <span
              style={{
                borderBottom: `${height * 0.005}px solid #ffd84d`,
                paddingBottom: height * 0.004,
              }}
            >
              {intro.kicker}
            </span>
          </div>
          <div
            style={{
              opacity: titleIn,
              fontSize: height * 0.065,
              fontWeight: 800,
              letterSpacing: 0,
              color: '#2d4a6b',
              textShadow: '0 2px 0 rgba(255,255,255,0.55)',
            }}
          >
            {intro.title}
          </div>
          {intro.subtitle ? (
            <div
              style={{
                opacity: subtitleIn,
                fontSize: height * 0.026,
                letterSpacing: 0,
                color: '#3f5d78',
              }}
            >
              {intro.subtitle}
            </div>
          ) : null}
        </div>
      </div>

      <Sfx src={scene.ui?.sfx?.click} from={22} durationInFrames={10} volume={0.3} />
    </AbsoluteFill>
  );
};

// ── Meme overlays: outlined word tags + giant captions ─────────────────────

const MEME_FONT = '"Microsoft YaHei", "Noto Sans SC", "Source Han Sans SC", sans-serif';

// Two stacked text layers: a thick outer stroke behind, then fill + inner
// white stroke on top. Gives the double outline used by the reference memes.
const OutlineText: React.FC<{
  text: string;
  fill: string;
  inner: string;
  outer: string;
  size: number;
  innerWidth: number;
  outerWidth: number;
  style?: React.CSSProperties;
}> = ({ text, fill, inner, outer, size, innerWidth, outerWidth, style }) => (
  <span
    style={{
      position: 'relative',
      display: 'inline-block',
      fontFamily: MEME_FONT,
      fontWeight: 900,
      fontSize: size,
      lineHeight: 1.12,
      letterSpacing: size * 0.015,
      whiteSpace: 'nowrap',
      ...style,
    }}
  >
    <span
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        color: 'transparent',
        WebkitTextStroke: `${outerWidth}px ${outer}`,
      }}
    >
      {text}
    </span>
    <span
      style={{
        position: 'relative',
        color: fill,
        WebkitTextStroke: `${innerWidth}px ${inner}`,
      }}
    >
      {text}
    </span>
  </span>
);

const WordLabels: React.FC<{ shot: Shot; height: number }> = ({ shot, height }) => {
  const frame = useCurrentFrame();
  return (
  <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', zIndex: 22 }}>
    {shot.characters
      .filter((entry) => entry.label)
      .map((entry) => {
        const label = entry.label!;
        const secret = label.tone === 'secret';
        const size = height * 0.058;
        const left = Math.min(92, Math.max(8, entry.x * 100));
        // A character that runs off-screen takes their word tag with them.
        const motion = entry.motion;
        if (motion?.startFrame != null && frame >= motion.startFrame) return null;
        return (
          <div
            key={`label-${entry.id}`}
            style={{
              position: 'absolute',
              left: `${left}%`,
              top: height * 0.018,
              transform: `translateX(-50%) rotate(${label.rotate ?? -3}deg)`,
            }}
          >
            <OutlineText
              text={label.text}
              fill={secret ? '#ff9ab7' : '#a9dcff'}
              inner="#ffffff"
              outer={secret ? '#ff5f8f' : '#123a5a'}
              size={size}
              innerWidth={size * 0.05}
              outerWidth={size * 0.15}
            />
          </div>
        );
      })}
  </div>
  );
};

const MemeCaption: React.FC<{
  text: string;
  color: string;
  width: number;
  height: number;
}> = ({ text, color, width, height }) => {
  const base = height * 0.098;
  const size = Math.min(base, (width * 0.84) / Math.max(1, Array.from(text).length * 1.02));
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: height * 0.06,
        display: 'flex',
        justifyContent: 'center',
        pointerEvents: 'none',
        zIndex: 32,
      }}
    >
      <div style={{ transform: 'rotate(-1.2deg)' }}>
        <OutlineText
          text={text}
          fill={color}
          inner="#ffffff"
          outer={color}
          size={size}
          innerWidth={size * 0.055}
          outerWidth={size * 0.15}
        />
      </div>
    </div>
  );
};

const ThoughtText: React.FC<{
  text: string;
  color: string;
  width: number;
  height: number;
}> = ({ text, color, width, height }) => {
  const size = Math.min(height * 0.048, (width * 0.7) / Math.max(1, Array.from(text).length * 1.02));
  return (
    <div
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: height * 0.17,
        display: 'flex',
        justifyContent: 'center',
        pointerEvents: 'none',
        zIndex: 31,
      }}
    >
      <div
        style={{
          transform: 'rotate(-1deg)',
          opacity: 0.96,
          filter: `drop-shadow(0 0 ${size * 0.5}px ${color}66)`,
        }}
      >
        <OutlineText
          text={text}
          fill="#ffffff"
          inner="#ffffff"
          outer="#0b1119"
          size={size}
          innerWidth={size * 0.045}
          outerWidth={size * 0.13}
        />
      </div>
    </div>
  );
};

const ShotView: React.FC<{ shot: Shot; scene: Scene; uiStartFrame: number }> = ({
  shot,
  scene,
  uiStartFrame,
}) => {
  const frame = useCurrentFrame();
  const showUi = shot.from + frame >= uiStartFrame;

  const activeLine = shot.lines.find(
    (line) =>
      frame >= line.from - shot.from && frame < line.from - shot.from + line.durationInFrames,
  );
  const lastLine = shot.lines[shot.lines.length - 1];
  const lastLineEnd = lastLine
    ? lastLine.from - shot.from + lastLine.durationInFrames
    : 0;
  // Monologue and vote overlays own the silent tail after the final line; they
  // never interrupt dialogue.
  const tailActive = !activeLine && frame >= lastLineEnd;
  // Keep the previous speaker highlighted through the gap between lines.
  // Snapping back to full brightness for a few frames and dimming again on the
  // next line reads as a flicker.
  const lastSpoken = [...shot.lines]
    .reverse()
    .find((line) => frame >= line.from - shot.from);
  // Before the first line of a shot, hold the first speaker's highlight instead
  // of flashing back to full brightness for the lead-in frames.
  const displayLine = activeLine ?? lastSpoken ?? shot.lines[0];
  const promptSpeaker =
    lastLine?.speaker || (shot.characters[0]?.id ?? '');

  // `holdEmotion` keeps a character in the expression of the last line they
  // have spoken so far, instead of snapping back to the shot's standing face.
  const heldEmotionFor = (id: string): string | undefined => {
    for (let index = shot.lines.length - 1; index >= 0; index -= 1) {
      const line = shot.lines[index];
      if (line.speaker === id && frame >= line.from - shot.from) {
        return line.emotion;
      }
    }
    return undefined;
  };

  const speakingX = displayLine
    ? shot.characters.find((entry) => entry.id === displayLine.speaker)?.x ?? 0.5
    : 0.5;

  const { width, height } = useVideoConfig();
  const focusId = shot.focus ?? null;
  // The spotlight belongs to the inner-monologue mode. While a line is being
  // spoken the room and the rest of the cast stay at full colour.
  const focusEntry =
    tailActive && focusId
      ? shot.characters.find((entry) => entry.id === focusId)
      : undefined;
  // The spotlighted character is drawn last so they sit in front of the room.
  const ordered = focusEntry
    ? [...shot.characters.filter((entry) => entry.id !== focusId), focusEntry]
    : shot.characters;
  const captionStyle = scene.episode.style?.caption_style ?? 'ba';

  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          // Stage light, not a colour filter: keep the room readable, drop the
          // exposure a stop and let saturation fall off naturally.
          filter: focusEntry
            ? 'brightness(0.46) saturate(0.72) contrast(1.02)'
            : undefined,
        }}
      >
        <SceneBackdrop shot={shot} />
      </div>
      <AbsoluteFill>
        <AbsoluteFill
          style={{
            background: `radial-gradient(circle at ${(focusEntry?.x ?? speakingX) * 100}% 46%, rgba(255,240,214,${
              focusEntry ? 0.4 : 0.16
            }), rgba(255,240,214,0) ${focusEntry ? 48 : 52}%)`,
          }}
        />
        {ordered.map((entry) => {
          const isFocus = focusEntry?.id === entry.id;
          const dimmed = Boolean(focusEntry) && !isFocus;
          return (
            <div
              key={`${shot.id}-${entry.id}`}
              style={{
                position: 'absolute',
                inset: 0,
                opacity: 1,
                filter: dimmed
                  ? 'grayscale(0.72) brightness(0.38) saturate(0.6)'
                  : undefined,
                zIndex: isFocus ? 6 : 3,
              }}
            >
              <CharacterFigure
                entry={entry}
                data={scene.characters[entry.id]}
                activeLine={displayLine}
                heldEmotion={entry.holdEmotion ? heldEmotionFor(entry.id) : undefined}
                shadowColor="rgba(20,30,45,0.22)"
                shotDuration={shot.durationInFrames}
              />
            </div>
          );
        })}
      </AbsoluteFill>

      <WordLabels shot={shot} height={height} />

      {shot.systemVoice ? (
        <Audio src={staticFile(shot.systemVoice)} />
      ) : null}

      {shot.monologue?.audio ? (
        <Audio src={staticFile(shot.monologue.audio)} />
      ) : null}

      {tailActive && shot.monologue ? (
        <ThoughtText
          text={shot.monologue.text}
          color={scene.characters[shot.monologue.speaker]?.color || '#ffffff'}
          width={width}
          height={height}
        />
      ) : null}

      {tailActive && shot.voteTags?.length ? (
        shot.voteTags.map((tag) => {
            const entry = shot.characters.find((char) => char.id === tag.speaker);
            if (!entry) return null;
            const size = height * 0.05;
            return (
              <div
                key={`vote-${tag.speaker}`}
                style={{
                  position: 'absolute',
                  left: `${Math.min(92, Math.max(8, entry.x * 100))}%`,
                  top: height * 0.62,
                  transform: 'translateX(-50%) rotate(-2deg)',
                  zIndex: 30,
                }}
              >
                <OutlineText
                  text={tag.text}
                  fill={scene.characters[tag.speaker]?.color || '#ffffff'}
                  inner="#ffffff"
                  outer="#08111f"
                  size={size}
                  innerWidth={size * 0.05}
                  outerWidth={size * 0.14}
                />
              </div>
            );
          })
      ) : null}

      {showUi ? (
        <>
          {captionStyle === 'ba' ? <StoryChrome /> : null}

          {shot.buttons?.map((btn, index) => (
            <BAButton key={`${shot.id}-btn-${index}`} btn={btn} sfx={scene.ui?.sfx?.click} />
          ))}

          {shot.choices?.options?.length ? (
            <ChoiceBox choices={shot.choices} sfx={scene.ui?.sfx} />
          ) : null}

          {activeLine ? (
            captionStyle === 'meme' ? (
              <MemeCaption
                key={`caption-${activeLine.id}`}
                text={activeLine.text}
                color={scene.characters[activeLine.speaker]?.color || '#ffffff'}
                width={width}
                height={height}
              />
            ) : (
              <DialogueBox
                key={activeLine.id}
                speaker={activeLine.speaker}
                text={activeLine.text}
                character={scene.characters[activeLine.speaker]}
                lineFrame={frame - (activeLine.from - shot.from)}
              />
            )
          ) : shot.choices?.prompt ? (
            captionStyle === 'meme' ? (
              <MemeCaption
                key={`${shot.id}-prompt`}
                text={shot.choices.prompt}
                color={scene.characters[promptSpeaker]?.color || '#ffffff'}
                width={width}
                height={height}
              />
            ) : (
              <DialogueBox
                key={`${shot.id}-prompt`}
                speaker={promptSpeaker}
                text={shot.choices.prompt}
                character={scene.characters[promptSpeaker]}
                lineFrame={frame - (shot.choices.fromFrame ?? 0)}
                prompt
              />
            )
          ) : null}
        </>
      ) : null}
    </AbsoluteFill>
  );
};

// ── Root ────────────────────────────────────────────────────────────────────

const BAEpisode: React.FC<Scene> = (scene) => {
  const {width, height} = useVideoConfig();
  const fontFamily = scene.episode.style?.font_family || 'PingFang SC';
  const ui = scene.ui;
  const introEnd = scene.intro?.durationInFrames ?? 0;
  const bgm = scene.bgm;

  return (
    <AbsoluteFill style={{ background: '#101820', fontFamily, color: '#253844' }}>
      {bgm ? (
        <Audio
          src={staticFile(bgm.src)}
          loop={bgm.loop !== false}
          volume={(f) => {
            const base = bgm.volume ?? 0.15;
            const total = scene.episode.durationInFrames;
            const fadeIn = bgm.fadeInFrames ?? 45;
            const fadeOut = bgm.fadeOutFrames ?? 75;
            const head = fadeIn > 0 ? Math.min(1, f / fadeIn) : 1;
            const tail = fadeOut > 0 ? Math.min(1, Math.max(0, total - f) / fadeOut) : 1;
            return base * Math.max(0, Math.min(head, tail));
          }}
        />
      ) : null}

      <TransitionSeries>
        {scene.shots.flatMap((shot, index) => {
          const next = scene.shots[index + 1];
          const sequence = (
            <TransitionSeries.Sequence
              key={shot.id}
              durationInFrames={shot.durationInFrames}
              name={shot.id}
            >
              <ShotView shot={shot} scene={scene} uiStartFrame={introEnd} />
            </TransitionSeries.Sequence>
          );
          if (!next?.transition) return [sequence];
          // A shot's duration already contains the transition overlap into the
          // next shot (prepare.py adds it), so the sequences stay in sync with
          // the absolute line/audio frames.
          const transition = (
            <TransitionSeries.Transition
              key={`${shot.id}-transition`}
              presentation={transitionPresentation(next.transition, width, height)}
              timing={transitionTiming(next.transition)}
            />
          );
          return [sequence, transition];
        })}
      </TransitionSeries>

      {scene.shots.flatMap((shot) =>
        shot.lines.map((line) => (
          <React.Fragment key={line.id}>
            <Sequence
              from={line.from}
              durationInFrames={line.durationInFrames}
              name={`audio-${line.id}`}
            >
              {line.audio ? <Audio src={staticFile(line.audio)} /> : null}
            </Sequence>
            {ui?.sfx?.click && ui.lineClick !== false && line.from >= introEnd ? (
              <Sfx
                src={ui.sfx.click}
                from={line.from}
                durationInFrames={10}
                volume={ui.lineClickVolume ?? 0.14}
              />
            ) : null}
          </React.Fragment>
        )),
      )}

      {scene.intro ? <Intro intro={scene.intro} scene={scene} /> : null}
    </AbsoluteFill>
  );
};

const calculateMetadata = ({ props }: { props: Scene }) => {
  const episode = props?.episode;
  return {
    durationInFrames: Math.max(1, Number(episode?.durationInFrames) || 30),
    fps: Number(episode?.fps) || 30,
    width: Number(episode?.width) || 1280,
    height: Number(episode?.height) || 720,
  };
};

registerRoot(() => (
  <Composition
    id="BAEpisode"
    component={BAEpisode}
    defaultProps={fallbackScene}
    calculateMetadata={calculateMetadata}
    durationInFrames={30}
    fps={30}
    width={1280}
    height={720}
  />
));




