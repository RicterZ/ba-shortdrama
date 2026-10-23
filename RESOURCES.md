# 素材获取：kivo.wiki（基沃托斯古书馆）

STUD-9 把 kivo.wiki 的资源获取跑通，并落到 `data/` 作为短剧的前期材料准备。全部入口是一个脚本：

```sh
cd code/ba-production
npm run res:kivo -- <子命令>
# 等价于 ../carocut/.venv/bin/python scripts/fetch_kivo.py <子命令>
```

脚本只做拉取、校验、索引，不改剧本、不渲染。下载是幂等的：已有文件默认复用，`--force` 才重下。

## 能拿到什么

| 类型 | kivo 来源 | 命令 | 落到哪里 |
|---|---|---|---|
| 角色信息 | `/api/v1/data/students/{id}` | `student <id\|中文名>` | `data/characters/<slug>/originals/kivo-student.json`、`kivo/summary.json` |
| 角色头像 | 学生字段 `avatar` | `student <id>` | `kivo/avatar.png` |
| 表情差分 | 学生字段 `gallery[*]`（标题含「差分」） | `student <id>` | `kivo/expressions/<差分组>/<原名>.png` |
| Live2D 立绘 | `/api/v1/data/spines/{id}` | `student <id> --spine` | `kivo/spine/<name>/{skel,atlas,png}` |
| 平面全身立绘 | kivo 不提供；按英文名匹配 SchaleDB | `student <id> --portrait` | `kivo/portrait.webp` |
| BGM | `/api/v1/musics/`、`/musics/{id}` | `music list/get/preset` | `data/audio/bgm/<id>-<slug>.ogg` |
| UI / 剧情 / 战斗音效 | `cloud.kivo.wiki/s/vmIj`（文章 24） | `sfx list/get/preset` | `data/audio/sfx/<原名>.wav` |
| 音频索引 | 脚本生成 | 自动 | `data/audio/manifest.json` |

kivo 没有剧情 UI 截图或界面布局数据，也没有单独的 UI 音效接口；短剧的 UI 造型按实机画面确认，点击音改从 Blue Archive Wiki 取，记录在 `docs/UI.md` 和 `data/ui/manifest.json`。kivo 的 `UI_*` 音效仍可用于对白推进等场景，但当前 UI 套件使用 `data/ui/sfx/`。

kivo 同样不提供平面全身表情立绘（只有 Live2D 和 840×840 脸部裁切）。全身图从 bluearchive.wiki 取，见下一节。

## 全身表情立绘（bluearchive.wiki）

bluearchive.wiki 的角色 `/gallery` 页面按服装分组，列出游戏内的全部立绘索引。每张是透明背景 PNG，约 1920px 高，同一服装下身体不变、只换脸。

```sh
cd code/ba-production

# 先看这套页面有哪些服装、每套有哪些表情索引
npm run res:sprites -- list Momoi

# 下载全部服装 × 全部表情，并同步 profile.yaml
npm run res:sprites -- get Momoi
npm run res:sprites -- get Momoi --slug saiba-momoi --no-profile
npm run res:sprites -- get Momoi --contact          # 额外生成每套服装的缩略图总览
```

`get` 的 `page` 可以是角色英文名（自动拼 `/gallery`），也可以是完整页面名。`--slug` 默认从 `kivo/summary.json` 的英文名反查角色目录；没有 kivo 资料时用页面名转 kebab-case。已有文件默认复用，只有缺失文件才下载；`--no-profile` 只更新 `sprites/manifest.json`。

才羽桃（`saiba-momoi`，2026-10-23）：

| 服装 | 目录 | 游戏立绘 ID | 张数 | 索引 |
|---|---|---|---:|---|
| 标准制服 | `sprites/default/` | `Momoi` | 10 | `00`–`08`, `99` |
| 女仆 | `sprites/maid/` | `CH0201` | 13 | `diorama_00`–`diorama_11`, `diorama_99` |
| 武装 | `sprites/battle/` | `NP0267` | 29 | `00`–`27`, `99` |
| 防寒服 | `sprites/winter/` | `NP0235` | 29 | `00`–`27`, `99` |

合计 81 张、约 68 MB。女仆装的索引带 `diorama_` 前缀，脚本按页面文件名原样保留，不重新编号。

### 结构化结果

```text
data/characters/<slug>/sprites/<outfit>/<index>.png
data/characters/<slug>/sprites/manifest.json
data/characters/<slug>/profile.yaml          # outfits 由 get 自动重写，persona/voice 不动
```

`manifest.json` 记录来源页面 / API / 抓取时间 / 权利说明，以及每套服装的 `id`、中文名、`game_sprite_id`、`type`、`variant`、`background`；每张图记录 `key`、`file`、尺寸、字节数、SHA-256、wiki 原始文件名和直链。

`profile.yaml` 的每个 outfit 同时保留**原始索引**和**语义别名**：

