# 制作工作流

## 0. 素材准备（可选，前期一次）

新角色、新 BGM、新界面音效从 kivo.wiki 取，细节和 API 契约见 `RESOURCES.md`。

```sh
cd code/ba-production

# 角色：信息 + 头像 + 表情差分 + Live2D；--portrait 额外取 SchaleDB 平面立绘
npm run res:kivo -- student 2 --portrait --spine

# 全身表情立绘：全部服装 × 全部表情，自动写入 profile.yaml
npm run res:sprites -- list Momoi
npm run res:sprites -- get Momoi
npm run res:sprites -- get Momoi --contact   # 需要核对表情时生成缩略图总览
npm run test:sprites                         # 立绘抓取回归：默认表情、缺图失败、不覆盖索引

# BGM / 音效：先查，再取；也可以直接取起步合集
npm run res:kivo -- music list --match School
npm run res:kivo -- music preset
npm run res:kivo -- sfx list --match UI_Button
npm run res:kivo -- sfx preset

# 核对索引与文件哈希
npm run res:check
```

产物：`data/characters/<slug>/kivo/`（信息、头像、差分、spine）、`data/characters/<slug>/sprites/<outfit>/`（全身表情立绘 + manifest）、`data/audio/bgm/`、`data/audio/sfx/`、`data/audio/manifest.json`。`fetch_sprites.py` 会更新 `profile.yaml` 的 `outfits`（不动 persona / voice）；`fetch_kivo.py` 不改 profile，新角色仍需按 `kivo/summary.json` 补人设并确认音色。

## 1. 建一集

```sh
cd code/ba-production
npm run ep:new -- 003-summer-patch --title "夏日补丁" --characters saiba-momoi
```

`episode.yaml` 的 `template` 选择渲染模板，默认 `blue-archive`；新建集数可用 `--template blue-archive` 指定。`width` / `height` / `fps` 是画幅与帧率配置，例如竖屏可用 `--width 720 --height 1280`。目前只有 `blue-archive` 模板，模板决定视觉呈现，画幅尺寸由集数配置决定。新建的剧集默认带 `transitions` 块（场景切换加 12 帧 fade），规则见下面「转场」。

生成 `videos/003-summer-patch/` 骨架和空白的 `script.json`、`storyboard.json`。填完后才能准备。

## 2. 写台词 `script.json`

```json
[
  { "id": "L1", "speaker": "saiba-momoi", "emotion": "excited", "text": "老师！我把新作打通关了！" },
  { "id": "L2", "speaker": "saiba-momoi", "emotion": "confident", "text": "而且顺手，把最终 BOSS 卡进墙里了。" }
]
```

- `id` 可省略，默认 `L1`、`L2`……
- `speaker` 必须是 `episode.yaml` 的 `characters` 之一。
- `voice_text`（可选）：真正送去语音合成的台词；省略时用 `text`。外语配音、中文字幕时把两者分开写（`text` 显示在屏幕上，`voice_text` 只用来配音），字幕长度校验只看 `text`。
- `emotion` 只是演出意图；有对应表情立绘时换图，没有时回退到该套装的 `default` 立绘并打印警告。静止时不做呼吸、说话抖动等程序化微动；需要动作时在分镜里写 `motion`。
- 单句字幕上限 26 字/行、2 行，校验脚本会拒绝超长台词。
- 一句一个说话人，目前不支持两人同时说话。

## 3. 写分镜 `storyboard.json`

```json
{
  "shots": [
    {
      "id": "S1",
      "scene": { "id": "game-dev-room", "variant": "afternoon" },
      "camera": "push-in",
      "characters": [
        { "id": "saiba-momoi", "outfit": "default", "x": 0.66, "entrance": "slide-in-right", "emotion": "default" }
      ],
      "lines": ["L1", "L2"]
    }
  ]
}
```

