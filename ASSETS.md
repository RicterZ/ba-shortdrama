# 素材及角色来源

## 才羽桃（saiba-momoi）

2026-10-23 从 SchaleDB 的 GitHub 镜像获取标准版，student ID **13011**。

- 数据：https://raw.githubusercontent.com/SchaleDB/SchaleDB/main/data/cn/students.json
- 立绘：https://raw.githubusercontent.com/SchaleDB/SchaleDB/main/images/student/portrait/13011.webp

已核对角色 ID、姓名、千禧年／游戏开发部设定，并目视确认立绘。原始数据在 `originals/`，立绘保留原始 WebP。

### 当前可用素材

| 素材 | 用途 | 状态 |
|---|---|---|
| `sprites/default.webp` | 旧路径兼容；`profile.yaml` 已改用分服装立绘 | 保留 |
| `sprites/{default,maid,battle,winter}/` | 4 套服装的全部表情全身立绘，共 81 张透明 PNG | 已入库，`profile.yaml` 已接入 |
| `sprites/manifest.json` | 立绘索引：游戏 ID、尺寸、哈希、wiki 直链 | 已入库 |
| `kivo/portrait.webp` | 同一张默认图的 kivo 拉取副本（跨源核对哈希一致） | 可用 |
| `kivo/expressions/` 40 张脸部差分 | 表情参考；840×840，**不是全身立绘** | 已入库，模板暂未消费 |
| `kivo/spine/` Live2D 包 | 初始立绘、回忆大厅、防寒服的 skel/atlas/贴图 | 已入库，模板暂未消费 |

`profile.yaml` 的 `outfits` 里每套服装都有 `default` 和全部原始索引，常用的情绪名（`happy` / `worried` / `excited` / `shocked` / `sad` / `angry` / `smug` 等）已作为别名指向具体索引。分镜写 `outfit` + `emotion` 就会换图；未登记的表情仍回退到该套装的 `default` 立绘，不冒充有素材。

## 才羽绿（saiba-midori）

2026-10-23 接入。kivo id **27**（`https://api.kivo.wiki/api/v1/data/students/27`），SchaleDB student ID **10016**。

- 资料：`originals/kivo-student.json`、`kivo/summary.json`、`kivo/avatar.png`、`kivo/portrait.webp`；脸部差分 35 张。
- 立绘：`sprites/{default,maid,battle,winter}/` 共 67 张透明 PNG（标准制服 11、女仆 14、武装 21、防寒服 21），索引在 `sprites/manifest.json`。
- 人设：游戏开发部原画师，才羽桃的双胞胎妹妹；害羞、句子短、对画有自信。`profile.yaml` 的 persona 与台词约定是二创生产用，不是官方设定。
- 音色：Edge TTS `zh-CN-XiaoyiNeural`（语速 0.95）；不是原作声优，也没有声音克隆。

## 天童凯伊（tendou-kei）

2026-10-23 接入。kivo id **518**（`https://api.kivo.wiki/api/v1/data/students/518`），SchaleDB 无平面立绘（DevName `kei` 未匹配）。

- 资料：`originals/kivo-student.json`、`kivo/summary.json`、`kivo/avatar.png`；脸部差分 122 张。
- 立绘：`sprites/{default,amas,prototype,unarmed}/` 共 114 张透明 PNG（标准制服 34、AMAS 26、Prototype 20、Unarmed 34），索引在 `sprites/manifest.json`。本集使用 `unarmed`（无武器）以免巨大轨道炮遮挡其他角色；`unarmed` 的情绪别名是手工从 `default` 复制并在本地登记的。
- 人设：原为爱丽丝体内的 AI，现为特异现象调查部成员；高傲、好胜、嘴硬心软。`profile.yaml` 的 persona 与台词约定是二创生产用，不是官方设定。
- 音色：Edge TTS `zh-CN-XiaoxiaoNeural`（语速 1.04、音高 -6Hz）；不是原作声优，也没有声音克隆。

## kivo.wiki 资源（STUD-9）

2026-10-23 跑通 <https://kivo.wiki> 的素材获取，脚本 `code/ba-production/scripts/fetch_kivo.py`（`npm run res:kivo`），契约与边界见 `RESOURCES.md`。

