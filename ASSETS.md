# 素材及角色来源

获取脚本的命令与契约见 `RESOURCES.md`。

## 角色

| 角色 | 目录 | kivo id | SchaleDB ID | 立绘（`sprites/`） |
|---|---|---:|---:|---|
| 才羽桃 | `saiba-momoi` | 2 | 13011 | `default` / `maid` / `battle` / `winter`，共 81 张 |
| 才羽绿 | `saiba-midori` | 27 | 10016 | `default` / `maid` / `battle` / `winter`，共 67 张 |
| 天童凯伊 | `tendou-kei` | 518 | 无平面立绘 | `default` / `amas` / `prototype` / `unarmed`，共 114 张 |

每个角色目录的内容：

| 路径 | 内容 |
|---|---|
| `profile.yaml` | 人设、台词约定、语音、服装与立绘表 |
| `sprites/<outfit>/<index>.png` | bluearchive.wiki 全身表情立绘，透明 PNG |
| `sprites/manifest.json` | 立绘索引：游戏 ID、尺寸、哈希、wiki 直链 |
| `originals/kivo-student.json` | kivo 原始 API 响应 |
| `kivo/summary.json`、`kivo/avatar.png` | 精简档案与头像 |
| `kivo/portrait.webp` | SchaleDB 默认立绘（仅有 SchaleDB 立绘的角色） |
| `kivo/expressions/` | 840×840 脸部差分，仅作表情参考，模板不消费 |
| `kivo/spine/` | Live2D 包，模板不消费 |

- `profile.yaml` 的 `outfits` 以原始索引（`00`、`diorama_03` 等）为权威键，另有人工标注的语义别名（`happy` / `worried` / `shocked` 等）。别名是制作约定，不是官方表情名。分镜写 `outfit` + `emotion` 换图；未登记的表情回退到该套服装的 `default`。
- `tendou-kei` 的 `unarmed` 服装别名是从 `default` 手工复制登记的。
- `persona` 与台词约定是二创生产用，不是官方设定。

## 语音

- 现有三名角色的主 provider 都是 Vocu（悟声），音色 ID 在 `voice.voice_id`。才羽桃的备用是 Fish Audio（`s2.1-pro-free`），绿和凯伊的备用是 Edge TTS。
- 备用 provider 只在显式加 `--voice-fallback` / `--fallback` 时启用。
- Key 只放在 `local/.env`（`VOCU_API_KEY`、`FISH_AUDIO_API_KEY`），权限 600，不进版本库。
- **不是原作声优，也没有做声音克隆。** 画面不压角标，说明放在 `review.json` 和发布简介里，公开发布时不能省略。
- Fish Audio 免费模型和 Edge TTS 不保证可商用，公开发布前核实服务条款和音色授权。

## BGM 与音效

- BGM：kivo 音乐库的游戏内曲目，原始 `.ogg`，在 `data/audio/bgm/`。在 `episode.yaml` 的 `bgm` 块引用，见 `WORKFLOW.md`。
- 通用音效：kivo 公开分享的游戏音效 WAV，在 `data/audio/sfx/`。
- 索引：`data/audio/manifest.json`，每条含 `id`、`kind`、`path`、`sha256`、`size`、来源 URL、用途和权利说明；`npm run res:check` 校验。
- 剧情 UI 音效：`data/ui/sfx/click.wav`、`select.wav`、`hover.wav`，来自 Blue Archive Wiki 的 `SE_Button_01.wav`、`SE_Confirm_01.wav`、`SE_Confirm_02.wav`；来源、处理方式和许可见 `data/ui/manifest.json`。prepare 会自动复制进每集，不需要手写路径。

## 背景库

背景图由工作区所有者提供的主题 zip（标注来源为 kivo.wiki）整理而来：

- 按 `data/scenes/<scene-id>/backgrounds/<scene-id>-<variant>.jpg` 命名；同一地点的 day / night / sunset / rain 等作为变体共存。
- 从原图居中裁切 16:9，输出 sRGB JPEG q90；原图宽 ≥1920 时为 1920×1080，否则 1280×720，不做 AI 放大。
- `data/backgrounds/manifest.json` 记录 `id`、`scene_id`、`name`、`category`、`variant`、`lighting`、`source_zip`、`source_file`、`source_bytes`、`path`、尺寸、`crop`、`sha256`、`tags`，以及排除项、重复项、损坏项和尺寸异常。
- 坏图或截断图记入 manifest 的 `damaged`，不中断整批处理。
- 已建 scene profile 的场景：`game-dev-room`、`millenium-campus`、`millenium-corridor`、`milleniumclub`（千年教室）、`millenium-seminar-club-room`（SEMINAR 部室）、`shopping-district`、`city-downtown`。其余场景按 manifest 索引，需要时再建 profile。

```sh
cd code/ba-production
npm run bg:build     # 从 temp/*.zip 重新解包、裁切、生成 manifest
npm run bg:check     # manifest、哈希、尺寸、重复登记、损坏项、scene profile 引用
npm run bg:test      # 回归测试
```

## 授权

这些是第三方镜像 / 资料站提供的游戏素材，权利属 NEXON Games / Yostar 等权利方，不因公开可下载而获得再分发或商用许可。公开发布、打包资源或商业使用前必须核实权利方政策：

- kivo.wiki 使用条款：<https://kivo.wiki/license>
- Blue Archive Wiki 版权说明：<https://bluearchive.wiki/wiki/Blue_Archive_Wiki:Copyrights>
- 各 manifest 的 `rights` 字段逐项确认，不要把「有文件」当成「有授权」。

## 新角色接入

1. `npm run res:kivo -- student <kivo id> --portrait --spine` 拉资料；`npm run res:sprites -- get <英文名>` 拉全部服装 × 全部表情立绘，并写入 `profile.yaml` 的 `outfits`。
2. 在 `data/characters/<id>/profile.yaml`（`schemas/profile.json`）补人设、`voice` provider/音色/fallback、`default_outfit`。
3. 每套服装至少要有一张 `default`（`fetch_sprites.py` 自动补齐）。
4. 在 `episode.yaml` 的 `characters` 中加入 `<id>`；分镜里用 `outfit` 选衣服。
5. 缺少的表情写进 `profile.missing`，prepare 会回退到 default 立绘并打印警告。