- 台词必须在镜头中按顺序各出现一次，不能漏、不能重复。
- `scene` 引用 `data/scenes/<id>/scene.yaml`，可写成字符串（用默认变体）或 `{id, variant}`。变体决定光线和墙面色，例如 `afternoon` / `monitor-glow` / `lamp`；切镜时自动换光。
- `outfit` 选角色 profile 里的服装；省略时用 `default_outfit`。同一角色可以在不同镜头穿不同衣服。
- `x` 是角色中心横坐标（0–1）；`bottom` 是底部偏移比例（默认 -0.25）；`height` 是画面高度占比（默认 1.08）；`scale` 是额外缩放。需要不同构图时在分镜里写 `height` / `bottom` 覆盖。
- `entrance`：`none` / `fade-in` / `slide-in-left` / `slide-in-right`；滑入是纯平移，没有步伐起伏。
- `motion`（可选）：镜头内的走位。`fromX` / `toX` 与 `fromBottom` / `toBottom` 是起点和终点的位置比例，`fromScale` / `toScale` 是缩放，`startFrame` / `endFrame` 相对镜头起点（省略时从 0 到镜头结束），`ease` 取 `linear` / `ease-in-out`。省略的起止值取角色当前的 `x` / `bottom` / `scale`。走位只做平移，不模拟走路；走完停在终点，后续镜头沿用同一个 `x` / `bottom`，不要每镜重新漂移。
- `motion.hops`（可选）：把这段位移拆成几次跳跃，每次向前一截并起落一次，用来演被吓退、边退边跳；`hopLift` 是每次起跳的高度（相对画面高度，默认 0.05）。`ease` 对跳跃不起作用，落点仍然是 `toX` / `toBottom`，下一镜照样从落点接上。这是走位，人会从起点挪到终点。原地跳不要用它，用下面的 `actions`：`jump` 是吃惊单跳，`hophop` 是兴奋连跳两次，都不改 `x` / `bottom`。两套可以同时出现，互不替换：`hops` 管位置，`actions` 管姿态。
- `facing`（可选）：`left` / `right`，默认 `right`（原图方向）；`left` 把立绘水平镜像。
- `turns`（可选）：转身动画。`to` 是转向后的朝向，`atLine` 写该镜头内的一句台词 id（在该句开始时转身），或写 `startFrame`（相对镜头起点）；`durationInFrames` 默认 6。转身用水平镜像过渡表现，例如 Momoi 从看 Midori 转去看 Kei：
  ```json
  { "id": "saiba-momoi", "facing": "left", "turns": [{ "to": "right", "atLine": "L18", "durationInFrames": 10 }] }
  ```
- `camera`：`static` / `punch-in` / `push-in` / `pull-back`。
- `holdEmotion`（可选，默认 `false`）：角色在别人说话时保持自己上一句的表情，不回到 `emotion` 的常驻脸；下一镜重置。适合惊吓、生气这类要延续到对方台词结束的反应，例如 Momoi 被吓到后一直保持 `surprised`，等 Kei 说完才恢复。
- `emotionCues`（可选）：不等角色开口就能换表情，写 `[{ "emotion": "surprised", "startFrame": 660 }]`（帧相对镜头起点，prepare 会自动加转场帧）。同一时刻有多条时取最后一条；角色正在说话时仍用该句台词的表情。用来在对方台词还没说完时先给出反应表情。
- 仍然可以用 `background` 兜底：CSS 渐变字符串，或 `{"type":"image","path":"images/xxx.webp"}`（路径相对 `raws/`）。有 `scene` 时优先用场景渲染器。
- 每个镜头可放多个角色；当前说话人高亮，其他人自动压暗。说话人也可以不在画面里（画外音）。
- 可选 `choices` 显示浅蓝切面选择条，例如：
  ```json
  {
    "prompt": "现在要怎么做？",
    "options": ["把这段录下来", "再打一次最终 BOSS"],
    "selected": 0,
    "fromFrame": 300,
    "selectFrame": 340,
    "hideFrame": 372
  }
  ```
  `fromFrame` / `selectFrame` / `hideFrame` 都相对本镜头起点；`prompt` 在台词结束后显示在对白框里。省略时间字段时分别默认 `0` / `+30` / `+52`。