- 角色信息来自 `https://api.kivo.wiki/api/v1/data/students/{id}`，才羽桃为 kivo id **2**；原始响应在 `data/characters/saiba-momoi/originals/kivo-student.json`，精简档案在 `kivo/summary.json`。
- kivo 的角色立绘是 Live2D：`/data/spines/{id}` 提供 `skel` / `atlas` / 2048×2048 图集；当前 Remotion 模板没有 Live2D 渲染器，spine 包只是素材沉淀。
- kivo 的「差分立绘」是 840×840 的脸部裁切，不是全身透明立绘；平面全身图仍需 SchaleDB，脚本用 `--portrait` 按英文名匹配并下载，才羽桃的哈希与现有 `sprites/default.webp` 一致。
- 头像来自 `static.kivo.wiki`，落 `kivo/avatar.png`。

### BGM 与界面音效

- BGM：kivo 音乐库 `/api/v1/musics/`，入库 7 首起步曲目到 `data/audio/bgm/`（Constant Moderato、Luminous memory、Mischievous Step、Lovely Picnic、Colorful Mess、Unwelcome School、Step by Step），原始 `.ogg`，来源为游戏内曲目。
- 音效：kivo 文章《游戏内全音效素材速查表》的公开分享，共 3158 个 WAV；入库 20 个 `UI_` 界面音效到 `data/audio/sfx/`（点击、返回、确认、提示、铃声、转场等）。完整目录用 `npm run res:kivo -- sfx list` 查。
- 索引：`data/audio/manifest.json`，每条含 `id`、`kind`、`path`、`sha256`、`size`、来源 URL、用途和权利说明；`npm run res:check` 校验。
- BGM 已接入混音：`episode.yaml` 的 `bgm`（`file` / `volume` / `loop` / `fadeInFrames` / `fadeOutFrames`）由 `prepare.py` 复制进 `raws/audio/` 并写入 `scene.bgm`，Remotion 在整片期间循环播放并淡入淡出；分镜里不单独声明 BGM。

### 剧情 UI 音效（已接入）

- 文件：`data/ui/sfx/click.wav`（对白推进 / 按钮）、`select.wav`（选项确认）、`hover.wav`（选项出现）。
- 来源：Blue Archive Wiki 的官方游戏音效文件，`SE_Button_01.wav`、`SE_Confirm_01.wav`、`SE_Confirm_02.wav`；逐条 URL、原始时长、处理方式和许可见 `data/ui/manifest.json`。
- `prepare.py` 会把它们复制到该集 `raws/audio/ui/`，并在 `scene.json` 写入 `ui.sfx`；模板按帧触发，不需要每集手写路径。
- 许可见 `manifest.json` 的 `rights` 字段：音效版权属于 NEXON Games / Yostar，公开发布或商用前必须核实授权。

## bluearchive.wiki 全身表情立绘（STUD-9 追加）

2026-10-23 从 <https://bluearchive.wiki/wiki/Momoi/gallery> 获取才羽桃的全部平面立绘，脚本 `code/ba-production/scripts/fetch_sprites.py`（`npm run res:sprites`），详细契约见 `RESOURCES.md`。

- 4 套服装、81 张透明 PNG，约 1920px 高：标准制服 10 张（`Momoi`）、女仆 13 张（`CH0201`，索引 `diorama_00`–`diorama_11` 和 `diorama_99`）、武装 29 张（`NP0267`）、防寒服 29 张（`NP0235`）。
- 原图按服装落在 `data/characters/saiba-momoi/sprites/<outfit>/<index>.png`；索引同时写入 `sprites/manifest.json` 与 `profile.yaml` 的 `outfits`，路径相对角色目录。
- `profile.yaml` 保留原始索引作为权威键，并补充人工标注的语义别名；别名是制作约定，不是官方表情名。
- 图片仅在本地技术验证中使用；版权属 NEXON / 权利方，wiki 版权说明见 <https://bluearchive.wiki/wiki/Blue_Archive_Wiki:Copyrights>，公开发布或商用前必须核实。

## 语音

