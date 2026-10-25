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

## 三种镜头

**普通发言**：有台词，不写 `focus`。模板自动高亮说话人，其他人压暗，镜头由 `camera` 控制，默认静态。

**内心/聚光灯**：没有台词，写 `focus` 和 `monologue`。背景降饱和压暗，光落在 `focus` 角色身上，底部出现心理字幕。

**反应特写**：没有台词，写 `durationInFrames`，只放一个角色，`x: 0.5`、`height: 2.1`、`bottom: -1.15` 就是贴脸构图。prepare 会自动为这段静默留出时间，并把后面的台词整体后移。

```json
{
  "id": "C1",
  "scene": "game-dev-room",
  "durationInFrames": 24,
  "focus": "saiba-momoi",
  "characters": [
    { "id": "saiba-momoi", "outfit": "winter", "x": 0.5, "bottom": -1.15, "height": 2.1, "emotion": "shocked" }
  ],
  "lines": []
}
```

## 投票

投票镜头同样没有台词：写 `voteTags`，每个人身上显示自己投给谁。

```json
{
  "id": "VOTE",
  "durationInFrames": 90,
  "voteTags": [
    { "speaker": "saiba-momoi", "text": "凯伊" },
    { "speaker": "tendou-kei", "text": "小绿" }
  ],
  "characters": [],
  "lines": []
}
```

## 边界

- 词牌、心理字幕、投票字都按角色主题色和画幅高度计算，不依赖具体集数。
- `focus` 是内心/反应镜头的压暗，不是发言高亮；发言高亮由模板自动处理。
- 反应特写的高度和 `bottom` 是分镜声明，模板不硬编码某个角色。
- 需要气泡时仍按通用规则写 `bubbles`；没有登记 spine 的角色不能使用气泡。