- 可选 `buttons` 显示斜切按钮，`pressFrame`（相对镜头）触发按下动画、点击音和点击特效：
  ```json
  "buttons": [
    { "label": "SAVE CLIP", "x": 0.36, "y": 0.68, "width": 0.24, "pressFrame": 130, "variant": "primary" }
  ]
  ```
- `episode.yaml` 的 `ui` 块可以覆盖 UI 音效（`click` / `select` / `hover` 对应 `data/ui/sfx/<name>.wav`）、关闭逐句点击音（`lineClick: false`）或调整音量（`lineClickVolume`）。不写时使用默认三件套。
- 台词按镜头顺序连续排布；切镜点由 `timing` 参数自动决定，不需要手写帧号。

### 转场

转场由官方 `@remotion/transitions` 渲染，帧号和 padding 全部由 prepare 计算，分镜只需要声明效果。

`episode.yaml` 的 `transitions` 块决定默认行为，新建剧集默认写入：

```json
"transitions": { "on": "scene-change", "type": "fade", "durationInFrames": 12 }
```

- `on`：`scene-change`（默认，只在 `scene` 的 id 或 variant 变化时加）/ `every-cut`（每个切点都加）/ `none`（不加，回到硬切）。
- `type`：`fade` / `slide` / `wipe` / `flip` / `clock-wipe` / `iris` / `none`。`none` 等于不加转场。
- `durationInFrames`：默认 12；必须短于前后两个镜头，否则 prepare 报错。
- `direction`（可选）：`slide` 用 `from-left` / `from-top` / `from-right` / `from-bottom`；`wipe` 另有四个斜角方向（`from-top-left` 等）；`flip` 用 `from-left` / `from-right` / `from-top` / `from-bottom`。
- `easing`：`linear`（默认）/ `ease-in-out`；`perspective` 只用于 `flip`，`shouldFadeOutExitingScene` 只用于 `fade`。

单个镜头可以在 `storyboard.json` 里覆盖，写在**后一个**镜头上（表示进入该镜头的转场）：

```json
{ "id": "S2", "transition": { "type": "wipe", "durationInFrames": 10, "direction": "from-top-left" }, "scene": "..." }
```

不需要转场时写 `"transition": "none"`。第一个镜头不能声明转场（片头之前没有内容可叠）。省略 `durationInFrames` 时沿用 `episode.yaml` 的值。

**帧号不用手算，也不会偏移。** prepare 在每个切点插入与转场等长的静音 padding，台词和音频整体后移；`TransitionSeries` 的重叠再把这段时间抵消，所以总时长只增加 Σ转场帧数，画面与音频保持对齐。分镜里的 `choices.fromFrame` / `selectFrame` / `hideFrame`、`buttons.pressFrame`、角色的 `motion.startFrame` / `endFrame`、`turns.startFrame` 都相对镜头内容起点，prepare 会自动加上转场帧；`turns.atLine` 也不用改。想调节奏只改 `durationInFrames`，不要手写帧号。

已完成的旧集数没有 `transitions` 块，行为不变（全部硬切）。要给旧集数补转场，只在 `episode.yaml` 里加这个块并重新 prepare（`--reuse-audio` 即可），不需要改分镜。

### 场景 profile

```json
{
  "schema_version": 1,
  "id": "game-dev-room",
  "name": "游戏开发部活动室",
  "renderer": "image-stage",
  "default_variant": "afternoon",
  "image": "backgrounds/game-dev-room-default.jpg",
  "palette": { "wallTop": "#f7eadc", "wallBottom": "#e6c9b5", "floor": "#c59b7b", "accent": "#e78caf", "ink": "#241a16" },
  "variants": {
    "afternoon": { "lighting": "day", "tint": "#fff4e2" },
    "monitor-glow": { "lighting": "monitor", "tint": "#8fb8d8", "ink": "#0d1420", "image": "backgrounds/game-dev-room-night.jpg" },
    "lamp": { "lighting": "lamp", "tint": "#ffd2a1", "ink": "#2b1f1b" }
  }
}
```

