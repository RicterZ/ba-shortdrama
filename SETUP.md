# 环境与复现

## 依赖

- macOS（本项目在 macOS 上验证；Linux 未测试）
- Node.js 18+（当前 26.8.2）
- ffmpeg / ffprobe
- Google Chrome：`/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`
- Python：使用 `code/carocut/.venv`，其中已安装 `edge-tts`、`jsonschema`、`Pillow`
- `code/ba-production/node_modules`：Remotion 4.0.417、React 19

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
code/carocut/.venv/bin/python code/ba-production/scripts/prepare.py --episode 002-hidden-ending
```

## API key

语音由各角色 profile 的 `voice.provider` 选择，可在同一集混用 `vocu`、`fish-audio`、`edge-tts`。现有三名角色默认走 Vocu，key 只保存在本机：

```sh
# local/.env（权限 600，已在 .gitignore 中）
FISH_AUDIO_API_KEY=...
VOCU_API_KEY=...
```

- 角色 profile 的 `voice.api_key_env` 指向这个变量；脚本只从环境变量或 `local/.env` 读取，不会把 key 写进 `scene.json`、日志或文档。
- 没有 key 或接口失败时，加 `--voice-fallback` 才会使用 profile 的 `voice.fallback`；默认直接报错，避免悄悄换声线。只尝试一级 fallback；现有角色保留原 Fish Audio 配置为备用。
- Vocu 配置示例：`{"provider":"vocu","voice_id":"market:88762473-d08e-43e2-8e53-1982511e3707","api_key_env":"VOCU_API_KEY","speed":1.0,"format":"mp3"}`。切换服务时一起修改 provider、voice_id 和 api_key_env；不同服务的音色 ID 不通用。
- 语音生成统一走 `code/ba-production/scripts/voice.py`，不要临时写 inline 脚本：

  ```sh
  cd code/ba-production
  npm run voice -- check                                  # 配置 + key + 音色存在性（不合成）
  npm run voice -- sample --character tendou-kei --text "哼，听好了。"
  npm run voice -- episode --episode 003-game-dev-sneak --only L7
  ```

  `check` 默认只做轻量查询：provider、key 是否存在、`GET /api/voice/{id}` 是否可用，通常 1 秒内结束；加 `--synthesize` 才会合成试音并进入服务端生成队列。`episode` 只写 `audio/NNN.mp3`，之后用 `prepare.py --reuse-audio` 重建时间轴。`prepare.py` 内部调用同一套 provider。
- 悟声（Wusound）使用 [官方同步生成接口](https://dev.wusound.cn/)：`POST /api/tts/simple-generate` 返回 JSON 和签名音频 URL，再从该 URL 下载 MP3（与 Momoi 的 `vocu.py` 适配器一致；不向后者的 CDN 请求转发 API key）。实际 API 主机是 `https://v1.wusound.cn`（文档在 dev.wusound.cn；旧域名 `v1.vocu.ai` 会把有效 key 判成 401），需要付费账户和 API Key；`voice.py check` 默认只查音色，不再触发合成，`--synthesize` 才会试音。生成请求本身可能排队，超时用 `--timeout`（默认 360）控制；`--reuse-audio` 会复用旧音频，切换音色后不要带此参数。
- Edge TTS 免费、无需 key；Fish Audio 需要联网和额度，`s2.1-pro-free` 的可用性以服务方为准。
- 素材：使用 `data/characters` 里已经落盘的立绘。
- 渲染：本机 Remotion + Chrome。

`PEXELS_API_KEY`、`PIXABAY_API_KEY`、`FREESOUND_API_KEY`、`CARO_LLM_*` 只在接入 CaroCut 的原生素材检索/生图流程时才需要。

## CaroCut Web 界面（可选，当前未配置模型）

```sh
cd code/carocut
../../local/tools/node_modules/.bin/opencode serve --hostname 127.0.0.1 --port 4096
source .venv/bin/activate
PORT=3300 pnpm dev
```

该界面的五 Agent 流程需要先在 `opencode.json` 配置 provider/model；当前 `opencode auth list` 为 0 credentials，且配置里的 reviewer 模型已失效。本项目的主链不依赖它。

## 已知告警

- npm audit 有历史告警，未做强制升级；结果在 `local/logs/npm-audit.json`。
- 服务只绑定本机，不要暴露公网。
