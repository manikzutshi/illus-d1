import { describe, expect, it } from 'vitest';
import type { JobInfo, LibraryItem, StudioState } from '../types';
import physFixture from '../__fixtures__/alarm_physical_state.json';
import { checkCards, issuesForPart, overallTone } from './checks';
import { jobHeadline, jobPhases, phaseOf } from './jobPhases';
import { categoryLabel, groupLibrary, searchLibrary } from './library';
import { focusTarget, wireArc } from '../physical/coords';
import { centerOn, fitView, zoomPercent } from '../geometry';

const state = physFixture as unknown as StudioState;

// A real event sequence as emitted by src/studio/service.py::summarize_event.
const EVENTS = [
  { t: 0, event: 'USER_PROMPT', message: 'Reading the request' },
  { t: 1, event: 'REQUIREMENTS_EXTRACTED', message: 'Understood intent: adjustable temperature alarm' },
  { t: 1, event: 'FUNCTIONAL_INTENT', message: 'Required behaviour: alarm on when temp above' },
  { t: 2, event: 'TOOL_CALL', message: 'Using tool browse_library' },
  { t: 3, event: 'TOOL_CALL', message: 'Searching the component library for “comparator”' },
  { t: 4, event: 'TOOL_CALL', message: 'Calculating led_resistor' },
  { t: 5, event: 'FUNCTIONAL_RESULT', message: 'Functional check → FAIL: F004 bz1 is not driven' },
  { t: 5, event: 'TOOL_CALL', message: 'Checking a draft design with the deterministic validator → PASS electrically, functional FAIL' },
  { t: 6, event: 'PROPOSAL_REQUESTED', message: 'Repairing the design (attempt 1)' },
  { t: 7, event: 'PROPOSED_DESIGN', message: 'Draft design proposed: 8 parts, 7 nets' },
  { t: 8, event: 'VALIDATION_RESULT', message: 'Validation PASS' },
];

function job(status: JobInfo['status'], events = EVENTS, result?: StudioState): JobInfo {
  return { job_id: 'j', status, prompt: 'alarm', events, trace_summary: {}, elapsed_s: 9, result };
}

describe('AI job phases come from real events', () => {
  it('maps each event kind to its phase', () => {
    expect(phaseOf(EVENTS[1])).toBe('understand');
    expect(phaseOf(EVENTS[4])).toBe('library');
    expect(phaseOf(EVENTS[5])).toBe('calculate');
    expect(phaseOf(EVENTS[7])).toBe('validate');
    expect(phaseOf(EVENTS[8])).toBe('repair');
    expect(phaseOf(EVENTS[9])).toBe('draft');
  });

  it('while running, the latest phase is active and earlier ones are done', () => {
    const ph = jobPhases(job('running', EVENTS.slice(0, 5)));
    const by = Object.fromEntries(ph.map(p => [p.id, p]));
    expect(by.understand.state).toBe('done');
    expect(by.understand.detail).toContain('temperature alarm');
    expect(by.library.state).toBe('active');
    expect(by.library.detail).toBe('2 lookups');
    expect(by.schematic.state).toBe('pending');
  });

  it('when done, schematic and physical verdicts come from the deterministic result, not the AI', () => {
    const ph = jobPhases(job('done', EVENTS, state));
    const by = Object.fromEntries(ph.map(p => [p.id, p]));
    expect(by.repair.state).toBe('done');
    expect(by.validate.detail).toContain('electrical PASS');
    expect(by.schematic.state).toBe(state.verification.ok ? 'done' : 'failed');
    expect(by.physical.state).toBe(state.physical!.verification!.ok ? 'done' : 'failed');
    expect(by.physical.detail).toContain('build matches');
    expect(jobHeadline(job('done', EVENTS, state))).toBe('Design built and verified');
  });

  it('a failed job marks where it stopped', () => {
    const ph = jobPhases(job('failed', EVENTS.slice(0, 8)));
    expect(ph.find(p => p.id === 'validate')!.state).toBe('failed');
    expect(ph.find(p => p.id === 'physical')!.state).toBe('pending');
  });
});

const item = (id: string, name: string, category: string, extra: Partial<LibraryItem> = {}): LibraryItem => ({
  id, name, short_name: null, category, object_type: 'PHYSICAL', family: null, tags: [], aliases: [], description: '',
  pin_count: 2, symbol: { symbol_id: 's', kind: 'part', graphics: [], pins: [], body: [0, 0, 0, 0], description: '' }, ...extra,
});