`image` 是相对 `data/scenes/<id>/` 的背景图；某个变体可以写自己的 `image` 覆盖它。`palette` 是基础色，`variants` 里的同名键覆盖它，`lighting` 决定模板叠加的冷光、暖光或自然光。**背景图由工作区所有者提供，模板不自行绘制房间**；缺图时 prepare 会警告并用中性底色占位。`renderer` 必须和 `templates/index.tsx` 里实现的渲染器一致，目前只有 `image-stage`。

### 开头标题卡

开头的 Episode 展示页由 `episode.yaml` 的 `intro` 控制，不需要改模板代码。

- 要标题卡：写上 `intro`。`kicker` 是小标签（实机写作 `Episode 1`，带黄色下划线），`title` 是浅蓝切面带上的深蓝大标题，`subtitle` 可选。`durationInFrames` 是卡片长度；省略时用 `timing.intro_frames`（默认 60）。卡片结束后再空 `timing.lead_in_frames`，第一句台词才开始。
- 不要标题卡：删掉整个 `intro`。模板不会画这页，prepare 也不再预留 `timing.intro_frames`，视频从第一个镜头开始，第一句只空 `lead_in_frames`。`timing.intro_frames` 本身不会单独打开标题卡。
- 改过 `intro` 之后要重新 prepare，时间轴才会跟着变。已经准备好的旧集数保持原样，直到下次 prepare。

`style.watermark` 不渲染。设计 token 见 `docs/UI.md`。

### 台词打字效果

对白区按实机的固定速度逐字显示：15 字 / 1 秒（15 字/秒；30fps 下每 2 帧一个字），台词开始 2 帧后起字。打完之前右下角的青色三角不出现，打完后才闪烁提示继续。`choices.prompt` 同样逐字显示。速度是模板常量 `TYPEWRITER_CHARS_PER_SECOND`，不按句子长短自适应，所以台词的 `durationInFrames` 要够长——validate 只校验字幕长度，不校验打字是否能在句内打完。

### 背景音乐

`episode.yaml` 可以加 `bgm` 块：

```json
"bgm": { "file": "data/audio/bgm/0003-mischievous-step.ogg", "volume": 0.16, "loop": true, "fadeInFrames": 60, "fadeOutFrames": 90 }
```

`file` 相对工作区根目录；prepare 会把它复制到 `raws/audio/` 并写入 `scene.bgm`，Remotion 在整片期间循环播放，按 `fadeInFrames` / `fadeOutFrames` 淡入淡出，音量为 `volume`。不写 `bgm` 就没有背景音乐。

## 4. 准备

语音有单独的入口 `scripts/voice.py`（`npm run voice -- ...`），`prepare.py` 内部也调用它，不需要再写临时脚本：

```sh
cd code/ba-production

# 检查配置、key 和音色是否存在（轻量查询，不合成；--config-only 只查配置，--synthesize 才试音）
npm run voice -- check

# 单角色试音，默认写到 local/work/voice-samples/
npm run voice -- sample --character saiba-momoi --text "老师，早上好。"

# 单气泡或单动作预览，不经过某一集。默认出一段短视频到 local/work/fx-preview/
# 气泡要这套衣服已经写了 spine。--still 只出中间一帧。
# --scene 换成真实房间；--episode 和 --shot 再沿用那一镜的站位。
npm run fx -- preview Heart --character saiba-momoi
npm run fx -- preview Heart --character saiba-momoi --episode 003-game-dev-sneak --shot S2 --still
npm run fx -- preview hophop --character saiba-momoi --scene game-dev-room --still

# 为一集生成全部语音（--only L7,L12 只补指定台词；--reuse 跳过已有文件）
npm run voice -- episode --episode 003-game-dev-sneak --only L7 --timeout 180

# 主 provider 失败时使用 profile 里的 fallback
npm run voice -- episode --episode 003-game-dev-sneak --fallback
```