- 原始索引（`00`、`diorama_03` 等）是权威键，和 wiki / 游戏资源一一对应。
- 语义别名（`default`、`happy`、`worried`、`excited`、`shocked`、`sad`、`angry`、`smug` 等）只是短剧的生产约定，方便 `script.json` 的 `emotion` 直接命中；别名来自对缩略图总览的人工目视标注，不是官方表情名。
- 每套服装的 `default` 由脚本里的 `OUTFIT_DEFAULT_KEYS` 明确指定：标准制服 / 防寒服指向 `00`，武装装指向 `02`，女仆指向 `diorama_00`；不再按文件名顺序自动猜。

写入 profile 时路径相对角色目录（`sprites/default/00.png`），和 `lib.read_character` 的解析方式一致；manifest 里则保留项目根相对路径，便于跨目录检索。

### 边界

- 只有 `gallery` 页面列出的索引才会下载；页面没有的服装或表情不会被猜出来。
- 写索引前会核对页面列出的全部文件：任意一张没有解析到 URL、数量与页面不符，或本地文件缺失 / 哈希不符，脚本都会失败退出，且**不覆盖**已有的 `manifest.json` 和 `profile.yaml`（`missing` 也保持原样）。回归测试：`npm run test:sprites`。
- 武装 / 防寒服的 `00`–`27` 不是每个编号都是不同表情，部分编号是姿势或状态差分；按需使用，写剧本时优先用语义别名。
- 表情别名是当前这一版的人工标注；新增角色或 wiki 改版后先跑 `list` + `--contact`，重新核对再补别名。
- 图片权利仍属 NEXON / 权利方；wiki 的版权说明见 <https://bluearchive.wiki/wiki/Blue_Archive_Wiki:Copyrights>，公开发布或商用前必须核实。

## 常用命令

```sh
# 角色
npm run res:kivo -- student list --name 才羽
npm run res:kivo -- student 2 --portrait --spine

# BGM：先查再取，或直接取起步合集
npm run res:kivo -- music list --match School
npm run res:kivo -- music get 7
npm run res:kivo -- music preset

# 音效：UI_Button_Touch = 点击，UI_Button_Back = 返回，UI_Complete_Check = 确认
npm run res:kivo -- sfx list --match UI_Button
npm run res:kivo -- sfx get UI_Button_Touch UI_Button_Back
npm run res:kivo -- sfx preset

# 校验 manifest、文件大小与 SHA-256
npm run res:check
```

`student` 的 `slug` 默认取英文姓名：kivo id 2 → `saiba-momoi`，与现有角色目录一致；皮肤变体会追加 id。`--slug` 可覆盖。

## 已实测的 API 契约（2026-10-23，kivo 1.0.0-beta.43）

Base：`https://api.kivo.wiki/api/v1`。响应统一包一层 `{code, codename:"Koyuki", data, message, success}`。图片、音频、spine 在 `https://static.kivo.wiki`，接口返回的 `//static...` 需要补 `https:`。

| 端点 | 说明 |
|---|---|
| `GET /data/students/?page=&page_size=&name=` | 学生列表；`name` 支持中文片段；含皮肤变体（同一角色多条，`skin` 非空） |
| `GET /data/students/{id}` | 完整档案：多语言姓名、学校 id、社团关系 id、年龄/身高/生日/兴趣、简介、战斗数据、语音元数据、表情差分 `gallery`、spine id 列表 |
| `GET /data/schools/?page=&page_size=` | 学校 id → 名称 |
| `GET /data/relations/?page=&page_size=` | 社团 / 关系名称 |
| `GET /data/spines/?page=&page_size=` | 立绘索引；`type` 为 `spr`（立绘）/`home`（回忆大厅）/`model` |
| `GET /data/spines/{id}` | `skel_file`、`atlas_file`、`images`（Live2D 图集） |
| `GET /musics/?page=&page_size=` | BGM 列表（1003 首、115 个专辑）；**不支持过滤参数**，脚本本地筛选 |
| `GET /musics/{id}` | 单曲详情，`file` 是原始 `.ogg` |
| `GET /search/?keywords=&page=&page_size=` | 全站搜索；文章 24 是《游戏内全音效素材速查表》 |

音效分享是 Cloudreve v3 公共分享，会话流程：

```text
GET  cloud.kivo.wiki/api/v3/share/info/vmIj?password=kivowiki      # 解锁，拿 cookie
GET  cloud.kivo.wiki/api/v3/share/list/vmIj/?path=/               # 3158 个 wav 的清单
PUT  cloud.kivo.wiki/api/v3/share/download/vmIj?path=/<name>.wav   # 返回阿里云 OSS 签名地址
```

分享密码是 kivo 文章里公开的 `kivowiki`。清单缓存在 `local/cache/kivo/sfx-catalog.json`，7 天刷新；`sfx list --refresh` 强制刷新。下载地址约 15 分钟过期，脚本每次现取。

## 数据布局

