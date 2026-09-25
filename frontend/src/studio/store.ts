import { useCallback, useReducer, useRef } from 'react';
import { api, ApiError } from './api';
import type { EditOp, Highlight, Selection, StudioDocument, StudioState } from './types';

export type Tool = 'select' | 'wire';

export interface StoreState {
  studio: StudioState | null;
  undo: StudioDocument[];
  redo: StudioDocument[];
  selection: Selection;
  selectionSource: 'canvas' | 'panel';
  hoverNet: string | null;
  highlight: Highlight | null;
  tool: Tool;
  wireStart: string | null;
  busy: boolean;
  error: string | null;
  notice: string | null;
}

export const initialState: StoreState = {
  studio: null, undo: [], redo: [], selection: null, selectionSource: 'canvas', hoverNet: null, highlight: null, tool: 'select',
  wireStart: null, busy: false, error: null, notice: null,
};

export type Action =
  | { type: 'loaded'; studio: StudioState; notice?: string }
  | { type: 'refreshed'; studio: StudioState }
  | { type: 'edited'; studio: StudioState; previous: StudioDocument }
  | { type: 'undone'; studio: StudioState; current: StudioDocument }
  | { type: 'redone'; studio: StudioState; current: StudioDocument }
  | { type: 'select'; selection: Selection; source?: 'canvas' | 'panel' }
  | { type: 'hoverNet'; net: string | null }
  | { type: 'highlight'; highlight: Highlight | null }
  | { type: 'tool'; tool: Tool }
  | { type: 'wireStart'; pin: string | null }
  | { type: 'busy'; busy: boolean }
  | { type: 'error'; error: string | null }
  | { type: 'notice'; notice: string | null };

const HISTORY = 50;

/** Drop a selection that no longer refers to anything in the new state. */
function keepSelection(sel: Selection, studio: StudioState): Selection {
  if (!sel) return null;
  if (sel.kind === 'component') return studio.document.design.components.some(c => c.instance_id === sel.id) ? sel : null;
  if (sel.kind === 'net') return studio.schematic.nets[sel.id] ? sel : null;
  const [iid] = sel.id.split('.');
  return studio.document.design.components.some(c => c.instance_id === iid) ? sel : null;
}

export function reducer(s: StoreState, a: Action): StoreState {
  switch (a.type) {
    case 'loaded':
      return { ...s, studio: a.studio, undo: [], redo: [], selection: null, highlight: null, wireStart: null, busy: false, error: null, notice: a.notice ?? null };
    case 'refreshed':
      return { ...s, studio: a.studio, busy: false, error: null, selection: keepSelection(s.selection, a.studio) };
    case 'edited': {
      const msg = a.studio.op_results.map(r => r.message).join(' · ') || null;
      return { ...s, studio: a.studio, undo: [...s.undo, a.previous].slice(-HISTORY), redo: [], busy: false, error: null,
               notice: msg, selection: keepSelection(s.selection, a.studio), highlight: null, wireStart: null };
    }
    case 'undone':
      return { ...s, studio: a.studio, undo: s.undo.slice(0, -1), redo: [...s.redo, a.current], busy: false,
               selection: keepSelection(s.selection, a.studio), notice: 'Undone' };
    case 'redone':
      return { ...s, studio: a.studio, redo: s.redo.slice(0, -1), undo: [...s.undo, a.current], busy: false,
               selection: keepSelection(s.selection, a.studio), notice: 'Redone' };
    case 'select':
      return { ...s, selection: a.selection, selectionSource: a.source ?? 'canvas' };
    case 'hoverNet':
      return s.hoverNet === a.net ? s : { ...s, hoverNet: a.net };
    case 'highlight':
      return { ...s, highlight: a.highlight };
    case 'tool':
      return { ...s, tool: a.tool, wireStart: null };
    case 'wireStart':
      return { ...s, wireStart: a.pin };
    case 'busy':
      return { ...s, busy: a.busy };
    case 'error':
      return { ...s, error: a.error, busy: false };
    case 'notice':
      return { ...s, notice: a.notice };
    default:
      return s;
  }
}

function message(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return e instanceof Error ? e.message : String(e);
}

export function useStudio() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const ref = useRef(state);
  ref.current = state;

  const load = useCallback(async (fn: () => Promise<StudioState>, notice?: string) => {
    dispatch({ type: 'busy', busy: true });
    try {
      dispatch({ type: 'loaded', studio: await fn(), notice });
    } catch (e) {
      dispatch({ type: 'error', error: message(e) });
    }
  }, []);

  const applyOps = useCallback(async (ops: EditOp[]) => {
    const current = ref.current.studio;
    if (!current || ops.length === 0) return;
    dispatch({ type: 'busy', busy: true });
    try {
      const next = await api.edit(current.document, ops);
      dispatch({ type: 'edited', studio: next, previous: current.document });
    } catch (e) {
      dispatch({ type: 'error', error: message(e) });
    }
  }, []);

  const undo = useCallback(async () => {
    const s = ref.current;
    if (!s.studio || s.undo.length === 0) return;
    dispatch({ type: 'busy', busy: true });
    try {
      const prev = s.undo[s.undo.length - 1];
      dispatch({ type: 'undone', studio: await api.state(prev), current: s.studio.document });
    } catch (e) {
      dispatch({ type: 'error', error: message(e) });
    }
  }, []);

  const redo = useCallback(async () => {
    const s = ref.current;
    if (!s.studio || s.redo.length === 0) return;
    dispatch({ type: 'busy', busy: true });
    try {
      const next = s.redo[s.redo.length - 1];
      dispatch({ type: 'redone', studio: await api.state(next), current: s.studio.document });
    } catch (e) {
      dispatch({ type: 'error', error: message(e) });
    }
  }, []);

  /** Re-derive the state of the current document (e.g. to add the physical build) without touching history. */
  const refresh = useCallback(async () => {
    const current = ref.current.studio;
    if (!current) return;
    dispatch({ type: 'busy', busy: true });
    try {
      dispatch({ type: 'refreshed', studio: await api.state(current.document) });
    } catch (e) {
      dispatch({ type: 'error', error: message(e) });
    }
  }, []);

  return { state, dispatch, load, applyOps, undo, redo, refresh };
}

export type Studio = ReturnType<typeof useStudio>;