`voice.py` 负责 provider、重试、首尾静音裁剪和错误码输出；`episode` 只写 `audio/NNN.mp3`，时间轴仍由 prepare 重建。Vocu 整集默认走异步多句接口（`--sync` 可强制逐句同步），`check` 默认只做音色查询、不触发合成。三个 provider 都从各自 profile 的 `voice` 读取，`vocu` 的主机是 `https://v1.wusound.cn`。

```sh
EPISODE=003-summer-patch npm run ep:prepare
```

会做四件事：

1. 用 `voice.py` 的同一套 provider 合成 `audio/NNN.mp3`（支持 Vocu / Fish Audio / Edge TTS，可按角色混用；加 `--voice-fallback` 使用该 profile 的备用 provider），复制到 `raws/audio/`。
2. 裁掉每句首尾静音，再用 ffprobe 实测时长，按 `ceil(时长×fps) + 14 帧` 计算时间轴。
3. 把本集用到的立绘按服装复制到 `raws/images/`，缺失表情回退到 default 并打印警告；场景背景图也复制进快照，缺图时警告。
4. 生成 `project/scene.json`（渲染输入）、`audio/timing.json`（可读时间轴）、`assets.lock.json`（素材哈希）。
5. 按 `episode.yaml` 的 `transitions` 在每个切点插入转场 padding，算出各镜头的 `durationInFrames`；台词、音频和镜头内相对帧一起后移，保证不重叠。

## 5. 校验

```sh
npm run ep:validate
```

检查：schema、角色与音色、台词覆盖与顺序、字幕长度、音频存在与时长达标、时间轴不重叠、转场定义与镜头连续性、scene 与 timing 一致、素材哈希、成片容器与时长。

## 6. 渲染

采用两阶段渲染：先出快速预览审片，通过后再出高质量成片。

```sh
# 快速预览：半尺寸、每 3 帧采样一次（720p/30fps 源输出 640×360/10fps），ultrafast 编码
EPISODE=003-summer-patch npm run ep:preview

# 审片通过后：2x 输出尺寸、高质量编码，输出 output/<episode-id>.mp4
EPISODE=003-summer-patch npm run ep:final
```

视频只有 `ep:preview` 和 `ep:final` 两个入口，`render.py` 渲染视频时必须指定 `--profile`。耗时基准（M1 Ultra，003-game-dev-sneak，6744 帧 / 3 分 45 秒）：整集 preview 约 133 秒。

只想看某一段时，不要按段渲染，先出整集 preview，再用 ffmpeg 从中切出片段（秒级，画面和声音与整集一致）：

```sh
ffmpeg -ss 120 -to 150 -i videos/<episode-id>/output/<episode-id>-preview.mp4 -c copy clip.mp4
```

两个阶段共用同一份 `project/scene.json` 和时间轴，预览阶段不要改素材或重新生成语音。`preview/frame-NNNN.png` 用来抽查单帧。默认 1280×720@30；改 `episode.yaml` 的 `width` / `height` / `fps` 后重新准备即可换画幅。

执行约束：先 validate，再 preview；人工确认后才运行 final。画面修改复用未变更的音频，重新 prepare 和 validate 后重出 preview。静帧单独使用 ep:still，不让视频命令默认附带静帧。

preview 参数：scale=0.5、every-nth-frame=3、JPEG 70、CRF 28、ultrafast、默认并发 4，直接低规格渲染而不是先出高清再压缩。Remotion 按源时间轴采样并降低输出帧率，保留音频和播放时长（末尾允许一个采样间隔的舍入误差）。预览不修改 scene.json、语音或素材；细微动画和快速表情切换需在 final 复核。`render.py` 默认 `--mode video`，并输出 Remotion 调用总耗时。

final 只放大画幅，不做 60fps 转换；不要通过改 fps 数字来变更帧率，那会改变片长。

排查慢渲染时保留完整进度和退出码，记录实际 profile、输出规格和总耗时。

## 7. 审片与发布

- 先看预览帧，再完整看片。`review.json` 记录看过的帧、是否完整听音、缺失项。
- `publication_approved` 默认 `false`，不要在没有人工确认的情况下改成 `true`。
- 投稿是人工操作，没有自动发布。
- 公开发布前必须确认素材权利，见 `ASSETS.md`。

