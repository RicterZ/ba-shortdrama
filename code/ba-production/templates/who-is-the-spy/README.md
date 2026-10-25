# who-is-the-spy

《谁是卧底》二创用的渲染模板。和 `official` 共用场景、立绘、动作、气泡和转场，额外提供词牌、聚光灯、心理字幕、大字幕和投票字。

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
| `label` | 角色 | 头顶词牌：`{ text, tone: normal\|secret, rotate }` |
| `focus` | 镜头 | 聚光灯角色 id；只在没有台词的镜头生效 |
| `monologue` | 镜头 | 心理字幕：`{ speaker, text }`；镜头没有台词时整段显示 |
| `voteTags` | 镜头 | 人物身上的投票字：`[{ speaker, text }]` |
| `durationInFrames` | 镜头 | 无台词反应镜头的固定长度 |

## 完整示例：西瓜和南瓜

四个人的词：小桃、小绿、优香是「西瓜」，凯伊是「南瓜」。

`S1` 正常发言；`S2` 没有台词，同时打开聚光灯、心理字幕和投票字；`S3` 是凯伊的贴脸反应特写。

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
      "focus": "tendou-kei",
      "monologue": { "speaker": "tendou-kei", "text": "……他们说的，好像不是南瓜。" },
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

## 三种镜头

- **普通发言**：有台词，不写 `focus`。模板自动高亮说话人，其他人压暗。
- **聚光灯/心理**：没有台词，写 `focus` 和 `monologue`。背景压暗，光落在 `focus` 角色上，底部出现心理字幕；同时可以叠 `voteTags`。
- **贴脸反应**：没有台词，写 `durationInFrames`，只放一个角色，`x: 0.5`、`height: 2.1`、`bottom: -1.15`。

无台词镜头由 prepare 自动留出静默时间，后面的台词整体后移，不需要手写帧号。
