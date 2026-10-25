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

## 分镜字段

| 字段 | 位置 | 作用 |
|---|---|---|
| `label` | 角色 | 头顶词牌：`{ text, tone: normal\|secret }` |
| `focus` | 镜头 | 聚光灯角色 id；只在没有台词的镜头生效 |
| `monologue` | 镜头 | 心理字幕：`{ speaker, text }` |
| `voteTags` | 镜头 | 人物身上的投票字：`[{ speaker, text }]` |
| `systemVoice` | 镜头 | 镜头开头的系统语音，例如“发言结束，开始投票”，不显示字幕 |
| `durationInFrames` | 镜头 | 无台词镜头的固定长度 |

投票、聚光灯、心理字幕是**分开的镜头**：投票镜头只有 `voteTags` 和 `systemVoice`；心理镜头才写 `focus` 和 `monologue`。

## 完整示例：西瓜和南瓜

小桃、小绿、优香的词是「西瓜」，凯伊是「南瓜」。

`S1` 发言；`S2` 投票，只有投票字和系统语音；`S3` 凯伊的聚光灯内心；`S4` 贴脸反应。

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
      "id": "S3",
      "scene": "game-dev-room",
      "camera": "static",
      "durationInFrames": 56,
      "focus": "tendou-kei",
      "monologue": { "speaker": "tendou-kei", "text": "……他们说的，好像不是南瓜。" },
      "characters": [
        { "id": "saiba-momoi", "outfit": "winter", "x": 0.10, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "saiba-midori", "outfit": "winter", "x": 0.33, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "hayase-yuuka", "outfit": "pajama", "x": 0.60, "bottom": -0.12, "height": 0.80, "emotion": "calm" },
        { "id": "tendou-kei", "outfit": "unarmed", "x": 0.90, "bottom": -0.12, "height": 0.84, "emotion": "blush" }
      ],
      "lines": []
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
  { "id": "L4", "speaker": "tendou-kei", "emotion": "default", "text": "……它是橙色的，里面也是橙色的。" }
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
- `focus` 是内心/反应镜头的压暗，不是发言高亮。
- 投票字按角色主题色和画幅高度计算。
- 需要气泡时仍按通用规则写 `bubbles`；没有登记 spine 的角色不能使用气泡。