```text
data/characters/<slug>/originals/kivo-student.json   # 原始 API 响应，保留全部字段和语音 URL
data/characters/<slug>/kivo/summary.json             # 供写 profile.yaml 的精简档案
data/characters/<slug>/kivo/avatar.png
data/characters/<slug>/kivo/portrait.webp            # 可选，来自 SchaleDB
data/characters/<slug>/kivo/expressions/<组>/<图片>   # 脸部差分，840×840 RGBA
data/characters/<slug>/kivo/spine/<name>/            # Live2D skel/atlas/贴图
data/characters/<slug>/sprites/<outfit>/<index>.png  # 全身表情立绘（bluearchive.wiki）
data/characters/<slug>/sprites/manifest.json         # 立绘索引：来源、游戏 ID、尺寸、哈希、直链

data/audio/bgm/<id:04d>-<slug>.ogg
data/audio/sfx/<原名>.wav
data/audio/manifest.json                             # 索引：来源、哈希、大小、用途、权利说明
```

`summary.json` 把学校 / 社团 id 解析成名字，并带上 `combat` 摘要与语音条数，写 `profile.yaml` 时不用再翻原始 JSON。语音文件本身不下载；68 条左右的 URL 都在 `originals/kivo-student.json` 里。

`data/audio/manifest.json` 与 `data/backgrounds/manifest.json` 同一套思路：每条记录 `id`、`kind`、`path`、`sha256`、`size`、来源 URL 和权利说明。`npm run res:check` 会核对文件存在、大小、哈希、重复路径和容器头。

## 立绘的边界（重要）

- kivo 角色页展示的是 **Live2D**：`data/spines/{id}` 给的是 `skel`/`atlas`/2048×2048 图集，不是可以直接放进 `image-stage` 的透明全身 PNG。当前 Remotion 模板没有 Live2D 渲染器，spine 包先作为素材沉淀，后续接 `spine-canvas`/`pixi-spine` 时直接用。
- `gallery` 里的「初始立绘差分」「防寒服差分」是 **脸部裁切**（840×840 RGBA），用于对照表情，不能当全身立绘。`summary.json` 里逐张记录了尺寸。
- 需要平面全身立绘时有两种来源：`--portrait` 从 SchaleDB 取单张默认立绘；要全部服装 × 全部表情时用 `npm run res:sprites -- get <英文名>` 从 bluearchive.wiki 取。
- `fetch_sprites.py` 会直接把 `outfits` 写进 `profile.yaml`（persona、voice 不动），因此新角色落地时可以先用它铺好立绘，再人工确认音色。若角色还没有 profile，加 `--no-profile` 只入库图片和 manifest。

## 音效目录

分享里共 3158 个 `.wav`：

| 前缀 | 数量 | 含义 |
|---|---:|---|
| `SFX_` | 2311 | 战斗音效（角色技能、爆炸、枪械等） |
| `SE_` | 613 | 剧情音效（环境、动作、提示） |
| `UI_` | 180 | 界面音效（按钮、确认、奖励、抽卡等） |
| `Main_` | 29 | 主界面 / 大厅 |
| `FX_` | 9 | 关卡环境音 |
| 其他 | 16 | 技能、角色专属等 |

短剧起步合集（`sfx preset`，20 个）覆盖：点击 `UI_Button_Touch`、返回 `UI_Button_Back`、确认 `UI_Complete_Check`、选项 `UI_Bit_Select`、提示 `UI_Notice`、气泡 `UI_Bubble`、星星 `UI_Star`、三连铃 `UI_Chime_01..03`、加载 `UI_Loading`、准备 `UI_Ready`、转场 `UI_Transition_Whoosh_ST`、错误 `UI_Error_Neg`、淡入淡出 `UI_Fade`、解锁 `UI_Unlock`、升级 `UI_LevelUp`、评级 `UI_Rank`、暂停 `UI_Pause`、警报 `UI_Alarm`。

BGM 起步合集（`music preset`）：Constant Moderato、Luminous memory、Mischievous Step、Lovely Picnic、Colorful Mess、Unwelcome School、Step by Step，都是游戏内曲目，适合日常/搞笑/标题场景。完整列表用 `music list --match` 查。

## 权利

kivo 是玩家整理的资料站，素材权利仍属《蔚蓝档案》权利方。使用条款见 <https://kivo.wiki/license>。本次只做到「本地技术验证可用」：

- 不因 kivo 公开可下载就获得再分发、商用或二创授权；
- 公开发布、打包资源或商业使用前必须核对权利方政策；
- 音频入库时 `manifest.json` 每条都写了 `rights` 字段，发布前逐项确认，不要把「有文件」当成「有授权」；
- 官方 BGM / 音效不要用于暗示官方背书。

## 缓存与排错

- 参考表和音效目录缓存在 `local/cache/kivo/`，SchaleDB 学生表也缓存在这里（7 天）。删掉缓存即可强制重拉。
- 音效分享若报「仍处于锁定状态」，说明 kivo 改了分享密码或链接；到 <https://kivo.wiki/article/24> 重新确认后改脚本顶部的 `SHARE_PASSWORD` / `SHARE_KEY`。
- 所有下载先写 `.part` 再原子替换，失败不会留下半个文件。
- `npm run res:check` 失败时先看是缺文件还是哈希不符；手工替换过素材就删掉对应 manifest 条目重新拉取。
