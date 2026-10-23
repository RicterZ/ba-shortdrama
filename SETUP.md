# 环境与复现

## 获取代码

```sh
git clone --recurse-submodules <本仓库地址> ba-shortdrama
# 已 clone 但没带 submodule：
git submodule update --init
```

`code/ba-production` 直接在本仓库里；`code/carocut` 是 [bilibili/carocut](https://github.com/bilibili/carocut) 的 submodule，版本由本仓库固定。`data/`、`videos/`、`local/`、`temp/`、`attachments/` 是本机素材与产物，不进版本库。

## 依赖

- macOS（本项目在 macOS 上验证；Linux 未测试）
- Node.js 18+
- ffmpeg / ffprobe
- Google Chrome：`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- [uv](https://docs.astral.sh/uv/)
- `code/ba-production/node_modules`：Remotion 4.0.417、React 19，在该目录下 `npm ci` 安装

新 checkout 的完整初始化：

```sh
git submodule update --init
uv sync
(cd code/ba-production && npm ci)
```

Python 依赖由仓库根目录的 `pyproject.toml` / `uv.lock` 统一声明，包括 `ba-production` 自己用的包和 carocut `requirements.txt` 里的包。环境装在仓库根目录的 `.venv`（不进版本库），每个 checkout 各一份，uv 全局缓存让重复安装很快：

```sh
uv sync
```

## 资源根（worktree 共用素材）

素材库 `data/`（角色、场景、背景、音频、UI 音效）和 `local/`（`.env`、下载缓存）从「资源根」读取；剧集产物 `videos/`、`temp/` 始终写在当前 checkout 里。资源根按以下顺序确定：

1. 环境变量 `BA_ASSETS_ROOT`
2. 仓库根目录的 `.ba-assets-root` 文件（一行路径，已 gitignore）
3. 仓库根目录本身（主 checkout 不需要任何配置）

新 worktree 指向主 checkout 即可，**不要软链** `data`、`local`、`videos` 等目录：

```sh
echo /Users/sakana/Projects/ba-shortdrama > .ba-assets-root
```

资源根路径不存在时脚本直接报错退出。

npm 脚本通过 `uv run python` 调用，会自动找到根目录的环境；carocut 升级、`requirements.txt` 变化时，同步修改 `pyproject.toml` 后重新 `uv lock`。

## 常用命令

```sh
cd code/ba-production

# 新建
npm run ep:new -- 003-summer-patch --title "夏日补丁" --characters saiba-momoi

# 准备一集：合成语音、算时间轴、复制立绘、生成 scene.json 和 assets.lock.json
EPISODE=003-summer-patch npm run ep:prepare
# 只改画面、复用已有语音时
EPISODE=003-summer-patch npm run ep:prepare -- --reuse-audio

# 校验全部剧集（只校验一集可加 -- --episode 003-summer-patch）
npm run ep:validate

# 先出快速预览审片，人工确认后再出成片
EPISODE=003-summer-patch npm run ep:preview
EPISODE=003-summer-patch npm run ep:final
# 单独抽帧
EPISODE=003-summer-patch npm run ep:still -- --frame 120
```

直接调用脚本也可以：

```sh
uv run python code/ba-production/scripts/prepare.py --episode 002-hidden-ending
```

## 语音 provider 选择（Agent 必须先询问用户）

Agent 在新 checkout 上第一次生成语音（`ep:prepare`、`npm run voice -- sample/episode`）之前，必须先询问用户使用哪个语音 provider，不得自行决定：

| 选项 | 需要用户提供 | 写入位置 |
|---|---|---|
| `vocu`（悟声，现有角色默认） | `VOCU_API_KEY`（付费账户）；各角色的 `voice_id` | key 写 `local/.env`，`voice_id` 写角色 profile |
| `fish-audio` | `FISH_AUDIO_API_KEY`；各角色的 `voice_id` | 同上 |
| `edge-tts` | 无，免费、不需要 key | 只改角色 profile |
| 不选 | 无 | 不改配置，生成时加 fallback 参数 |

流程：

1. 用户选了付费 provider：请用户提供 key，Agent 写入 `local/.env` 并 `chmod 600 local/.env`。不要把 key 写进命令行参数、提交、日志或 issue 评论；回复里只说"已写入"，不要回显 key。用户想自己填时，告诉他变量名，等他确认填好再继续。
2. 角色 profile 的 `voice.provider`、`voice.voice_id`、`voice.api_key_env` 要和所选 provider 一致；不同服务的音色 ID 不通用，缺 `voice_id` 时向用户要，不要猜。
3. 运行 `npm run voice -- check` 确认 key 和音色可用，通过后再生成。
4. 用户不选，或者暂时没有 key：使用 profile 里的 `voice.fallback`（通常是 `edge-tts`），生成时显式加 `--voice-fallback`（`prepare.py`）或 `--fallback`（`voice.py`），并告诉用户当前音频来自 fallback 声线，之后换回正式 provider 时要重新合成，不能带 `--reuse-audio`。

用户已经做过选择、`local/.env` 里已有对应 key 时，不必重复询问。

## API key

语音由各角色 profile 的 `voice.provider` 选择，可在同一集混用 `vocu`、`fish-audio`、`edge-tts`。现有三名角色默认走 Vocu，key 只保存在本机：

```sh
# local/.env（权限 600，已在 .gitignore 中）
FISH_AUDIO_API_KEY=...
VOCU_API_KEY=...
```

- 角色 profile 的 `voice.api_key_env` 指向这个变量；脚本只从环境变量或 `local/.env` 读取，不会把 key 写进 `scene.json`、日志或文档。
- 没有 key 或接口失败时，加 `--voice-fallback` 才会使用 profile 的 `voice.fallback`；默认直接报错，避免悄悄换声线。只尝试一级 fallback。
- Vocu 配置示例：`{"provider":"vocu","voice_id":"market:88762473-d08e-43e2-8e53-1982511e3707","api_key_env":"VOCU_API_KEY","language":"auto","speed":1.0,"format":"mp3"}`。切换服务时一起修改 provider、voice_id 和 api_key_env；不同服务的音色 ID 不通用。`language` 默认 `auto` 自动识别，日语等外语台词可显式写 `ja`；需要「外语配音 + 中文字幕」时在 `script.json` 里给该句加 `voice_text`。
- 语音生成统一走 `code/ba-production/scripts/voice.py`，不要临时写 inline 脚本：

  ```sh
  cd code/ba-production
  npm run voice -- check                                  # 配置 + key + 音色存在性（不合成）
  npm run voice -- sample --character tendou-kei --text "哼，听好了。"
  npm run voice -- episode --episode 003-game-dev-sneak --only L7
  ```

  `check` 默认只做轻量查询：provider、key 是否存在、`GET /api/voice/{id}` 是否可用，通常 1 秒内结束；加 `--synthesize` 才会合成试音并进入服务端生成队列。`episode` 只写 `audio/NNN.mp3`，之后用 `prepare.py --reuse-audio` 重建时间轴。`prepare.py` 内部调用同一套 provider。
- 悟声（Wusound）使用 [官方同步生成接口](https://dev.wusound.cn/)：`POST /api/tts/simple-generate` 返回 JSON 和签名音频 URL，再从该 URL 下载 MP3（不向 CDN 请求转发 API key）。API 主机是 `https://v1.wusound.cn`（`v1.vocu.ai` 会把有效 key 判成 401），需要付费账户和 API Key。生成请求本身可能排队，超时用 `--timeout`（默认 360）控制；`--reuse-audio` 会复用旧音频，切换音色后不要带此参数。
- Edge TTS 免费、无需 key；Fish Audio 需要联网和额度，`s2.1-pro-free` 的可用性以服务方为准。
- 素材：使用 `data/characters` 里已经落盘的立绘。
- 渲染：本机 Remotion + Chrome。

`PEXELS_API_KEY`、`PIXABAY_API_KEY`、`FREESOUND_API_KEY`、`CARO_LLM_*` 只在接入 CaroCut 的原生素材检索/生图流程时才需要。

## CaroCut Web 界面（可选）

```sh
cd code/carocut
../../local/tools/node_modules/.bin/opencode serve --hostname 127.0.0.1 --port 4096
source ../../.venv/bin/activate
PORT=3300 pnpm dev
```

该界面的五 Agent 流程需要先在 `opencode.json` 配置 provider/model。本项目的主链不依赖它。

## 注意

- 服务只绑定本机，不要暴露公网。