## 8. 迭代原则

- 改台词 → 重新 prepare（会重新合成语音）→ validate → preview → 审片 → final。
- 只改画面/站位/镜头 → `prepare --reuse-audio` → validate → preview，避免重复合成。
- 新角色：先 `npm run res:kivo -- student <kivo id> --portrait --spine` 拉信息与素材，再 `npm run res:sprites -- get <英文名>` 拉全部服装的全部表情立绘；然后在 `data/characters/<id>/` 建 `profile.yaml`（人设参考 `kivo/summary.json`、`voice` provider/音色、`outfits` 立绘表），由 `profile.json` schema 校验；最后到 `episode.yaml` 的 `characters` 里引用。多套衣服就在 `outfits` 下加条目，分镜用 `outfit` 选择，`emotion` 可用原始索引或已登记的语义别名。
- 新场景：先从 `data/backgrounds/manifest.json` 选图（或运行 `npm run bg:build` 重建），再在 `data/scenes/<id>/scene.yaml` 建配置，`image` 写相对场景目录的 `backgrounds/<id>-<variant>.jpg`；由 `scene.json` schema 校验，`npm run bg:check` 会核对图片存在、哈希、命名和重复登记。分镜用 `scene` 引用。没有对应 renderer 时先在模板里实现，不要用代码现画房间。

### 角色内置动作（首批已接入）

分镜角色可用 `actions`，时间为镜头内容起点后的帧数；prepare 自动补偿转场。
动作、`emotionCues` 换脸与 `motion` 站位移动互相独立。吓退用 `motion.hops`；站在原地高兴地跳用 `hophop`。不要用两套去演同一次跳。

```json
{"id":"saiba-momoi","actions":[{"name":"hophop","startFrame":12},{"name":"falldownR","startFrame":90}]}
```

| 预设 | LLM 选择场景 | 持续时间 |
|---|---|---|
| `jump` / `hophop` | 吃惊单跳 / 兴奋连跳两次 | 0.25 / 0.5 秒 |
| `greeting` | 招呼、点头（轻微下沉后恢复） | 0.4 秒 |
| `shake` / `stiff` | 摇晃 / 小幅快速震动 | 0.24 / 0.4 秒 |
| `closeup` | 强调角色，放大到原来的 1.5 倍 | 保持至下一动作 |
| `falldownL` / `falldownR` | 左右摇摆后晕倒下落 | 约 1.87 秒后隐藏 |
| `hide` | 立即隐藏角色及投影 | 保持至下一动作 |

同一角色同时只取开始时间最新的动作；下一动作替换前一个（包括恢复隐藏状态和取消拉近），不是队列，也不叠加多个预设。晕倒结束前留足镜头时长；方向是画面方向，不随角色朝向镜像。
这些曲线参考社区播放器，并非官方逐帧认证。来源及许可见 `THIRD_PARTY_NOTICES.md`。

### 气泡与配套音效

先运行 `uv run python code/ba-production/scripts/fetch_bubbles.py` 获取固定版本图片及对应音效，不覆盖已有资源。图片从 ba-archive 的固定提交拉取，清单在 `data/effects/ba/`；音效走 kivo 的 Cloudreve 分享，登记在 `data/audio/manifest.json`。分享失败时图片已经保存，报错只针对音效。代码来源和许可见 `THIRD_PARTY_NOTICES.md`，游戏素材的权利不因项目开源而转移。

`npm run res:kivo -- student <id> --spine` 下载结束后，会用每套服装的默认立绘和每个 skel 比宽高比并打印接近或不符。差在 2% 以内只说明尺寸接近，脚本不会写入 `outfits.spine`；确认是同一套未裁切站立导出后再手写。之后 `fetch_sprites` 刷新服装时会保留已经写好的 `spine`。

在 storyboard 的角色条目中加入 `bubbles`，与 `emotion`（换脸）及 `actions`（立绘动作）分别控制。例如：

