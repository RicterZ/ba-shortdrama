# 架构与边界

## 目录

```text
ba-shortdrama/
├── code/carocut/          上游 bilibili/carocut（git submodule，版本由主仓库固定）
├── code/ba-production/    自有生产链（模板、schema、脚本）
├── data/characters/       角色 profile（人设、语音绑定、服装与立绘）；<id>/kivo/ 存 kivo 原始资料与差分/spine，<id>/sprites/ 存全身表情立绘与 manifest
├── data/scenes/           场景 profile + 背景图（<id>/scene.yaml、<id>/backgrounds/）
├── data/backgrounds/      背景库索引 manifest.json（来源、尺寸、裁切、哈希）
├── data/audio/            BGM / 音效库与 manifest.json（来源、用途、哈希）
├── videos/<id>/           每集独立数据
│   ├── episode.yaml       画幅、fps、角色、字幕与时间参数、intro
│   ├── script.json        台词（speaker / emotion / text）
│   ├── storyboard.json    镜头（场景、运镜、角色站位与服装、台词引用）
│   ├── audio/             逐句音频 + timing.json
│   ├── raws/              本集实际使用的素材快照（渲染 public-dir）
│   ├── project/scene.json 生成的渲染输入
│   ├── preview/           预览帧
│   ├── output/            成片
│   ├── assets.lock.json   素材路径与 SHA-256
│   └── review.json        审核记录
├── local/                 本机私有配置、缓存、日志（不进版本库；含 .env）
└── *.md                   项目说明
```

## 数据流

```text
kivo.wiki（角色资料 / spine / 差分 / BGM / 音效）
        │
        └─ fetch_kivo.py（npm run res:kivo）──> data/characters/*/kivo/ + data/audio/* + manifest.json

bluearchive.wiki（全部服装 × 全部表情全身立绘）
        │
        └─ fetch_sprites.py（npm run res:sprites）──> data/characters/*/sprites/<outfit>/ + manifest.json + profile.yaml

episode.yaml + script.json + storyboard.json
      + data/characters/*/profile.yaml + data/scenes/*/scene.yaml
        │
        ├─ prepare.py ──> voice.py（Vocu / Fish Audio / Edge TTS）──> raws/audio/
        │             ──> episode.yaml 的 bgm        ──> raws/audio/ + scene.bgm
        │             ──> 按服装取立绘快照          ──> raws/images/
        │             ──> timing.json / scene.json / assets.lock.json
        │
        ├─ validate.py ──> 错误列表（schema、字幕、时间轴、哈希、成片）
        │
        └─ render.py ──> Remotion（--props scene.json --public-dir raws）
                      ├─ --profile preview（ep:preview）──> <id>-preview.mp4，人工审片
                      ├─ --profile final（ep:final）    ──> <id>.mp4
                      └─ --mode still（ep:still）       ──> preview/frame-NNNN.png
```

BGM 由 `episode.yaml` 的 `bgm` 块经 prepare 进入 scene.json；kivo 的 spine 仍只是入库素材，没有 Live2D 渲染器。剧情 UI 音效走单独的 `data/ui/sfx/`（见 `docs/UI.md`），不依赖 kivo 的 `data/audio/sfx/`。全身表情立绘走 bluearchive.wiki，由 `fetch_sprites.py` 写入 `profile.yaml` 的 `outfits`，prepare 按现有服装/表情路径直接取用。

## Remotion 模板

