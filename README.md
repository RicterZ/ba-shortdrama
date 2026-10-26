# 蔚蓝档案短剧工作区

用 Remotion 把台本、分镜、角色立绘和合成语音渲染成《蔚蓝档案》风格的剧情短片。代码在 `code/`，角色与场景素材在 `data/`，每集数据在 `videos/<集>/`。

## 内置模板
- 官方游戏风格：`official`
- 二创《我是卧底》：`who-is-the-spy`

## 功能

- **台本到成片**：台词、分镜、角色立绘和合成语音一起生成时间轴，渲染成带配音、BGM、音效的 MP4。
- **立绘演出**：表情切换、说话时他人压暗、进场（淡入、滑入）、镜头内走位与跳跃、转身，以及 9 种动作预设（跳、连跳、打招呼、摇晃、僵住、特写、左右倒下、隐藏）。
- **情绪气泡**：20 种游戏内气泡（爱心、愤怒、感叹号、问号、汗、省略号等）和音效。位置按立绘骨骼读出的脸部中心计算，任何带 Spine 骨骼文件的角色都能自动放对，跟着立绘移动、缩放。
- **剧情 UI**：片头标题带、对白框（姓名、社团、逐字打字、▼ 继续提示）、选项条、剧情按钮、`AUTO`/`MENU` 和点击特效，按游戏实机样式实现。
- **镜头转场**：镜头之间的叠化等转场，由官方 `@remotion/transitions` 渲染。
- **导出到必剪**：`ep:bcut` 把一集写成必剪草稿，便于二次剪辑：
  - 背景和立绘是图片，台词、词牌、投票字是可编辑的原生字幕。
  - 进场、走位、动作预设和转身写成必剪关键帧。
  - 片头、对话框、界面按钮是图片；气泡、选项是透明视频片段。
  - 配音、BGM、音效分轨。
  - 转场叠化暂不导出。

## 快速开始

把这个仓库地址交给你的 DeepSeek Hareness / Claude / Codex / Cursor，对她说：
```text
请先安装 RicterZ/ba-shortdrama 项目，我想用这个项目生成视频：生成一段5s地视频，不要开头的 episode 展示，视频内容为才羽桃井在游戏开发部室里笑着并且雀跃地对我说“你好！老师！”，说完话后弹出爱心气泡。
```
你会得到如下视频：

https://github.com/user-attachments/assets/39d2ecca-8bbb-4426-875f-5b2a94759027



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
EPISODE=002-hidden-ending npm run ep:bcut     # 导出必剪草稿（可选），安装见 WORKFLOW.md
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

- 只支持「立绘演出 + 对白」：角色有出场和镜头内走位，没有 Live2D、口型、骨骼动画或程序化微动。Spine 骨骼文件只用来定位气泡，不驱动动画。
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