```json
{
  "bubbles": [
    {"name": "Think", "startFrame": 15},
    {"name": "Heart", "atLine": "L3", "offsetFrames": 6},
    {"name": "Heart", "afterLine": "L3", "offsetFrames": 6},
    {"name": "Shy", "startFrame": 75, "sound": false}
  ]
}
```

`name` 必须是下表大小写一致的预设名。时间用 `startFrame`、`atLine`、`afterLine` 三选一。`startFrame` 是镜头内容起点后的非负整数帧，prepare 自动补偿转场，不要重复加转场时长。`atLine` 写本镜头里的一句台词 id，对齐这句的内容起点；`afterLine` 对齐这句的结束。`offsetFrames` 是相对这个锚点的帧数，可以为负。台词结束后 6 帧出现，写 `afterLine` 加 `"offsetFrames": 6`，不用查这句有多少帧，也不用自己减 `shot.from`。`sound` 为布尔值，省略时默认 `true`，`false` 只关闭该气泡音效。音频播放自身长度（镜头结束仍会截断，应留足镜头时间）。不要填写 `x/y/scale/duration`；位置、大小和时长仍由预设决定，不能按镜头改。

| 气泡预设 | LLM 选择场景 |
|---|---|
| `Think` | 思考：独立的思考云气泡，不是省略号气泡 |
| `Shy` | 害羞斜线；与脸红换脸差分分别控制 |
| `Angry` / `Upset` | 生气十字 / 不满的线团气泡 |
| `Chat` / `Dot` | 交谈 / 三个依次出现的省略点 |
| `Exclaim` / `Question` / `Surprise` | 感叹号 / 问号 / 惊讶符号组合 |
| `Heart` / `Music` | 爱心气泡 / 音符 |
| `Respond` / `Twinkle` / `Bulb` | 回应线 / 闪光星 / 灵光灯泡 |
| `Sweat` / `Sad` / `Tear` | 汗滴 / 低落竖线 / 泪水 |
| `Steam` / `Sigh` / `Zzz` | 冒气 / 叹气 / 睡觉 |

气泡约 0.5–2.35 秒（`Zzz` 三阶段依次显示约 2.35 秒），具体时长见 `code/ba-production/templates/bubble-presets.json`。同一角色后触发气泡替换前一个视觉效果，音效可重叠。气泡作为人物容器的子元素，继承站位、跳跃、进场位移、缩放、旋转、转向及隐藏。不得用 Dot、emoji 或换脸代替 Think/Shy。

#### 实现备注

19 种曲线依据社区播放器转换为分层按帧演出，属于近似复现，不宣称官方逐帧一致。`Think` 上游缺处理函数，采用真实 `Emoticon_Balloon_T` 图和专用音效，入场/停留曲线为本项目自实现；仍需人工比对官方节奏。

