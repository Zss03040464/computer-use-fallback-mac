import fs from 'node:fs';
import path from 'node:path';

const root = path.dirname(new URL(import.meta.url).pathname);
const overlayPath = path.join(root, 'runtime', 'virtual_cursor_overlay.py');
const managerPath = path.join(root, 'runtime', 'cu_runtime', 'overlay.py');
const feedbackPath = path.join(root, 'runtime', 'cu_runtime', 'cursor_feedback.py');

const overlay = fs.readFileSync(overlayPath, 'utf8');
const manager = fs.readFileSync(managerPath, 'utf8');
const feedback = fs.readFileSync(feedbackPath, 'utf8');

function numberConstant(source, name) {
  const match = source.match(new RegExp(`^${name}\\s*=\\s*([0-9]+)`, 'm'));
  if (!match) {
    throw new Error(`Missing ${name} in overlay script`);
  }
  return Number(match[1]);
}

const width = numberConstant(overlay, 'WINDOW_WIDTH');
const height = numberConstant(overlay, 'WINDOW_HEIGHT');

if (width > 40 || height > 40) {
  throw new Error(`Live cursor overlay is too large: ${width}x${height}`);
}

const hotspotX = numberConstant(overlay, 'HOTSPOT_X');
const hotspotY = numberConstant(overlay, 'HOTSPOT_Y');
if (hotspotX > 10 || hotspotY > 10) {
  throw new Error(`Cursor hotspot is too padded for native-size cursor: ${hotspotX},${hotspotY}`);
}

const coreWidth = numberConstant(feedback, 'CURSOR_CORE_WIDTH');
const coreHeight = numberConstant(feedback, 'CURSOR_CORE_HEIGHT');
if (coreWidth > 15 || coreHeight > 20) {
  throw new Error(`Cursor core exceeds physical-pointer scale: ${coreWidth}x${coreHeight}`);
}

if (!feedback.includes('aqua-glass-arrow-v2')) {
  throw new Error('Cursor must use the V2 repository-owned style contract');
}

if (overlay.includes('fallback-native-cyan-arrow')) {
  throw new Error('Production renderers must not retain the obsolete cyan cursor identity');
}

if (!overlay.includes('from cu_runtime.cursor_feedback import')) {
  throw new Error('Live overlay must consume the shared cursor feedback model');
}

if (!overlay.includes('cursor_visual(') || !overlay.includes('pulse_strength')) {
  throw new Error('Live overlay must render the persisted cursor feedback phase');
}

if (!feedback.includes('(12.4, 9.4)') || feedback.includes('(12, 9)')) {
  throw new Error('Cursor shape must use the original V2 clipped-tail geometry');
}

if (overlay.includes('bezierPathWithOvalInRect_') || feedback.includes('.ellipse(')) {
  throw new Error('Cursor must not render the old accent dot or a hard pulse ring');
}

if (!overlay.includes('CURSOR_FILL_RGBA') || !overlay.includes('CURSOR_AQUA_RGBA')) {
  throw new Error('Live overlay must consume the shared translucent white and aqua palette');
}

if (!overlay.includes('setLineJoinStyle_') || !overlay.includes('setLineCapStyle_')) {
  throw new Error('Live overlay must use rounded vector joins and caps');
}

if (!overlay.includes('setIgnoresMouseEvents_(True)')) {
  throw new Error('Live cursor overlay must remain click-through');
}

if (!overlay.includes('NSPanel') || !overlay.includes('NSWindowStyleMaskNonactivatingPanel')) {
  throw new Error('Live cursor overlay must use a nonactivating AppKit panel');
}

if (!overlay.includes('NSApplicationActivationPolicyProhibited') || overlay.includes('NSApplicationActivationPolicyAccessory')) {
  throw new Error('Overlay process must be prohibited from becoming the active application');
}

if (!overlay.includes('orderFront_(None)') || overlay.includes('orderFrontRegardless()')) {
  throw new Error('Nonactivating overlay must order its panel without overriding the current frontmost application');
}

if (overlay.includes('NSScreen.mainScreen()') || !overlay.includes('frame_origin_for_point')) {
  throw new Error('Live cursor overlay must map Quartz points from the primary AppKit screen origin');
}

if (!overlay.includes('--owner-pid') || !overlay.includes('process_is_running')) {
  throw new Error('Detached live cursor overlay must exit when its owner worker exits');
}

if (!manager.includes('"--owner-pid"') || !manager.includes('str(os.getpid())')) {
  throw new Error('Session overlay manager must pass its persistent worker PID to the overlay process');
}

if (!overlay.includes('orderOut_') || !overlay.includes('state is None')) {
  throw new Error('Malformed or missing cursor state must hide the live overlay');
}

if (!feedback.includes('base.alpha_composite(visible, dest=(left, top))') || !feedback.includes('render_cursor_patch(scale, pulse)')) {
  throw new Error('Screenshot cursor feedback must use compact bounded compositor layers');
}

console.log('Overlay style guard: PASS');
