// Floating toolbar at the bottom of the canvas. Same place and grammar in both views; the
// controls that do not apply to a view are simply absent.
import type { Studio } from '../store';

export interface CanvasCmd { n: number; kind: 'fit' | 'zoomIn' | 'zoomOut' | 'locate' | 'view-iso' | 'view-top' | 'view-front' }

export function CanvasToolbar({ studio, view, zoom, labels, onLabels, send }: {
  studio: Studio; view: 'schematic' | 'physical'; zoom: number | null; labels: boolean;
  onLabels: (v: boolean) => void; send: (k: CanvasCmd['kind']) => void;
}) {
  const { state, dispatch, applyOps, undo, redo } = studio;
  const sel = state.selection;
  return (
    <div className="canvas-toolbar" role="toolbar" aria-label={`${view} tools`}>
      {view === 'schematic' && (
        <div className="grp">
          <button className={state.tool === 'select' ? 'on' : ''} onClick={() => dispatch({ type: 'tool', tool: 'select' })} title="Select / move (V)">↖</button>
          <button className={state.tool === 'wire' ? 'on' : ''} onClick={() => dispatch({ type: 'tool', tool: 'wire' })} title="Connect pins (W)">⌇</button>
        </div>
      )}
      <div className="grp">
        <button onClick={() => void undo()} disabled={!state.undo.length} title="Undo (Ctrl+Z)">↶</button>
        <button onClick={() => void redo()} disabled={!state.redo.length} title="Redo (Ctrl+Y)">↷</button>
      </div>
      {view === 'schematic' ? (
        <div className="grp">
          <button onClick={() => send('zoomOut')} title="Zoom out">−</button>
          <span className="zoom" title="Zoom (100% = whole design)">{zoom ?? 100}%</span>
          <button onClick={() => send('zoomIn')} title="Zoom in">+</button>
        </div>
      ) : (
        <div className="grp">
          <button onClick={() => send('view-iso')} title="3D view">3D</button>
          <button onClick={() => send('view-top')} title="Top view">Top</button>
          <button onClick={() => send('view-front')} title="Front view">Front</button>
        </div>
      )}
      <div className="grp">
        <button onClick={() => send('fit')} title="Fit to view (F)">⤢</button>
        <button onClick={() => send('locate')} disabled={!sel} title="Look at the selection (L)">◎</button>
      </div>
      {view === 'physical' && (
        <label className="toggle" title="Show part labels">
          <input type="checkbox" checked={labels} onChange={e => onLabels(e.target.checked)} /> Labels
        </label>
      )}
      <div className="grp">
        <button disabled={!state.studio} title={view === 'physical' ? 'Re-arrange the breadboard build' : 'Re-run the automatic schematic layout'}
                onClick={() => void applyOps([view === 'physical' ? { op: 'physical_auto_arrange', keep_locked: false } : { op: 'auto_arrange', keep_locked: false }]).then(() => send('fit'))}>
          ✦ Auto-arrange</button>
      </div>
    </div>
  );
}
