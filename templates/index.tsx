import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Composition,
  Img,
  Sequence,
  interpolate,
  registerRoot,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

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
  audio: string;
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
};

type CharacterTurn = {
  /** Direction the sprite faces after the turn. */
  to: 'left' | 'right';
  /** Frame relative to the shot where the turn starts. */
  startFrame: number;
  durationInFrames: number;
};

type Shot = {
  id: string;
  from: number;
  durationInFrames: number;
  scene?: SceneDef | null;
  background?: { type?: string; value?: string; path?: string };
  camera: string;
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
    style?: { accent?: string; font_family?: string };
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

const ImageStage: React.FC<{ scene: SceneDef; progress: number }> = ({ scene, progress }) => {
  const p = scene.palette;
  const lighting = scene.lighting || 'day';
  const drift = interpolate(progress, [0, 1], [-4, 6]);
  const zoom = 1.035 + progress * 0.015;

  return (
    <AbsoluteFill style={{ background: p.ink || '#1a2028', overflow: 'hidden' }}>
      {scene.image ? (
        <Img
          src={staticFile(scene.image)}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            transform: `scale(${zoom}) translate(${drift}px, ${-drift * 0.4}px)`,
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

const SceneBackdrop: React.FC<{ shot: Shot; progress: number }> = ({ shot, progress }) => {
  if (shot.scene?.renderer === 'image-stage') {
    return <ImageStage scene={shot.scene} progress={progress} />;
  }
  return <GradientBackground background={shot.background} />;
};

// ── Characters ──────────────────────────────────────────────────────────────

const CharacterFigure: React.FC<{
  entry: Shot['characters'][number];
  data: CharacterData;
  activeLine?: Line;
  shadowColor: string;
  shotDuration: number;
}> = ({ entry, data, activeLine, shadowColor, shotDuration }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  if (!data) return null;

  const outfit = data.outfits[entry.outfit] || data.outfits[data.default_outfit];
  if (!outfit) return null;
  const isSpeaking = activeLine?.speaker === entry.id;
  const isDimmed = Boolean(activeLine) && !isSpeaking;
  const emotion = isSpeaking ? activeLine?.emotion || entry.emotion : entry.emotion;
  const sprites = outfit.sprites || {};
  const sprite = sprites[emotion] || sprites.default;
  if (!sprite) return null;

  const entrance = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 16 });
  let tx = 0;

  // Blocking: characters can slide between marks inside a shot. The slide is a
  // pure translation; there is no walk cycle or step bob.
  const motion = entry.motion;
  let px = entry.x;
  let pBottom = entry.bottom;
  let poseScale = entry.scale;
  if (motion) {
    const start = motion.startFrame ?? 0;
    const end = Math.max(start + 1, motion.endFrame ?? shotDuration);
    const raw = interpolate(frame, [start, end], [0, 1], clamp);
    const t = motion.ease === 'linear' ? raw : raw * raw * (3 - 2 * raw);
    px = interpolate(t, [0, 1], [motion.fromX ?? entry.x, motion.toX ?? entry.x]);
    pBottom = interpolate(t, [0, 1], [motion.fromBottom ?? entry.bottom, motion.toBottom ?? entry.bottom]);
    poseScale = interpolate(t, [0, 1], [motion.fromScale ?? entry.scale, motion.toScale ?? entry.scale]);
  }

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
          bottom: `${pBottom * 100}%`,
          width: `${entry.height * 34}%`,
          height: `${entry.height * 5}%`,
          transform: 'translateX(-50%)',
          borderRadius: '50%',
          background: shadowColor,
          filter: 'blur(14px)',
        }}
      />
      <Img
        src={staticFile(sprite)}
        style={{
          position: 'absolute',
          left: `${px * 100}%`,
          bottom: `${pBottom * 100}%`,
          height: `${entry.height * 100}%`,
          width: 'auto',
          transform: `translateX(-50%) translate(${tx}px, 0px) scale(${poseScale}) scaleX(${flip})`,
          transformOrigin: 'bottom center',
          opacity: entry.entrance === 'fade-in' ? entrance : 1,
          filter: isDimmed
            ? 'brightness(0.66) saturate(0.82) drop-shadow(0 10px 22px rgba(20,30,45,0.20))'
            : 'drop-shadow(0 16px 30px rgba(20,30,45,0.22))',
        }}
      />
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

const DialogueBox: React.FC<{
  speaker: string;
  text: string;
  character?: CharacterData;
  prompt?: boolean;
}> = ({ speaker, text, character, prompt }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const appear = spring({ frame, fps, config: { damping: 200 }, durationInFrames: 10 });
  const textOpacity = interpolate(frame, [0, 6], [0, 1], clamp);
  const blink = 0.4 + 0.6 * Math.abs(Math.sin(frame / 10));

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
        {text}
      </div>

      {/* 右下闪烁的青色三角 */}
      {prompt ? null : (
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
          <SceneBackdrop shot={firstShot} progress={0.1} />
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
  const promptSpeaker =
    lastLine?.speaker || (shot.characters[0]?.id ?? '');

  const progress = interpolate(frame, [0, Math.max(1, shot.durationInFrames)], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const cameraScale =
    shot.camera === 'push-in'
      ? 1 + progress * 0.06
      : shot.camera === 'pull-back'
        ? 1.07 - progress * 0.06
        : shot.camera === 'punch-in'
          ? 1 + Math.min(progress * 1.6, 1) * 0.035
          : 1;

  const speakingX = activeLine
    ? shot.characters.find((entry) => entry.id === activeLine.speaker)?.x ?? 0.5
    : 0.5;

  return (
    <AbsoluteFill style={{ overflow: 'hidden' }}>
      <AbsoluteFill style={{ transform: `scale(${cameraScale})`, transformOrigin: '50% 62%' }}>
        <SceneBackdrop shot={shot} progress={progress} />
        <AbsoluteFill
          style={{
            background: `radial-gradient(circle at ${speakingX * 100}% 46%, rgba(255,255,255,0.16), rgba(255,255,255,0) 52%)`,
          }}
        />
        {shot.characters.map((entry) => (
          <CharacterFigure
            key={`${shot.id}-${entry.id}`}
            entry={entry}
            data={scene.characters[entry.id]}
            activeLine={activeLine}
            shadowColor="rgba(20,30,45,0.22)"
            shotDuration={shot.durationInFrames}
          />
        ))}
      </AbsoluteFill>

      {showUi ? (
        <>
          <StoryChrome />

          {shot.buttons?.map((btn, index) => (
            <BAButton key={`${shot.id}-btn-${index}`} btn={btn} sfx={scene.ui?.sfx?.click} />
          ))}

          {shot.choices?.options?.length ? (
            <ChoiceBox choices={shot.choices} sfx={scene.ui?.sfx} />
          ) : null}

          {activeLine ? (
            <DialogueBox
              key={activeLine.id}
              speaker={activeLine.speaker}
              text={activeLine.text}
              character={scene.characters[activeLine.speaker]}
            />
          ) : shot.choices?.prompt ? (
            <DialogueBox
              key={`${shot.id}-prompt`}
              speaker={promptSpeaker}
              text={shot.choices.prompt}
              character={scene.characters[promptSpeaker]}
              prompt
            />
          ) : null}
        </>
      ) : null}
    </AbsoluteFill>
  );
};

// ── Root ────────────────────────────────────────────────────────────────────

const BAEpisode: React.FC<Scene> = (scene) => {
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

      {scene.shots.map((shot) => (
        <Sequence
          key={shot.id}
          from={shot.from}
          durationInFrames={shot.durationInFrames}
          name={shot.id}
        >
          <ShotView
            shot={shot}
            scene={scene}
            uiStartFrame={scene.intro?.durationInFrames ?? 0}
          />
        </Sequence>
      ))}

      {scene.shots.flatMap((shot) =>
        shot.lines.map((line) => (
          <React.Fragment key={line.id}>
            <Sequence
              from={line.from}
              durationInFrames={line.durationInFrames}
              name={`audio-${line.id}`}
            >
              <Audio src={staticFile(line.audio)} />
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
