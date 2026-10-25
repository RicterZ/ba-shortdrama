## BA character action presets

`code/ba-production/templates/character-actions.mjs` adapts the character action
parameters and fall timeline from **ba-archive/blue-archive**, contributed by
the ba-archive project contributors, under GNU AGPL version 3.

- Source: https://github.com/ba-archive/blue-archive
- Revision: `4ddc9ee241f6028d724346acda190155dc98aaf6`
- Files: `lib/ba-story-player/lib/layers/characterLayer/actionPlayer.ts` and
  `lib/ba-story-player/lib/layers/characterLayer/options/actionOptions.ts`
- License text: `licenses/ba-archive-AGPL-3.0.txt`
- Changes: replaced stateful Pixi/GSAP playback with deterministic frame sampling
  for Remotion; normalized translations to sprite dimensions; added timed cue
  replacement. Jump, greeting and shake curves are approximations, not an
  assertion of frame-exact game reproduction.

Retain this notice and the license when redistributing the adaptation. A release
incorporating this code must meet the applicable AGPL source-distribution and
network-use obligations; attribution alone is not sufficient. This notice does
not relicense unrelated third-party software or game assets. Blue Archive game
images, sounds and other content remain the property of their respective owners.

## Shy bubble

`code/ba-production/templates/bubbles.mjs` and the Shy rendering in
`templates/index.tsx` adapt `emotionPlayer.ts` and `options/emotionOptions.ts`
from the same pinned ba-archive revision under AGPL-3.0. Changes: frame-sampled
scale, two internal rotations, opacity; CSS layout for flat character sprites.
`fetch_bubbles.py` retrieves artwork from that revision and records provenance
locally; these game images and Kivo sound effects are not relicensed as AGPL.

## Expanded bubble presets

`bubble-presets.json` and `bubbleLayers` adapt the same revision's
`stores/index.ts` emotion resource mapping and `emotionPlayer.ts` timelines.
All 19 upstream-supported effects use their named image layers and approximate
frame curves, rather than copying the Pixi/GSAP runtime. Think has no handler in
that upstream revision: its thought-balloon entrance/hold is independently
implemented here using `Emoticon_Balloon_T.png`, not the Dot effect. Game-exact
Think content and timing have not been established.

Bubble placement now also uses the pinned `prepareEmotionContainer` equations
`(offset.x - 0.8) * 540` and `(offset.y - 1.2) * 1012`, and
`getRelativeScale`: base texture width is `options.scale * 540` reference units.
The flat-PNG adapter now reads actual Spine 4.2.33 export bounds for the
explicitly selected matching standing PNG, instead of assuming a centered
2024-unit plane. Local origin is (-bounds.x, bounds.y + bounds.height) in
image-down coordinates. Character art and bubbles share a transformed parent,
so translation, scaling, rotation, facing and visibility are inherited.
The per-preset offsets and scale values are taken from `emotionOptions.ts`.
Think still has no upstream parameters and retains explicitly custom settings.
## Bcut draft templates

`code/ba-production/scripts/bcut_templates/*.json` are copied from
LQH-A-A-O/dsh-bcut-edit, revision `8cbd464976aa8babe2c88312eb915e4a15e3680a`,
`home/skills/bcut-edit/templates`. Copyright (c) 2026 涟崎桦, MIT.
Source: https://github.com/LQH-A-A-O/dsh-bcut-edit
Full license: `licenses/dsh-bcut-edit-MIT.txt`.
The exporter uses the project's documented field structure; application
compatibility is experimental and is not endorsed by Bilibili.