- `templates/index.tsx` 只有一个 composition：`BAEpisode`。
- 通过 `calculateMetadata` 从 `episode` props 读取 `durationInFrames` / `fps` / `width` / `height`。
- 渲染命令用 `--props <该集>/project/scene.json` 和 `--public-dir <该集>/raws`，因此模板完全不知道剧集目录，新增剧集不改代码。
- 每个镜头是一个 `TransitionSeries.Sequence`；场景、角色、字幕、运镜都从 scene 数据生成。
- 切点可以用官方 `@remotion/transitions` 的 `fade` / `slide` / `wipe` / `flip` / `clock-wipe` / `iris`。`episode.yaml` 的 `transitions` 决定默认策略（默认只在场景变化时加 12 帧 fade），单个镜头可在分镜里覆盖；镜头 `durationInFrames` 已包含与下一个镜头的重叠帧，prepare 同时在切点补等长静音，所以台词绝对帧与画面始终对齐。
- `image-stage` 场景读取 `data/scenes/<id>/backgrounds/` 下的背景图，按变体叠加冷光/暖光、暗角和轻微推拉；模板不自行绘制房间。缺图时用场景 profile 的中性底色占位并警告。
- 对白按游戏内实机样式：底部渐变压暗，白字姓名 + 青色社团名 + 细分割线 + 白字台词 + 右下闪烁青色三角，`intro` 是可选的 BA 风格标题卡（全宽浅蓝切面带、`Episode N` + 黄色下划线 + 深蓝大标题），删掉 `episode.yaml` 的 `intro` 就不会出现。
- 分镜可选的 `choices` 会渲染成浅蓝切面平行四边形选择条（深蓝居中文字），出现/确认/消失由 `fromFrame` / `selectFrame` / `hideFrame` 控制；`buttons` 渲染斜切按钮并支持 `pressFrame` 点击。
- 点击音与点击特效：对白推进、选项出现/确认、按钮按下播放 `ui.sfx` 里的 BA 音效；按钮和选项确认同时触发扩散虚线圆环 + 菱形火花。音效来源与许可见 `data/ui/manifest.json`，token 见 `docs/UI.md`。
- 画面不压水印；合成语音/非官方同人说明放在 `review.json` 和视频简介里。
- 角色按 `outfit` 取对应立绘；说话人高亮、其他人压暗；没有对应表情图时用该服装的 `default` 立绘，不做程序化微动。
- 音轨按台词各自 `Sequence` 挂载，帧号来自实测音频时长，不手写。

## scene.json

由 `prepare.py` 生成，不手工编辑。主要内容：

```json
{
  "episode": { "id": "...", "width": 1280, "height": 720, "fps": 30, "durationInFrames": 845 },
  "characters": {
    "saiba-momoi": {
      "name": "才羽桃",
      "color": "#c44b82",
      "club": "游戏开发部",
      "school": "千年科学学园",
      "default_outfit": "default",
      "voice": { "provider": "fish-audio", "model": "s2.1-pro-free", "voice_id": "..." },
      "outfits": {
        "default": {
          "name": "标准制服",
          "sprites": { "default": "images/...", "excited": "images/..." },
          "fallbacks": ["excited"]
        }
      }
    }
  },
  "intro": { "durationInFrames": 66, "kicker": "...", "title": "...", "subtitle": "..." },
  "ui": {
    "kit": "blue-archive",
    "sfx": { "click": "audio/ui/click.wav", "select": "audio/ui/select.wav", "hover": "audio/ui/hover.wav" },
    "lineClick": true,
    "lineClickVolume": 0.14
  },
  "shots": [
    {
      "id": "S1",
      "from": 0,
      "durationInFrames": 323,
      "transition": null,
      "scene": { "id": "game-dev-room", "renderer": "image-stage", "variant": "afternoon", "lighting": "day", "image": "images/scene-...jpg", "palette": {} },
      "characters": [],
      "lines": [],
      "buttons": [],
      "choices": null
    }
  ]
}
```

`fallbacks` 记录哪些表情回退到了 default 立绘。

## 硬边界

- 台词串行，不支持重叠对白；多角色同框是支持的。
- 立绘是静态图，没有 Live2D、口型、骨骼动画。
- 场景渲染器目前只有 `image-stage`；新场景要先有背景图，再在模板里扩展 renderer，不能用代码现画房间。
- 一个剧集一份 Remotion 工程描述，不生成独立 React 代码。
- CaroCut 上游仍可通过 `code/carocut/workspaces -> ../videos` 看到这些目录，但主链不依赖它的五 Agent 调度；其 UI 需要另外配置模型。
- 发布环节没有自动化。
