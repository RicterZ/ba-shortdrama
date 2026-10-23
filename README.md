# 蔚蓝档案短剧工作区

用 Remotion 把台本、分镜、角色立绘和合成语音渲染成《蔚蓝档案》风格的剧情短片。代码在 `code/`，角色与场景素材在 `data/`，每集数据在 `videos/<集>/`。

## 一条链

```sh
cd code/ba-production
npm run res:kivo -- student 2 --portrait --spine   # 角色资料与立绘（可选，前期一次）
npm run res:sprites -- get Momoi                    # 全部服装 × 全部表情全身立绘（可选）
npm run res:kivo -- music preset                    # BGM 起步合集（可选）
npm run res:kivo -- sfx preset                      # 音效起步合集（可选）
npm run res:check                                   # 音频索引与哈希
npm run voice -- check                              # 语音 provider / key / 音色
EPISODE=002-hidden-ending npm run ep:prepare     # 语音 + 时间轴 + 素材快照 + scene.json
npm run ep:validate                              # schema、素材、字幕、音画时长、哈希
EPISODE=002-hidden-ending npm run ep:preview     # 快速预览（半尺寸、1/3 帧率），人工审片
EPISODE=002-hidden-ending npm run ep:final       # 审片通过后出高质量成片
EPISODE=002-hidden-ending npm run ep:still -- --frame 120   # 单独抽帧（可选）
```

正式流程：prepare → validate → preview → 人工审片 → final。

新建一集：

```sh
npm run ep:new -- 003-summer-patch --title "夏日补丁" --characters saiba-momoi
```

## 角色与场景 profile

- `data/characters/<id>/profile.yaml`：人设、台词写作约定、语音 provider/音色绑定、多套服装及每套的立绘表。写台词前先读这里。
- `data/scenes/<id>/scene.yaml`：场景渲染器、背景图、调色板和光线变体。分镜用 `"scene": {"id": "game-dev-room", "variant": "lamp"}` 引用。

语音默认使用 profile 的主 provider（现有角色为 Vocu），显式加 `--voice-fallback` 才切到备用 provider（Fish Audio / Edge TTS）。key 只放在 `local/.env`。语音不是原作声优，也没有做声音克隆；合成语音说明放在 `review.json` 和发布简介里。

## 边界

- 只支持「立绘演出 + 对白」：角色有出场和镜头内走位，没有 Live2D、口型、骨骼动画或程序化微动。
- 场景渲染器只有 `image-stage`：读取背景图，叠加光线、暗角和轻微推拉；模板不自行绘制房间。
- 剧情 UI 按游戏实机样式实现（对白、选择条、`AUTO`/`MENU`、标题带、点击音与点击特效），见 `docs/UI.md`。
- 没有自动投稿；B 站发布必须人工确认。
- 素材来自 SchaleDB 镜像、kivo.wiki 和 Blue Archive Wiki，权利属原权利方。公开发布或商用前必须核实，见 `ASSETS.md` 和 `RESOURCES.md`。

## 文档

- `SETUP.md`：环境、依赖、API key
- `WORKFLOW.md`：每集的制作步骤与数据格式
- `ARCHITECTURE.md`：目录、数据流、模板
- `ASSETS.md`：素材来源与授权
- `RESOURCES.md`：kivo.wiki / bluearchive.wiki 素材获取脚本
- `docs/UI.md`：剧情 UI 设计 token