气泡位置／大小使用固定参考坐标，而非按画面高度随意放置：参考半宽 540、半高 1012；
每种预设的 `offset` / `width` 从上游 `emotionOptions.ts` 读取。
气泡的参考位置为 `((offset.x-0.8)*540, (offset.y-1.2)*1012)`，
通常参考图宽为 `width*540`。`Dot`、`Steam`、`Tear`、`Zzz` 的上游处理函数没有调用缩放函数：未校准时 `Dot` 使用原生 255×198 气泡及 39×39 圆点；`Steam` 使用 191×147，支点 `(1.4, 1.5)`，两团气分别以绝对缩放 0.1→0.7、0.6→0.9 放大；`Tear` 以大泪 68×87 为坐标，小泪宽 52，位置分别为 `(0, 30)` 与 `(0, 0)`，右上支点，缩放 0.5→1 与 0.6→1；`Zzz` 以 92×94 原图为坐标，三枚位于 `(0, 0)`、`(-80, -30)`、`(-190, 7)`，绝对缩放 0.8 / 0.9 / 1。这四项不能套用 `width*540`。`Twinkle` 在缩放后再除以 0.5，第一颗星静止宽度是 `0.08*540/0.5=86.4`，另外两颗是它的 0.9 和 0.6，间距按第一颗的显示宽度计算。白气泡里的图案：`Heart` 的心用气泡宽度定位纵坐标；`Shy` 斜线以中心为锚，位置按起始 0.8 倍宽度从气泡右下角量起，气泡本身从右下角放大；`Upset` 线条锚在气泡正中，尺寸为原生 173×126；`Bulb` 灯泡和光晕的水平位置是气泡宽度的一半，纵坐标是原生像素 100 和 82。`Upset` 与 `Bulb` 的白气泡没有调用缩放函数，未校准时使用原生 255×198。独立符号里，`Question` 从底边中点放大；`Chat` 的旋转支点在缩放后取值，约为显示宽度的 1.3 倍；`Sad` 未调用缩放，三条线的坐标盒是原生 88×160；`Sigh` 未调用缩放，原图宽 141，支点 `(1, -0.2)`；`Music` 的水平位移按起始 0.7 倍宽度计算。`Surprise` 的问号在感叹号起始宽度的 1.5 倍处，上游没有使用选项里的旋转角。PNG 原点不再假定为图片中心：角色 profile 的每套服装通过
`"spine":"kivo/spine/momoi_spr_HD/momoi_spr.skel"` 指向对应站立模型。prepare 读取 Spine 4.2.33
导出的真实 `x/y/width/height` 和 PNG 尺寸，保存 `spineBounds`；局部原点为
`(-x, y+height)`（转换到向下为正的 PNG 坐标）。模型和 PNG 必须是同一套未裁切站立导出，
宽高比差超过 2% 会报错；同宽高比不能代替人工确认模型对应关系。
气泡、立绘共用一个人物变换容器，人物缩放 1.5 倍时，两者一起缩放，不重复乘系数。
缺少对应模型时明确报错，不再用 `2024` 或图片中心猜位置。旧 scene 快照含气泡时需重新 prepare。
`Shy` 还保留右下锚点。大幅拉近或立绘本身出画时，气泡也可能出画；不要为了塞进画面另改气泡比例。
`Think` 没有上游参数，仍为自实现设置，不将其标成已验证的官方固定参数。


#### 实机校准与验收边界

`code/ba-production/templates/bubble-calibrations.json` 按 Spine 文件 SHA-256 登记实机校准，仅覆盖匹配模型和指定气泡；prepare 自动把命中的数据写入 scene 的 `spineBounds.bubbleAnchors`。`x` 为相对未裁切 PNG 宽度的位置、`y` 为相对 PNG 高度的位置、`width` 为相对 PNG 宽度的气泡宽度。它们属于人物局部坐标，随人物一起变换；Dot 还可记录内部圆点的相对位置和间距。不要复制一个角色的数值到其他角色或其他服装。

目前只有优香标准立绘的 `Dot` 根据用户实机截图完成了位置、尺寸和两颗圆点间距校准；第三颗圆点按同间距外推，时间曲线仍参考社区实现。其他角色及其他气泡只有社区参数近似复现，不能标记为已全部实机对齐。新增校准后要重新 prepare，旧 scene 快照不会自动更新。优香其他独立图标里，除 `Steam`、`Zzz`、`Tear`、`Twinkle` 外，已登记供截图勘误的临时摆位（`reviewPlacementNote`），不是实机测量值。这四项改回上游脊柱偏移和原图像素尺寸，不再使用那组临时锚点。白色气泡共享 Dot 框，独立符号使用自己的位置和大小，不能把所有符号都强制放大成 Dot 白气泡。

审片顺序：先在 HTML/Remotion 静态截图确认同角色、同服装、同画幅下的立绘摆放，再检查气泡轮廓、尾巴指向、圆点大小及间距；检查人物移动、1.5 倍缩放和转向时的绑定，最后生成含音效的视频。每个预设应留足入场、完整演出和淡出时间，标签不得遮挡气泡。测试通过不等于实机视觉验收；未经用户确认不合并 main，仍有未校准项时不要宣称全部完成。