- 主引擎：Fish Audio，模型 `s2.1-pro-free`，才羽桃使用工作区所有者提供的音色 ID（记录在 `profile.yaml` 的 `voice.voice_id`）。
- Key 只放在 `local/.env` 的 `FISH_AUDIO_API_KEY`，权限 600，不进版本库、不写进成片数据。
- 备用引擎：Edge TTS，`zh-CN-XiaoyiNeural`，语速 +8%；只在显式加 `--voice-fallback` 时启用。
- **不是原作声优，也没有做声音克隆。** 画面不压「合成语音」角标，说明放在 `review.json` 和发布简介里；公开发布时不能省略。
- Fish Audio 的免费模型和 Edge TTS 都不保证商用可用；公开发布前必须核实服务条款和音色授权。

## 授权

这些是第三方镜像 / 资料站提供的游戏素材，不因镜像或 kivo.wiki 公开可下载而获得商业或再分发许可。当前仅用于用户要求的本地技术验证；后续公开发布、打包资源或商业使用前必须核实权利方政策。kivo 的使用条款见 <https://kivo.wiki/license>。

POC 阶段用的是工作区所有者提供的 `temp/学校相关.zip` 里的 `BG_GameDevRoom.jpg` 和 `BG_GameDevRoom_Night.jpg`，分别对应 `afternoon` 与 `monitor-glow` / `lamp` 变体。压缩包内标注来源为 kivo.wiki，原 zip 不改动，公开发布前必须核实权利。

## 背景库（STUD-8）

`temp/` 下 9 个主题 zip 已经整理成可引用的背景库：

- 原图 1149 张，排除 20 张（6 张特效叠加、8 张社团 Logo、6 张酒吧动画帧），入库 1129 张，分属 575 个场景。
- 全部按 `data/scenes/<scene-id>/backgrounds/<scene-id>-<variant>.jpg` 命名；同一地点的 day / night / sunset / rain 等作为变体共存。
- 统一从原图居中裁切 16:9（裁切框逐条记在 manifest），输出 sRGB JPEG q90；原图宽 ≥1920 时保留 1920×1080，否则 1280×720，不做 AI 放大。
- `data/backgrounds/manifest.json` 记录 `id`、`scene_id`、`name`、`category`、`variant`、`lighting`、`source_zip`、`source_file`、`path`、尺寸、`crop`、`sha256`、`tags`，以及排除项、重复项、损坏项和尺寸异常；每条都带来源文件大小（`source_bytes`）。
- 逐文件完整解码（`Image.load()`）后再裁切：坏图/截断图不会中断整批，而是记进 manifest 的 `damaged`（来源 zip、文件名、大小、失败阶段和错误信息），其余文件继续处理。
- 常用场景已生成 `data/scenes/<id>/scene.yaml`：`game-dev-room`、`millenium-campus`、`millenium-corridor`、`milleniumclub`（千年教室）、`millenium-seminar-club-room`（SEMINAR 办公室/部室，不是教室）、`shopping-district`、`city-downtown`；其余场景先按 manifest 索引，需要时再建 profile。
- 原始压缩包与解包暂存在 `temp/`、`local/backgrounds-library/staging/`，不进入交付目录。

重建和校验：

```sh
cd code/ba-production
npm run bg:build     # 从 temp/*.zip 重新解包、裁切、生成 manifest
npm run bg:check     # manifest、哈希、尺寸、重复登记、损坏项、scene profile 引用
npm run bg:test      # 坏图/截断图/重复/排除项的回归测试
```

这批图仍然只用于 POC；公开发布、打包或商用前必须核实 kivo.wiki 标注的来源与权利。

## 新角色接入

1. 先跑 `npm run res:kivo -- student <kivo id> --portrait --spine` 拉资料（`kivo/summary.json` 可直接对照人设）；再跑 `npm run res:sprites -- get <英文名>` 拉全部服装 × 全部表情的全身立绘，它会直接更新 `profile.yaml` 的 `outfits`。
2. 在 `data/characters/<id>/` 建 `profile.yaml`（`schemas/profile.json`）：人设、`voice` provider/音色/fallback、`default_outfit`、`outfits` 及每套衣服的表情立绘与 SHA-256。
3. 立绘放 `sprites/<outfit>/`，原始文件放 `originals/`；每套服装至少要有一张 `default`（`fetch_sprites.py` 自动补齐）。
4. 在 `episode.yaml` 的 `characters` 中加入 `<id>`；分镜里用 `outfit` 选衣服。
5. 缺少的表情写进 `profile.missing`，prepare 会回退到 default 立绘并打印警告。
