import { describe, expect, it } from 'vitest';
import { fitView, transformPoint, uprightAnchor, zoomAt, VEC } from './geometry';
import { initialState, reducer } from './store';
import type { Orient, StudioState } from './types';
import fixture from './__fixtures__/pwm_state.json';

const state = fixture as unknown as StudioState;

describe('geometry mirrors the backend', () => {
  it('rotates clockwise on screen and mirrors before rotating', () => {
    const norm = (p: [number, number]) => p.map(v => v + 0);
    expect(norm(transformPoint(3, 0, 0, 0, 90))).toEqual([0, 3]);
    expect(transformPoint(3, 1, 10, 10, 0, true)).toEqual([7, 11]);
    expect(norm(transformPoint(1, 0, 0, 0, 180, true))).toEqual([1, 0]);
  });

  it('reproduces every backend pin position from symbol + placement', () => {
    const sch = state.schematic;
    let checked = 0;
    for (const c of sch.components) {
      const sym = sch.symbols[c.symbol_id];
      for (const p of c.pins.filter(q => !q.hidden)) {
        const sp = sym.pins.find(q => q.name === p.symbol_pin)!;
        const [x, y] = transformPoint(sp.x, sp.y, c.x, c.y, c.rotation, c.mirror);
        expect([Math.round(x), Math.round(y)]).toEqual([p.x, p.y]);
        // orientation agrees too
        const [vx, vy] = VEC[sp.orientation as Orient];
        const [tx, ty] = transformPoint(vx, vy, 0, 0, c.rotation, c.mirror);
        expect(VEC[p.orientation].map(Math.round)).toEqual([Math.round(tx), Math.round(ty)]);
        checked++;
      }
    }
    expect(checked).toBeGreaterThan(10);
  });

  it('keeps symbol text upright', () => {
    expect(uprightAnchor('start', 0, false)).toBe('start');
    expect(uprightAnchor('start', 180, false)).toBe('end');
    expect(uprightAnchor('start', 0, true)).toBe('end');
    expect(uprightAnchor('end', 90, false)).toBe('middle');
  });

  it('fits and zooms around a fixed point', () => {
    const v = fitView([0, 0, 40, 20], 2);
    expect(v.w / v.h).toBeCloseTo(2);
    const z = zoomAt(v, 0.5, 10, 5);
    expect(z.w).toBeCloseTo(v.w / 2);
    // the anchor point keeps its relative position
    expect((10 - z.x) / z.w).toBeCloseTo((10 - v.x) / v.w);
  });
});

describe('studio reducer', () => {
  const loaded = reducer(initialState, { type: 'loaded', studio: state });

  it('loads a design and clears history', () => {
    expect(loaded.studio?.document.design.project_id).toBe('pwm-motor');
    expect(loaded.undo).toEqual([]);
  });

  it('records undo history on edits and clears redo', () => {
    const edited = reducer({ ...loaded, redo: [state.document] }, {
      type: 'edited', previous: state.document,
      studio: { ...state, op_results: [{ op: 'move_component', kind: 'presentation', message: 'Moved r1' }] },
    });
    expect(edited.undo).toHaveLength(1);
    expect(edited.redo).toHaveLength(0);
    expect(edited.notice).toBe('Moved r1');
  });

  it('undo/redo move documents between stacks', () => {
    const withHistory = { ...loaded, undo: [state.document] };
    const undone = reducer(withHistory, { type: 'undone', studio: state, current: state.document });
    expect(undone.undo).toHaveLength(0);
    expect(undone.redo).toHaveLength(1);
    const redone = reducer(undone, { type: 'redone', studio: state, current: state.document });
    expect(redone.undo).toHaveLength(1);
    expect(redone.redo).toHaveLength(0);
  });

  it('drops selections that no longer exist after an edit', () => {
    const selected = reducer(loaded, { type: 'select', selection: { kind: 'component', id: 'r1' } });
    const without = { ...state, document: { ...state.document, design: { ...state.document.design,
      components: state.document.design.components.filter(c => c.instance_id !== 'r1') } }, op_results: [] };
    const after = reducer(selected, { type: 'edited', studio: without, previous: state.document });
    expect(after.selection).toBeNull();
    const keep = reducer(selected, { type: 'edited', studio: { ...state, op_results: [] }, previous: state.document });
    expect(keep.selection).toEqual({ kind: 'component', id: 'r1' });
  });

  it('switching tools cancels a pending wire', () => {
    const armed = reducer(loaded, { type: 'wireStart', pin: 'r1.PIN1' });
    expect(reducer(armed, { type: 'tool', tool: 'select' }).wireStart).toBeNull();
  });
});
