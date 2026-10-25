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
- PyAV（`av`，由 `uv sync` 安装）：Python 的媒体探测和语音裁剪直接调用 FFmpeg 库，不需要系统 `ffmpeg` / `ffprobe` 命令
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

PyAV 在有预编译 wheel 的 Windows/Linux/macOS 平台随包提供 FFmpeg 库，不把 binary 放进 Git；没有匹配 wheel 的平台需要自行准备编译依赖。Remotion 渲染的原生依赖仍由 npm 管理，整个项目目前只在 macOS 验证。`WORKFLOW.md` 中手动调用 `ffmpeg` 切片的可选命令仍需另行安装 FFmpeg。

## 资源与产物

所有任务（包括 Multica agent）都直接在主 checkout 里工作，不使用 git worktree。

- **资源**：`data/`（角色、场景、背景、音频、UI 音效）、`local/`（`.env`、日志、下载缓存）、`temp/`。全局一份，所有任务共享。
- **产物**：`videos/<剧集>/`（台本、音频、时间轴、预览和成片）。不进 git，切分支不会丢。

脚本固定读写仓库根目录下的这些目录，没有环境变量或配置文件覆盖。

`prepare`、`voice episode`/`retrim`、`render` 运行时会锁住剧集目录（`videos/<剧集>/.lock`，进程退出或被中断时自动释放）。同一集已有任务在写时，第二个任务直接报错退出，不会互相覆盖。

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
| `gpt-sovits` | 已启动的官方 `api_v2.py` 服务地址、服务端参考音频路径及语言 | 角色 profile（配置见下文） |
| 不选 | 无 | 不改配置，生成时加 fallback 参数 |

流程：

1. 用户选了付费 provider：请用户提供 key，Agent 写入 `local/.env` 并 `chmod 600 local/.env`。不要把 key 写进命令行参数、提交、日志或 issue 评论；回复里只说"已写入"，不要回显 key。用户想自己填时，告诉他变量名，等他确认填好再继续。
2. 角色 profile 的 `voice.provider`、`voice.voice_id`、`voice.api_key_env` 要和所选 provider 一致；不同服务的音色 ID 不通用，缺 `voice_id` 时向用户要，不要猜。`gpt-sovits` 不使用 `voice_id`，而使用参考音频及语言字段。
3. 用户选 `gpt-sovits`：先请用户按角色填写或确认 `base_url`（本机默认地址也需确认）、`ref_audio_path`、`text_lang`、`prompt_lang`、`prompt_text`（参考音频准确转写；留空须用户确认）。说明参考路径属于服务端；询问各角色共用模型还是使用独立模型，独立模型需提供各自服务地址。可选项 `speed` 默认 1.0、`text_split_method` 默认 `cut5`。缺少必填配置时停止并询问，不猜路径、语言、转写或模型，不擅自换成其他 provider。完整示例见下文「GPT-SoVITS（自托管）」。
4. 运行 `npm run voice -- check` 检查配置；对 GPT-SoVITS 这一步不联网，不能证明模型可用。用户确认配置后，运行 `npm run voice -- check --character <角色id> --synthesize` 做真实试音，并请用户确认声线，再生成整集。
5. 用户不选，或者暂时没有 key：使用 profile 里的 `voice.fallback`（通常是 `edge-tts`），生成时显式加 `--voice-fallback`（`prepare.py`）或 `--fallback`（`voice.py`），并告诉用户当前音频来自 fallback 声线，之后换回正式 provider 时要重新合成，不能带 `--reuse-audio`。已选 GPT-SoVITS 但配置不全时，应先等待补齐，不适用此默认 fallback 流程。

用户已经做过选择、`local/.env` 里已有对应 key 时，不必重复询问。

## API key

语音由各角色 profile 的 `voice.provider` 选择，可在同一集混用 `vocu`、`fish-audio`、`edge-tts`、`gpt-sovits`。现有三名角色默认走 Vocu，key 只保存在本机：

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

### GPT-SoVITS（自托管）

适配[官方 `api_v2.py`](https://github.com/RVC-Boss/GPT-SoVITS/blob/main/api_v2.py) 的 `POST /tts`，不是旧版 `api.py` 或 Gradio 接口。模型及运行环境由 GPT-SoVITS 单独管理，本仓库不安装推理依赖或下载模型。在其目录启动服务：

```sh
python api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
```

角色 `profile.yaml` 的 `voice` 示例：

```yaml
voice:
  provider: gpt-sovits
  base_url: http://127.0.0.1:9880
  ref_audio_path: /server/references/character.wav
  text_lang: ja
  prompt_lang: ja
  prompt_text: 参考音频中实际说出的台词
  speed: 1.0
  text_split_method: cut5
  fallback:
    provider: edge-tts
    voice_id: ja-JP-NanamiNeural
```

- `base_url` 可省略，默认 `http://127.0.0.1:9880`，不要加 `/tts`。官方接口不需要 API key；远程部署应通过可信网络连接，不要把无鉴权服务直接暴露到公网。
- `ref_audio_path`、`text_lang`、`prompt_lang` 必填。参考路径由**服务端**读取，不是本机上传；语言代码必须是已加载模型支持的值（如 `zh`、`ja`、`en`）。`prompt_text` 应填写参考音频的准确转写。
- `speed` 映射到 `speed_factor`。固定请求非流式 WAV，由共用裁静音流程转成最终 MP3；无需配置 `format`。字幕仍用 `text`，外语配音可用台词的 `voice_text`。
- `check` / `check --config-only` 仅校验本地配置，不保证服务在线、参考路径存在或模型可用；`check --synthesize` 才会调用服务验证。`sample`、`episode` 和 `prepare` 共用此 provider，重试与显式启用的 fallback 行为不变。
- 不自动调用全局模型切换接口。多角色共用同一模型时使用不同参考音频；需要不同模型时分别启动服务并在各角色配置不同 `base_url`，避免影响共享服务的其他请求。
- 本配置只是示例，不会修改现有角色声线。真实试音前先确认用户提供的服务地址、参考音频和模型授权。

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
