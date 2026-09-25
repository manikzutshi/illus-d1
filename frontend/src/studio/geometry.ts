// Mirror of src/schematic/geometry.py. The backend computes all placed pin positions;
// the UI only needs these transforms to render symbol graphics and upright text.
import type { Orient } from './types';

export const VEC: Record<Orient, [number, number]> = { left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] };

export function transformPoint(x: number, y: number, ox: number, oy: number, rotation = 0, mirror = false): [number, number] {
  let px = mirror ? -x : x;
  let py = y;
  switch (((rotation % 360) + 360) % 360) {
    case 90: [px, py] = [-py, px]; break;
    case 180: [px, py] = [-px, -py]; break;
    case 270: [px, py] = [py, -px]; break;
    default: break;
  }
  return [px + ox, py + oy];
}

/** Text anchor after a symbol transform, so symbol-internal text stays readable. */
export function uprightAnchor(anchor: 'start' | 'middle' | 'end', rotation: number, mirror: boolean): 'start' | 'middle' | 'end' {
  const [vx, vy] = transformPoint(1, 0, 0, 0, rotation, mirror);
  if (Math.abs(vy) > 0.5) return 'middle';
  if (vx < 0) return anchor === 'start' ? 'end' : anchor === 'end' ? 'start' : anchor;
  return anchor;
}

export function svgTransform(x: number, y: number, rotation: number, mirror: boolean): string {
  return `translate(${x} ${y}) rotate(${rotation}) scale(${mirror ? -1 : 1} 1)`;
}

export interface ViewBox { x: number; y: number; w: number; h: number }

export function fitView(bounds: number[], aspect: number, pad = 2): ViewBox {
  const [x0, y0, x1, y1] = bounds;
  let w = Math.max(x1 - x0 + 2 * pad, 10);
  let h = Math.max(y1 - y0 + 2 * pad, 10);
  if (w / h > aspect) h = w / aspect; else w = h * aspect;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  return { x: cx - w / 2, y: cy - h / 2, w, h };
}

/** Zoom the view by `factor` (<1 zooms in) keeping the world point (wx, wy) fixed under the cursor. */
export function zoomAt(v: ViewBox, factor: number, wx: number, wy: number): ViewBox {
  const w = Math.min(Math.max(v.w * factor, 8), 2000);
  const k = w / v.w;
  const h = v.h * k;
  return { x: wx - (wx - v.x) * k, y: wy - (wy - v.y) * k, w, h };
}

/** Centre of the schematic view the user currently sees (updated by the canvas). */
export const viewCenter = { x: 0, y: 0 };

/** Keep the zoom, move the view so the box is centred; widen it if the box does not fit. */
export function centerOn(v: ViewBox, box: number[], pad = 3): ViewBox {
  const [x0, y0, x1, y1] = box;
  const bw = x1 - x0 + 2 * pad, bh = y1 - y0 + 2 * pad;
  let { w, h } = v;
  if (bw > w || bh > h) { const k = Math.max(bw / w, bh / h); w *= k; h *= k; }
  return { x: (x0 + x1) / 2 - w / 2, y: (y0 + y1) / 2 - h / 2, w, h };
}

/** Zoom level relative to a reference (fitted) view, in percent. */
export function zoomPercent(v: ViewBox, fitted: ViewBox): number {
  return Math.round((fitted.w / v.w) * 100);
}
