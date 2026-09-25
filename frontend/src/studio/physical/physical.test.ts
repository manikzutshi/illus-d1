import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, physicalIncluded, setIncludePhysical } from '../api';
import { initialState, reducer } from '../store';
import type { StudioState } from '../types';
import fixture from '../__fixtures__/alarm_physical_state.json';
import { boardHoles, fitDistance, localSize, nearestHole, rotateXY, rotY, snappedAnchor, toThree } from './coords';
import { findingsFor, highlightFor, physicalSummary, selectionForWire } from './trace';

const state = fixture as unknown as StudioState;
const phys = state.physical!;

describe('physical coordinates mirror the backend', () => {
  it('maps the board frame (z up) to three.js (y up) and rotates the same way', () => {
    expect(toThree([1, 2, 3])).toEqual([1, 3, 2]);
    expect(rotY(90)).toBeCloseTo(-Math.PI / 2);
    expect(rotateXY(1, 0, 90).map(v => v + 0)).toEqual([0, 1]);       // +x -> +y, as in physical/placement.rotate
    expect(rotateXY(1, 2, 180).map(v => v + 0)).toEqual([-1, -2]);
    expect(rotateXY(1, 0, 270).map(v => v + 0)).toEqual([0, -1]);
  });

  it('rebuilds every breadboard hole and matches every inserted pin position exactly', () => {
    const holes = boardHoles(phys.board!);
    expect(holes.length).toBe(400);                                     // half-size board: 400 tie points
    const byId = new Map(holes.map(h => [h.id, h]));
    let checked = 0;
    for (const part of phys.parts) {
      for (const pin of part.pins) {
        if (!pin.hole) continue;
        const h = byId.get(pin.hole)!;
        expect(h).toBeDefined();
        expect(h.x).toBeCloseTo(pin.position[0], 3);
        expect(h.y).toBeCloseTo(pin.position[1], 3);
        expect(h.node).toBe(pin.node);
        checked++;
      }
    }
    expect(checked).toBeGreaterThan(15);
  });

  it('snaps a dragged part to the hole under its first pin', () => {
    const holes = boardHoles(phys.board!);
    const q1 = phys.parts.find(p => p.instance_id === 'q1')!;
    const a = holes.find(h => h.id === q1.anchor)!;
    const next = holes.find(h => h.x > a.x + 2 && Math.abs(h.y - a.y) < 1e-6 && h.x - a.x < 3)!;
    expect(snappedAnchor(holes, q1, 2.4, 0.3)!.id).toBe(next.id);        // near one pitch -> next column
    expect(snappedAnchor(holes, q1, 0.4, 0.2)!.id).toBe(q1.anchor);      // small jitter stays put
    expect(nearestHole(holes, 1000, 1000)).toBeNull();                   // far off the board: no hole
  });

  it('uses the unrotated body size and fits the camera to the bounds', () => {
    const r2 = phys.parts.find(p => p.instance_id === 'r2')!;
    const s = localSize(r2);
    expect(s[0]).toBeGreaterThan(s[1]);                                  // length runs along the pin row
    expect(fitDistance([0, 0, 100, 60])).toBeGreaterThan(fitDistance([0, 0, 50, 30]));
  });
});

describe('engineering <-> physical traceability', () => {
  it('a selected component highlights its physical part', () => {
    const h = highlightFor({ kind: 'component', id: 'u2' }, phys);
    expect([...h.parts]).toEqual(['u2']);
  });

  it('a selected net highlights exactly its wires and pins', () => {
    const net = Object.values(phys.nets).find(n => n.wires.length > 0)!;
    const h = highlightFor({ kind: 'net', id: net.net_id }, phys);
    expect([...h.wires].sort()).toEqual([...net.wires].sort());
    expect([...h.pins].sort()).toEqual([...net.pins].sort());
    const w = phys.wires.find(x => x.net_id === net.net_id)!;
    expect(selectionForWire(w)).toEqual({ kind: 'net', id: net.net_id });
  });

  it('a selected pin highlights the net it is on', () => {
    const h = highlightFor({ kind: 'pin', id: 'u1.VOUT' }, phys);
    const net = phys.parts.find(p => p.instance_id === 'u1')!.pins.find(p => p.pin_id === 'VOUT')!.net_id!;
    expect(h.nets.has(net)).toBe(true);
    expect(h.pins.has('u2.IN1_P')).toBe(true);                           // the other end of the temperature signal
  });

  it('the inspector summary names the hole of every pin', () => {
    const s = physicalSummary(phys, 'u2')!;
    expect(s.pins.every(p => /^[a-j]\d+$/.test(p.where))).toBe(true);
    expect(physicalSummary(phys, 'nope')).toBeNull();
    expect(findingsFor(phys, 'bt1').some(f => f.code === 'P101')).toBe(true);   // stand-in USB supply is flagged
  });
});

describe('view switching and state', () => {
  it('refreshing with the physical build keeps the selection and the history', () => {
    const noPhys = { ...state, physical: null } as StudioState;
    let s = reducer(initialState, { type: 'loaded', studio: noPhys });
    s = reducer(s, { type: 'select', selection: { kind: 'component', id: 'u2' } });
    s = { ...s, undo: [noPhys.document] };
    s = reducer(s, { type: 'refreshed', studio: state });
    expect(s.selection).toEqual({ kind: 'component', id: 'u2' });
    expect(s.undo.length).toBe(1);
    expect(s.studio?.physical?.parts.length).toBe(phys.parts.length);
  });

  it('drops a selection whose part no longer exists', () => {
    let s = reducer(initialState, { type: 'loaded', studio: state });
    s = reducer(s, { type: 'select', selection: { kind: 'component', id: 'ghost' } });
    s = reducer(s, { type: 'refreshed', studio: state });
    expect(s.selection).toBeNull();
  });
});

describe('api asks for the physical build only once the 3D view is used', () => {
  afterEach(() => { setIncludePhysical(false); vi.unstubAllGlobals(); });

  it('adds physical: true to state and edit requests after the flag is set', async () => {
    const bodies: unknown[] = [];
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
      bodies.push(JSON.parse(String(init.body)));
      return new Response(JSON.stringify(state), { headers: { 'content-type': 'application/json' } });
    }));
    await api.state(state.document);
    expect(physicalIncluded()).toBe(false);
    setIncludePhysical(true);
    await api.state(state.document);
    await api.edit(state.document, [{ op: 'physical_rotate', instance_id: 'q1' }]);
    await api.openExample('temperature_alarm');
    expect((bodies[0] as { physical?: boolean }).physical).toBeUndefined();
    expect(bodies.slice(1).every(b => (b as { physical?: boolean }).physical === true)).toBe(true);
  });
});
