// Coordinate helpers for the physical (3D) view. Pure functions - unit tested.
//
// Physical IR frame (backend, millimetres): x along the breadboard columns, y across the rows
// (row a at negative y), z up. three.js is Y-up, so a physical point (x, y, z) is drawn at
// (x, z, y), and a rotation of +θ about the physical z axis (x toward y) is a rotation of -θ
// about three's Y axis.
import type { BoardInfo, PhysicalPart, PhysicalProject, Selection, Vec3 } from '../types';

export const PITCH = 2.54;

export function toThree(p: Vec3 | number[]): [number, number, number] {
  return [p[0], p[2], p[1]];
}

export function rotY(deg: number): number {
  return (-deg * Math.PI) / 180;
}

/** Rotate a local (x, y) offset by the part rotation, in the physical frame. */
export function rotateXY(dx: number, dy: number, deg: number): [number, number] {
  const r = ((deg % 360) + 360) % 360;
  if (r === 90) return [-dy, dx];
  if (r === 180) return [-dx, -dy];
  if (r === 270) return [dy, -dx];
  return [dx, dy];
}

/** Body size in the part's own (unrotated) frame: [length along its pin row, depth, height]. */
export function localSize(part: PhysicalPart): Vec3 {
  const s = part.body?.size ?? [4, 4, 4];
  return part.rotation % 180 ? [s[1], s[0], s[2]] : [s[0], s[1], s[2]];
}

export interface HolePos { id: string; x: number; y: number; node: string; rail: boolean }

const RAIL_Y_STEPS: Record<string, number> = { 'T-': -9.5, 'T+': -8.5, 'B+': 8.5, 'B-': 9.5 };

/** Every hole of a board, rebuilt from BoardInfo (rows, columns and rail columns). */
export function boardHoles(board: BoardInfo): HolePos[] {
  const out: HolePos[] = [];
  board.column_x.forEach((x, i) => {
    const col = i + 1;
    for (const row of board.rows) {
      const node = `${'abcde'.includes(row) ? 'top' : 'bot'}:${col}`;
      out.push({ id: `${row}${col}`, x, y: board.row_y[row], node, rail: false });
    }
  });
  for (const r of board.rails) {
    for (const col of r.columns) {
      const x = board.column_x[col - 1];
      if (x === undefined) continue;
      out.push({ id: `${r.rail_id}${col}`, x, y: r.y ?? RAIL_Y_STEPS[r.rail_id] * PITCH, node: `rail:${r.rail_id}`, rail: true });
    }
  }
  return out;
}

export function nearestHole(holes: HolePos[], x: number, y: number, maxDist = PITCH): HolePos | null {
  let best: HolePos | null = null;
  let bd = Infinity;
  for (const h of holes) {
    const d = Math.hypot(h.x - x, h.y - y);
    if (d < bd) { bd = d; best = h; }
  }
  return best && bd <= maxDist ? best : null;
}

/** Where the first footprint site (the anchor) lands after dragging the part by (dx, dy) mm. */
export function snappedAnchor(holes: HolePos[], part: PhysicalPart, dx: number, dy: number): HolePos | null {
  if (!part.anchor) return null;
  const a = holes.find(h => h.id === part.anchor);
  if (!a) return null;
  return nearestHole(holes, a.x + dx, a.y + dy, PITCH * 0.75);
}

/** Axis-aligned bounds [minX, minY, maxX, maxY] -> camera distance that fits them. */
export function fitDistance(bounds: [number, number, number, number], fovDeg = 40): number {
  const w = Math.max(bounds[2] - bounds[0], 20);
  const h = Math.max(bounds[3] - bounds[1], 20);
  const r = Math.hypot(w, h) / 2;
  return (r / Math.tan(((fovDeg / 2) * Math.PI) / 180)) * 0.82;
}

export function boundsCenter(bounds: [number, number, number, number]): [number, number] {
  return [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2];
}

/**
 * Display path for a jumper: a smooth arch between the two IR endpoints (render-only; the IR path and
 * endpoints are the source of truth and are kept exactly at both ends). Leads from off-board terminals
 * and wires whose IR route had to climb over a body keep at least that height.
 */
export function wireArc(path: (Vec3 | number[])[], samples = 24): [number, number, number][] {
  if (path.length < 2) return path.map(p => [p[0], p[1], p[2]] as [number, number, number]);
  const a = path[0], b = path[path.length - 1];
  const span = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const irTop = Math.max(...path.map(p => p[2]));
  const apex = Math.max(Math.min(4 + span * 0.32, 38), irTop + 1, Math.max(a[2], b[2]) + 2);
  const out: [number, number, number][] = [[a[0], a[1], a[2]]];
  const lift = (t: number, z0: number, z1: number) => {
    // straight up out of the hole, a smooth arch, straight down into the other hole
    const base = z0 + (z1 - z0) * t;
    return base + (apex - Math.max(z0, z1)) * Math.sin(Math.PI * t) ** 0.8;
  };
  out.push([a[0], a[1], a[2] + Math.min(2.5, apex * 0.2)]);
  for (let i = 1; i < samples; i++) {
    const t = i / samples;
    out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, lift(t, a[2] + 2.5, b[2] + 2.5)]);
  }
  out.push([b[0], b[1], b[2] + Math.min(2.5, apex * 0.2)]);
  out.push([b[0], b[1], b[2]]);
  return out;
}

/** What the camera should look at for the current selection (physical frame), or null. */
export function focusTarget(phys: PhysicalProject | null | undefined, sel: Selection): { center: [number, number, number]; radius: number } | null {
  if (!phys || !sel) return null;
  const pts: number[][] = [];
  if (sel.kind === 'component' || sel.kind === 'pin') {
    const iid = sel.id.split('.')[0];
    const part = phys.parts.find(p => p.instance_id === iid);
    if (!part?.body) return null;
    const b = part.body;
    return { center: [b.center[0], b.center[1], b.center[2]], radius: Math.max(Math.hypot(b.size[0], b.size[1]) / 2, 8) };
  }
  const trace = phys.nets[sel.id];
  if (!trace) return null;
  for (const w of phys.wires.filter(w => w.net_id === sel.id)) pts.push(w.a.position, w.b.position);
  for (const ref of trace.pins) {
    const [iid, pin] = ref.split('.');
    const p = phys.parts.find(q => q.instance_id === iid)?.pins.find(q => q.pin_id === pin);
    if (p) pts.push(p.position);
  }
  if (!pts.length) return null;
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const c: [number, number, number] = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2, 0];
  return { center: c, radius: Math.max(Math.hypot(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) / 2, 10) };
}
