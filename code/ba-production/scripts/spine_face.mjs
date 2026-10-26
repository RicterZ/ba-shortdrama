// Print the setup-pose face centre of a BA standing Spine export, in skeleton units.
// BA standing skeletons carry the closed-eye overlay in an "eyeclose" slot; it sits
// on the face for every character, unlike any fixed offset from the root.
import fs from 'node:fs';
import * as spine from '@esotericsoftware/spine-core';

const file = process.argv[2];
const atlas = new spine.TextureAtlas(fs.readFileSync(file.replace(/\.skel$/, '.atlas'), 'utf8'));
class NullTexture extends spine.Texture {
  setFilters() {}
  setWraps() {}
  dispose() {}
}
for (const page of atlas.pages) page.setTexture(new NullTexture({width: page.width, height: page.height}));
const data = new spine.SkeletonBinary(new spine.AtlasAttachmentLoader(atlas))
  .readSkeletonData(new Uint8Array(fs.readFileSync(file)));
const skeleton = new spine.Skeleton(data);
skeleton.setToSetupPose();
skeleton.updateWorldTransform(spine.Physics.update);
const entries = data.defaultSkin.getAttachments();
const slotName = (item) => skeleton.slots[item.slotIndex].data.name;
// Exports name it "eyeclose" or "00_eyeclose". Otherwise use the expression slot:
// the one holding the most swappable face attachments.
let entry = entries.find((item) => /eyeclose/i.test(slotName(item)));
if (!entry) {
  const counts = new Map();
  for (const item of entries) counts.set(item.slotIndex, (counts.get(item.slotIndex) ?? 0) + 1);
  const [face, count] = [...counts].sort((a, b) => b[1] - a[1])[0] ?? [];
  if (!(count > 2)) throw new Error('Skeleton has no eyeclose or expression slot');
  entry = entries.find((item) => item.slotIndex === face);
}
const slot = skeleton.slots[entry.slotIndex];
const attachment = entry.attachment;
let vertices;
if (attachment instanceof spine.RegionAttachment) {
  vertices = new Float32Array(8);
  attachment.computeWorldVertices(slot, vertices, 0, 2);
} else if (attachment instanceof spine.MeshAttachment) {
  vertices = new Float32Array(attachment.worldVerticesLength);
  attachment.computeWorldVertices(slot, 0, attachment.worldVerticesLength, vertices, 0, 2);
} else {
  throw new Error('Unsupported eyeclose attachment');
}
const xs = vertices.filter((_, i) => i % 2 === 0);
const ys = vertices.filter((_, i) => i % 2 === 1);
process.stdout.write(JSON.stringify({
  x: (Math.min(...xs) + Math.max(...xs)) / 2,
  y: (Math.min(...ys) + Math.max(...ys)) / 2,
}) + '\n');
