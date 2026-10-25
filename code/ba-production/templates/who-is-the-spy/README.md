# who-is-the-spy

《谁是卧底》二创用的渲染模板。和 `official` 共用场景、立绘、动作、气泡和转场，额外提供词牌、聚光灯、心理字幕、系统语音、大字幕和投票字。

## 集数配置

```yaml
template: who-is-the-spy
style:
  caption_style: meme
  font_family: Microsoft YaHei
```

`caption_style: meme` 会关掉游戏对话框和右上角 AUTO / MENU，改用底部大字幕。

## 玩法约定

- 平民一个词，卧底一个相近的词；卧底在“暴言”之前不知道自己身份。
- **发言**：每人一句关于自己词的线索，不能直接说出词；固定顺序，一人一轮。
- **对话**：追问、吐槽、接话，不占轮次；对话结束回到原发言顺序。
- **暴言**：卧底自认为正常、但让平民震惊的一句；之后接三连反应特写。
- **投票**：系统语音 + `voteTags`，得票最多者出局；投出卧底平民胜，否则卧底胜。
- **心理**：写在 `script.json`，用 `kind: "thought"` 标记，不占轮次。

`script.json` 放发言、对话和心理独白；投票、系统语音、反应镜头在 `storyboard.json` 里。

## 分镜字段

| 字段 | 位置 | 作用 |
|---|---|---|
| `label` | 角色 | 头顶词牌：`{ text, tone: normal\|secret }` |
| `focus` | 镜头 | 聚光灯角色 id；在 thought 行或没有台词的镜头生效 |
| `kind` | script 行 | `speech`（默认）或 `thought`；thought 只显示心理字幕、不显示底部字幕或说话人高亮 |
| `silent` | script 行 | `true` 时只显示字幕、不合成；thought 默认配音 |
| `voteTags` | 镜头 | 人物身上的投票字：`[{ speaker, text }]` |
| `systemVoice` | 镜头 | 镜头开头的系统语音，例如“发言结束，开始投票”，不显示字幕 |
| `durationInFrames` | 镜头 | 无台词镜头的固定长度 |

投票、聚光灯、心理字幕是**分开的镜头**：投票镜头只有 `voteTags` 和 `systemVoice`；心理镜头写 `focus` 和 `lines: ["M1"]`，独白文本只写在 script 中。

## BGM

常驻曲在 `episode.yaml` 的 `bgm` 里；震惊段用 `mute` 静音，`cues` 叠加替换曲：

```yaml
bgm:
  file: data/audio/bgm/0005-colorful-mess.ogg
  volume: 0.13
  mute:
    - { from: S3, to: C3 }
    - { from: S6, atLine: L21 }
  cues:
    - { from: S6, atLine: L21, file: data/audio/bgm/0007-unwelcome-school.ogg, volume: 0.5 }
```

`mute` 是硬静音，默认不做淡入淡出；`atLine` 可以把切点对齐到台词，`offsetFrames` 再往后延迟。`cues` 不会自动静音常驻 BGM，需要同时写 `mute`。

## 完整示例：西瓜和南瓜

小桃、小绿、优香的词是「西瓜」，凯伊是「南瓜」。

`S1` 发言；`S2` 投票，只有投票字和系统语音；`S3T` 凯伊的聚光灯内心；`S4` 贴脸反应。

