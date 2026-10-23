# 蔚蓝档案短剧工作区

本机路径：`~/Projects/ba-shortdrama`。代码、角色资源、每集数据分别放在 `code/`、`data/`、`videos/`。

## 当前状态

- `videos/003-game-dev-sneak/output/003-game-dev-sneak.mp4`：175.8 秒、10 个镜头、55 句台词，「游戏开发部偷跑日常」；才羽桃 / 才羽绿 / 天童凯伊，游戏开发部活动室午后 / 显示器冷光 / 台灯三档光。语音为 Edge TTS 回退音色（Fish Audio 账户额度为 0）；背景音乐 `Mischievous Step`；凯伊使用 unarmed 的 flustered / embarrassed / panic / shy / bashful 表情差分，并按官方身高比例放大；角色在同一镜头内有走位动画。详见 `review.json`。
- `videos/002-hidden-ending/output/002-hidden-ending.mp4`：28.2 秒、3 个镜头、5 句台词，Fish Audio 语音 + 工作区所有者提供的游戏开发部背景（POC 临时使用）。
- `videos/001-momoi-pilot/output/001-momoi-pilot.mp4`：12.9 秒单镜头回归样片，同样使用 POC 背景。
- `videos/900-ui-kit/output/900-ui-kit.mp4`：21.2 秒 UI 校准样片，集中展示标题带、对白、`AUTO`/`MENU`、可点击按钮、选择条和点击音/点击特效。
- 背景素材库已整理完成（STUD-8）：`temp/` 下 9 个 zip 共 1149 张原图，去重后 1129 张背景 / 575 个场景，按 16:9 裁切并索引在 `data/backgrounds/manifest.json`，常用场景已建 scene profile（游戏开发部活动室、千年校园/走廊/教室/研讨部室、商业街、城市中心）。
- 素材获取已接上 kivo.wiki（STUD-9）：角色信息 / 头像 / 表情差分 / Live2D spine、BGM、UI 音效都能用 `npm run res:kivo` 拉取，落到 `data/characters/<id>/kivo/` 和 `data/audio/`，索引在 `data/audio/manifest.json`。命令、API 契约和素材边界见 `RESOURCES.md`。
- 全身表情立绘已接上 bluearchive.wiki：才羽桃 4 套服装共 81 张透明 PNG，才羽绿（kivo id 27）4 套共 67 张，天童凯伊（kivo id 518）4 套共 114 张；全部按服装落到 `data/characters/<id>/sprites/<outfit>/`，索引在 `sprites/manifest.json`，并写入 `profile.yaml` 的 `outfits`。用 `npm run res:sprites -- get Momoi|Midori|Kei` 复现。
- 剧情 UI 校准完成（STUD-11）：设计参考、颜色/字号 token 和音效来源见 `docs/UI.md`；可直接用的 UI 音效在 `data/ui/sfx/`，来源与许可见 `data/ui/manifest.json`。

现有角色默认用 **Vocu（悟声）** 合成中文语音，显式加 `--voice-fallback` 才切到 profile 里的备用 provider（Fish Audio / Edge TTS）。key 只放在 `local/.env`，不写进文档、不进版本库。**不是原作声优，也没有做声音克隆**；画面不再压角标，合成语音说明保留在 `review.json` 和发布简介里。

## 一条链

```sh
cd code/ba-production
npm run res:kivo -- student 2 --portrait --spine   # 角色资料与立绘（可选，前期一次）
npm run res:sprites -- get Momoi                    # 全部服装 × 全部表情全身立绘（可选）
npm run res:kivo -- music preset                    # BGM 起步合集（可选）
npm run res:kivo -- sfx preset                      # UI 音效起步合集（可选）
npm run res:check                                   # 音频索引与哈希
npm run voice -- check                              # 语音 provider / key / 每个角色试音
npm run voice -- episode --episode 003-game-dev-sneak --only L7   # 单独补语音（可选）
EPISODE=002-hidden-ending npm run ep:prepare     # 语音 + 时间轴 + 立绘快照 + scene.json
npm run ep:validate                              # schema、素材、字幕、音画时长、哈希
EPISODE=002-hidden-ending npm run ep:preview     # 快速预览（半尺寸、1/3 帧率），人工审片
EPISODE=002-hidden-ending npm run ep:final       # 审片通过后出高质量成片
EPISODE=002-hidden-ending npm run ep:still -- --frame 120   # 单独抽帧（可选）
```

唯一正式流程：prepare → validate → preview → 人工审片 → final。`ep:render` 只是不带 profile 的旧入口，新集不要用。

新建一集：

```sh
npm run ep:new -- 003-summer-patch --title "夏日补丁" --characters saiba-momoi
```

完整参数与数据结构见 `WORKFLOW.md`，链路设计见 `ARCHITECTURE.md`，环境见 `SETUP.md`。

## 角色与场景 profile

- `data/characters/<id>/profile.yaml`：人设、台词写作约定、语音 provider/音色绑定、多套服装及每套的立绘表。agent 写台词前先读这里。
- `data/scenes/<id>/scene.yaml`：场景渲染器、背景图位置、调色板和光线变体（午后 / 显示器冷光 / 傍晚台灯）。背景图由工作区所有者提供，模板不自行绘制房间。分镜用 `"scene": {"id": "game-dev-room", "variant": "lamp"}` 引用。

## 边界

- 当前只支持「立绘演出 + 对白」；没有 Live2D、口型。角色有出场和镜头内走位，静止时立绘保持不动，不做呼吸、说话抖动等程序化微动，也没有逐帧作画或骨骼动画。
- 才羽桃现有 4 套服装的全身表情立绘（标准制服 10 张、女仆 13 张、武装 29 张、防寒服 29 张），`profile.yaml` 已按服装和表情索引登记；模板按 `outfit` + `emotion` 直接换图。kivo 的 40 张脸部差分和 Live2D spine 仍只是素材沉淀，模板不消费。
- 场景渲染器目前只有 `image-stage`：读取工作区所有者提供的背景图，叠加光线、暗角和轻微推拉；新场景先放图，再在模板里扩展 renderer。`game-dev-room` 的 POC 背景来自 `temp/学校相关.zip`，正式素材库整理见 STUD-8。
- 剧情 UI 按游戏内实机样式重做：底部渐变压暗 + 白字姓名/青色社团/细分割线/闪烁青色三角的对白，浅蓝切面圆角选择条，`AUTO`/`MENU` 斜切按钮，以及全宽浅蓝 `Episode` 标题带。样式来源和设计 token 见 `docs/UI.md`。
- 标题卡是可选的：删掉 `episode.yaml` 里的 `intro` 就不会出现；分镜可选用 `choices` 渲染选择条，也可用 `buttons` 放可点击按钮。
- 点击音与点击特效已接入：对白推进、选项出现/确认、按钮按下都会播放 BA 音效并触发扩散圆环 + 菱形火花；音效文件与来源见 `data/ui/manifest.json`。
- 没有付费模型调用、没有自动投稿；B 站发布必须人工确认。
- 素材来自 SchaleDB 镜像、kivo.wiki 和 Blue Archive Wiki；BGM 已接入混音（`episode.yaml` 的 `bgm` 块，见 `WORKFLOW.md`），UI 音效已接入。公开发布或商用前必须核实权利方政策，见 `ASSETS.md` 和 `RESOURCES.md`。

阅读顺序：SETUP.md → WORKFLOW.md → ARCHITECTURE.md → ASSETS.md。