describe('library search and grouping scale with the registry', () => {
  const items = [
    item('a', 'NPN transistor', 'SEMICONDUCTOR', { aliases: ['bjt'], short_name: 'BC547' }),
    item('b', 'N-channel MOSFET', 'SEMICONDUCTOR', { tags: ['switch'] }),
    item('c', 'Ideal AND gate', 'LOGIC', { object_type: 'DIGITAL_PRIMITIVE' }),
    item('d', 'Gas sensor', 'SENSOR', { description: 'detects smoke' }),
    item('e', 'Quantum widget', 'FUTURE_CATEGORY'),
  ];
  it('matches names, aliases, tags and descriptions, name matches first', () => {
    expect(searchLibrary(items, 'bjt').map(i => i.id)).toEqual(['a']);
    expect(searchLibrary(items, 'smoke').map(i => i.id)).toEqual(['d']);
    expect(searchLibrary(items, 'switch').map(i => i.id)).toEqual(['b']);
    expect(searchLibrary(items, 'transistor semiconductor').map(i => i.id)).toEqual(['a']);
  });
  it('filters real parts vs idealised primitives', () => {
    expect(searchLibrary(items, '', 'ideal').map(i => i.id)).toEqual(['c']);
    expect(searchLibrary(items, '', 'physical').length).toBe(4);
  });
  it('groups by category in a stable order and labels unknown categories', () => {
    const g = groupLibrary(items);
    expect(g[0].category).toBe('SENSOR');
    expect(g.map(x => x.category)).toContain('FUTURE_CATEGORY');
    expect(categoryLabel('FUTURE_CATEGORY')).toBe('Future category');
    expect(g.reduce((n, x) => n + x.items.length, 0)).toBe(items.length);
  });
});

describe('checks summary', () => {
  it('summarises the three deterministic checks', () => {
    const cards = checkCards(state);
    expect(cards.map(c => c.id)).toEqual(['electrical', 'function', 'physical']);
    expect(cards[0].tone).toBe(state.validation.status === 'PASS' ? (state.validation.warnings.some(w => w.code !== 'W002') ? 'warn' : 'ok') : 'bad');
    expect(cards[2].verdict).toBe('Build matches netlist');
    expect(overallTone(cards)).not.toBe('bad');
  });
  it('collects what every check says about one part', () => {
    const issues = issuesForPart(state, 'bt1');
    expect(issues.some(i => i.source === 'Physical' && i.code === 'P101')).toBe(true);
    expect(issuesForPart(state, 'nope')).toEqual([]);
  });
  it('a design without a physical build says so instead of guessing', () => {
    const cards = checkCards({ ...state, physical: null } as StudioState);
    expect(cards[2].tone).toBe('neutral');
  });
});

describe('3D wire arcs and focus', () => {
  it('the rendered arch keeps both IR endpoints exactly and rises above the board', () => {
    for (const w of state.physical!.wires) {
      const arc = wireArc(w.path);
      expect(arc[0]).toEqual([w.path[0][0], w.path[0][1], w.path[0][2]]);
      const last = w.path[w.path.length - 1];
      expect(arc[arc.length - 1]).toEqual([last[0], last[1], last[2]]);
      expect(Math.max(...arc.map(p => p[2]))).toBeGreaterThanOrEqual(Math.max(...w.path.map(p => p[2])));
    }
  });
  it('focus targets the selected part or the whole net', () => {
    const q1 = focusTarget(state.physical, { kind: 'component', id: 'q1' })!;
    const body = state.physical!.parts.find(p => p.instance_id === 'q1')!.body!;
    expect(q1.center).toEqual(body.center);
    const net = Object.values(state.physical!.nets).find(n => n.wires.length > 0)!;
    expect(focusTarget(state.physical, { kind: 'net', id: net.net_id })!.radius).toBeGreaterThan(0);
    expect(focusTarget(state.physical, null)).toBeNull();
  });
});

describe('schematic locate keeps the zoom', () => {
  it('centres a box without zooming unless it does not fit', () => {
    const v = { x: 0, y: 0, w: 40, h: 25 };
    const c = centerOn(v, [100, 100, 104, 102]);
    expect(c.w).toBe(40);
    expect(c.x + c.w / 2).toBe(102);
    expect(centerOn(v, [0, 0, 200, 10]).w).toBeGreaterThan(40);
    expect(zoomPercent(fitView([0, 0, 50, 30], 1.6), fitView([0, 0, 50, 30], 1.6))).toBe(100);
  });
});

describe('selection source decides whether the Inspector opens', () => {
  it('canvas selections are the default; panel selections are marked', async () => {
    const { initialState, reducer } = await import('../store');
    let s = reducer(initialState, { type: 'select', selection: { kind: 'component', id: 'q1' } });
    expect(s.selectionSource).toBe('canvas');
    s = reducer(s, { type: 'select', selection: { kind: 'net', id: 'gnd' }, source: 'panel' });
    expect(s.selectionSource).toBe('panel');
    expect(s.selection).toEqual({ kind: 'net', id: 'gnd' });
  });
});