```json
{
  "shots": [
    {
      "id": "S1",
      "scene": "game-dev-room",
      "camera": "static",
      "characters": [
        { "id": "saiba-momoi", "outfit": "winter", "x": 0.10, "bottom": -0.12, "height": 0.80, "emotion": "happy", "label": { "text": "西瓜", "tone": "normal" } },
        { "id": "saiba-midori", "outfit": "winter", "x": 0.33, "bottom": -0.12, "height": 0.80, "emotion": "calm", "label": { "text": "西瓜", "tone": "normal" } },
        { "id": "hayase-yuuka", "outfit": "pajama", "x": 0.60, "bottom": -0.12, "height": 0.80, "emotion": "calm", "label": { "text": "西瓜", "tone": "normal" } },
        { "id": "tendou-kei", "outfit": "unarmed", "x": 0.90, "bottom": -0.12, "height": 0.84, "emotion": "default", "label": { "text": "南瓜", "tone": "secret" } }
      ],
      "lines": ["L1", "L2", "L3", "L4"]
    },
    {
      "id": "S2",
      "scene": "game-dev-room",
      "camera": "static",
      "durationInFrames": 90,
      "systemVoice": "data/audio/system/vote.mp3",
      "voteTags": [
        { "speaker": "saiba-momoi", "text": "凯伊" },
        { "speaker": "saiba-midori", "text": "凯伊" },
        { "speaker": "hayase-yuuka", "text": "凯伊" },
        { "speaker": "tendou-kei", "text": "小桃" }
      ],
      "characters": [
        { "id": "saiba-momoi", "outfit": "winter", "x": 0.10, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "saiba-midori", "outfit": "winter", "x": 0.33, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "hayase-yuuka", "outfit": "pajama", "x": 0.60, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "tendou-kei", "outfit": "unarmed", "x": 0.90, "bottom": -0.12, "height": 0.84, "emotion": "blush" }
      ],
      "lines": []
    },
    {
      "id": "S3T",
      "scene": "game-dev-room",
      "camera": "static",
      "focus": "tendou-kei",
      "characters": [
        { "id": "saiba-momoi", "outfit": "winter", "x": 0.10, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "saiba-midori", "outfit": "winter", "x": 0.33, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "hayase-yuuka", "outfit": "pajama", "x": 0.60, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "tendou-kei", "outfit": "unarmed", "x": 0.90, "bottom": -0.12, "height": 0.84, "emotion": "blush" }
      ],
      "lines": ["M1"]
    },
    {
      "id": "S4",
      "scene": "game-dev-room",
      "camera": "static",
      "durationInFrames": 24,
      "focus": "tendou-kei",
      "characters": [
        { "id": "tendou-kei", "outfit": "unarmed", "x": 0.5, "bottom": -1.15, "height": 2.1, "emotion": "surprised" }
      ],
      "lines": []
    }
  ]
}
```

对应的 `script.json`：

```json
[
  { "id": "L1", "speaker": "saiba-momoi", "emotion": "happy", "text": "它是绿的，外面有条纹。" },
  { "id": "L2", "speaker": "saiba-midori", "emotion": "calm", "text": "切开里面是红的。" },
  { "id": "L3", "speaker": "hayase-yuuka", "emotion": "calm", "text": "夏天吃最解渴。" },
  { "id": "L4", "speaker": "tendou-kei", "emotion": "default", "text": "……它是橙色的，里面也是橙色的。" },
  { "id": "M1", "speaker": "tendou-kei", "kind": "thought", "emotion": "blush", "text": "……他们说的，好像不是南瓜。" }
]
```

## 系统语音

`systemVoice` 是镜头开始时播放的一段音频，不显示任何字幕。模板自带一个生成好的投票播报：

```sh
uv run python -c "import asyncio, edge_tts; asyncio.run(edge_tts.Communicate('发言结束，开始投票。', 'zh-CN-YunjianNeural', rate='-5%').save('data/audio/system/vote.mp3'))"
```

`data/` 不进版本库，换机器时要重新生成一次。

## 边界

- 无台词镜头由 prepare 自动留出静默时间，后面的台词整体后移。
- 开头连续的无台词镜头同样保留完整时长；末尾无台词镜头以声明时长结束，不额外追加 outro。转场 padding 另计。
- thought 和 speech 共用配音、覆盖检查、时间轴与 `--reuse-audio`，音频按 shot-line 命名，例如 `S3T-M1.mp3`，不用手写镜头时长。
- 旧 `shot.monologue` 已停用，prepare/validate 会提示迁移到 script 的 thought 行。
- `systemVoice` 的源路径相对工作区或本集目录，快照按镜头分别保存。
- `focus` 是内心/反应镜头的压暗，不是发言高亮。
- 投票字按角色主题色和画幅高度计算。
- 需要气泡时仍按通用规则写 `bubbles`；没有登记 spine 的角色不能使用气泡。
