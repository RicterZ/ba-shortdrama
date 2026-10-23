# 剧情 UI 校准

短剧的剧情 UI 按 Blue Archive 实机剧情画面还原，含点击音与点击特效。本文记录参考来源、设计 token 和实现位置。

## 参考来源

- **kivo.wiki**：没有剧情 UI 截图或 UI 音效接口，因此 UI 样式按实机画面确认，音效取自 Blue Archive Wiki。
- **Blue Archive 实机剧情录屏**：对白、选择框、`AUTO`/`MENU` 和标题卡逐帧对照，参考帧分别来自：
  - 对白 + `AUTO`/`MENU`：实机剧情画面（16:9 之外的 2.08:1 录屏）；
  - 选择框：实机剧情选择画面；
  - 标题卡：Vol.1「Episode 1 / An Unexpected Alliance」章节标题。
- **Blue Archive Wiki**（<https://bluearchive.wiki/>）：官方游戏音效文件，`SE_Button_01.wav`、`SE_Confirm_01.wav`、`SE_Confirm_02.wav`。来源 URL 和处理方式在 `data/ui/manifest.json`。

> 实机画面只作为造型参考，没有把游戏截图打进成片；成片的背景、立绘和文字仍来自本项目的素材库和台本。

## 设计 token

尺寸以 1280×720 为基准；模板里用 `height` 比例写法，换分辨率时自动缩放。

### 对白（`DialogueBox`）

| 项目 | 值 |
| --- | --- |
| 底板 | 无面板；底部 42% 高度的黑色渐变压暗，底部 `rgba(4,10,17,.88)` → 68% 处透明 |
| 左右边距 | 9% |
| 姓名 | 白色，字重 700，`0.043 × height`，字距 1.5 |
| 社团 | 青色 `#7fd8ff`，字重 600，`0.036 × height`，与姓名同一基线，间距 `0.018 × height` |
| 分割线 | 姓名下方，1px 白色渐变，左右与文字对齐 |
| 台词 | 白色，`0.038 × height`，行高 1.55，字距 0.5，距顶 76% |
| 下一句指示 | 距底 7% 的右下角青色三角，`#6fe3ff`，宽 `0.026 × height`、高 `0.017 × height`，透明度呼吸闪烁 |

姓名行距底 27%，分割线距底 25%；正文从距顶 76% 起排，避免对白区过低。

### 选择（`ChoiceBox`）

| 项目 | 值 |
| --- | --- |
| 位置 | 2 项自顶部 28% 起；3 项自 22% 起，垂直排列 |
| 尺寸 | 宽 70%，高 9%，间距 3.5% |
| 形状 | 浅蓝白色的细长平行四边形，顶边相对底边右移约 10°（CSS `skewX(-10deg)`）；不使用圆角胶囊形或放大选中态 |
| 表面 | 中央浅色、两侧浅蓝，叠加低对比度三角切面 |
| 文字 | 深蓝灰居中，字重 400，字号 `0.040 × height` |
| 出现 | 逐项上移 + 淡入，约 14 帧 |
| 确认 | 选中条左端触发点击特效，并播放 `select.wav` |

### 按钮与常驻 UI（`StoryChrome` / `BAButton`）

| 项目 | 值 |
| --- | --- |
| `AUTO` | 黄色渐变 `#ffe874 → #ffd21f`，深色斜体文字，黄色外发光表示激活 |
| `MENU` | 米白渐变 `#fdfcf9 → #ece9e2`，深色斜体文字 |
| 形状 | `skewX(-9deg)` 的圆角矩形，文字反向 `skewX(9deg)` |
| 尺寸 | 宽 `0.108 × height`、高 `0.042 × height`，右上角距顶 2.4%、距右 4% |
| 自定义按钮 | `BAButton`，`variant: primary / secondary`，支持 `x` / `y` / `width` / `pressFrame` |
| 按下 | 弹簧缩放到 0.93 再回弹，外圈闪白/黄光，播放 `click.wav` |

### 标题卡（`Intro`）

| 项目 | 值 |
| --- | --- |
| 背景 | 首个镜头画面，模糊 3px、压暗；再叠一层深色渐变 |
| 标题带 | 全宽，距顶 38%，高 24%，浅蓝渐变 `#f3fafe → #c4daea`，叠加 4 块斜切面 |
| 小标签 | `Episode 1`，`0.032 × height`，深蓝 `#2d4a6b`，字距 2.5，黄色下划线 `#ffd84d` |
| 主标题 | 深蓝 `#2d4a6b`，`0.065 × height`，字重 800，字距 2 |
| 入场 | 标题带与文字原位淡入，不做横向展开、位移或弹簧动画 |
| 退场 | 结束前 14 帧整体淡出 |

### 点击特效（`ClickBurst`）

- 16 帧生命周期，从按点向外扩散。
- 虚线圆环半径 12 → 70px，旋转；内圈白色细环；中心白色闪光。
- 10 颗菱形火花（青色/白色交替）向外飞出。
- 按钮点击使用按钮中心为原点；选项确认使用选中条左端为原点，避免遮住文字。

## 音效

| 文件 | 触发 | 原始文件 | 音量 |
| --- | --- | --- | --- |
| `data/ui/sfx/click.wav` | 每句台词开始、按钮按下、标题卡出现 | `SE_Button_01.wav` | 台词 0.14 / 按钮 0.55 / 标题 0.30 |
| `data/ui/sfx/select.wav` | 选项确认 | `SE_Confirm_01.wav` | 0.65 |
| `data/ui/sfx/hover.wav` | 选项列表出现 | `SE_Confirm_02.wav` | 0.28 |

`prepare.py` 会把这三个文件复制到 `<episode>/raws/audio/ui/`，并把相对路径写进 `scene.json` 的 `ui.sfx`。`episode.yaml` 的 `ui` 块可选：

```json
"ui": {
  "kit": "blue-archive",
  "sfx": { "click": "click", "select": "select", "hover": "hover" },
  "lineClick": true,
  "lineClickVolume": 0.14
}
```

版权归 NEXON Games / Yostar；公开或商用前必须核实授权，详见 `data/ui/manifest.json` 的 `rights`。

## 实现位置

- `code/ba-production/templates/index.tsx`：`DialogueBox`、`ChoiceBox`、`Intro`、`StoryChrome`、`BAButton`、`ClickBurst`、`ShotView`、`BAEpisode`。
- `code/ba-production/scripts/prepare.py`：复制 UI 音效、写 `ui` 块、角色 `club`/`school`、按钮和选择时间字段校验。
- `code/ba-production/scripts/validate.py`：UI 音效存在性、`choices` 时间字段、`buttons` 范围。
- `code/ba-production/schemas/storyboard.json`：`choices.fromFrame/selectFrame/hideFrame`、`buttons`。
- `code/ba-production/schemas/episode.json`：`ui` 块。
- `videos/900-ui-kit/`：集中展示所有 UI 元素的 21 秒样片。

## 已知限制

- 参考录屏是 2.08:1，本片是 16:9；对白的纵向位置按 16:9 安全区做了微调，不是逐像素复刻。
- 字体使用系统 `PingFang SC` + `Arial`/`Helvetica`；没有打包游戏原字体。
- `AUTO` 目前只是状态展示，没有自动播放逻辑；`MENU` 没有菜单面板。两者作为「其他按钮」的样式样本。
- 按钮和选项的出现/消失是镜头内相对帧，需要和台词时长对齐；`prepare.py` 会拒绝越界帧。
