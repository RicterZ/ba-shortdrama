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
