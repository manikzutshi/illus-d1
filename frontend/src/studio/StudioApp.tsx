import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { useStudio } from './store';
import { Inspector } from './components/Inspector';
import { AssistantPanel, ExamplesPanel, ExplainPanel, LibraryPanel, ValidationPanel } from './components/Panels';
import { SchematicCanvas } from './components/SchematicCanvas';
import { FunctionPanel } from './components/FunctionPanel';
import './studio.css';

const PhysicalPreview = React.lazy(() => import('./components/PhysicalPreview'));

type LeftTab = 'assistant' | 'library' | 'examples';
type RightTab = 'inspect' | 'function' | 'validation' | 'explain';
type CenterTab = 'schematic' | 'physical';

class ErrorBoundary extends React.Component<{ children: React.ReactNode; fallback: string }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) { return { error: e.message }; }
  render() { return this.state.error ? <div className="empty">{this.props.fallback}: {this.state.error}</div> : this.props.children; }
}

function download(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function StudioApp() {
  const studio = useStudio();
  const { state, dispatch, applyOps, undo, redo } = studio;
  const [left, setLeft] = useState<LeftTab>('assistant');
  const [right, setRight] = useState<RightTab>('inspect');
  const [center, setCenter] = useState<CenterTab>('schematic');
  const [fitSignal, setFitSignal] = useState(0);
  const st = state.studio;

  // Open a starter design so the workspace is never blank.
  useEffect(() => { void studio.load(() => api.openExample('night_light_transistor')).then(() => setFitSignal(n => n + 1)); // eslint-disable-line
  }, []);

  useEffect(() => { if (state.selection) setRight('inspect'); }, [state.selection]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return;
      const sel = state.selection;
      const key = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && key === 'z') { e.preventDefault(); void (e.shiftKey ? redo() : undo()); return; }
      if ((e.ctrlKey || e.metaKey) && key === 'y') { e.preventDefault(); void redo(); return; }
      if (key === 'w') dispatch({ type: 'tool', tool: 'wire' });
      else if (key === 'v') dispatch({ type: 'tool', tool: 'select' });
      else if (key === 'escape') { dispatch({ type: 'wireStart', pin: null }); dispatch({ type: 'tool', tool: 'select' }); }
      else if (key === 'f') setFitSignal(n => n + 1);
      else if (key === 'r' && sel?.kind === 'component') void applyOps([{ op: 'rotate_component', instance_id: sel.id }]);
      else if (key === 'm' && sel?.kind === 'component') void applyOps([{ op: 'mirror_component', instance_id: sel.id }]);
      else if ((key === 'delete' || key === 'backspace') && sel) {
        if (sel.kind === 'component') void applyOps([{ op: 'remove_component', instance_id: sel.id }]);
        else if (sel.kind === 'net') void applyOps([{ op: 'delete_net', net_id: sel.id }]);
        else void applyOps([{ op: 'disconnect', pin: sel.id }]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [state.selection, applyOps, undo, redo, dispatch]);

  const v = st?.validation;
  const fs = st?.functional?.status;
  const badge = useMemo(() => {
    if (!v) return null;
    const warn = v.warnings.filter(w => w.code !== 'W002').length;
    return v.status === 'PASS'
      ? <span className="badge ok" onClick={() => setRight('validation')}>✓ valid{warn ? ` · ${warn} warning${warn > 1 ? 's' : ''}` : ''}</span>
      : <span className="badge bad" onClick={() => setRight('validation')}>✕ {v.errors.length} error{v.errors.length > 1 ? 's' : ''}</span>;
  }, [v]);
  const fbadge = !st?.functional?.intent_present ? null
    : <span className={`badge ${fs === 'PASS' ? 'ok' : fs === 'FAIL' ? 'bad' : 'warn'}`} onClick={() => setRight('function')}>
        {fs === 'PASS' ? '✓ function' : fs === 'FAIL' ? '✕ function' : fs === 'WARN' ? '⚠ function' : '? function'}</span>;

  return (
    <div className="studio">
      <header className="topbar">
        <div className="brand"><span className="logo">◆</span> Illustration Engine <span className="sub">Schematic Studio</span></div>
        <div className="docname">{st?.document.design.name ?? '—'}{badge}{fbadge}</div>
        <div className="tools">
          <div className="seg">
            <button className={state.tool === 'select' ? 'on' : ''} onClick={() => dispatch({ type: 'tool', tool: 'select' })} title="Select / move (V)">↖ Select</button>
            <button className={state.tool === 'wire' ? 'on' : ''} onClick={() => dispatch({ type: 'tool', tool: 'wire' })} title="Connect pins (W)">⌇ Wire</button>
          </div>
          <button onClick={() => void undo()} disabled={!state.undo.length} title="Undo (Ctrl+Z)">↶</button>
          <button onClick={() => void redo()} disabled={!state.redo.length} title="Redo (Ctrl+Y)">↷</button>
          <button onClick={() => setFitSignal(n => n + 1)} title="Fit to view (F)">⤢ Fit</button>
          <button disabled={!st} onClick={() => void applyOps([{ op: 'auto_arrange', keep_locked: false }]).then(() => setFitSignal(n => n + 1))} title="Re-run automatic layout">✦ Auto-arrange</button>
          <button disabled={!st} onClick={async () => st && download(`${st.document.design.project_id}.svg`, await api.exportSvg(st.document), 'image/svg+xml')}>Export SVG</button>
          <button disabled={!st} onClick={() => st && download(`${st.document.design.project_id}.design.json`, JSON.stringify(st.document.design, null, 2), 'application/json')}>Export IR</button>
        </div>
      </header>

      <aside className="left">
        <nav className="tabs">
          {(['assistant', 'library', 'examples'] as const).map(t => <button key={t} className={left === t ? 'on' : ''} onClick={() => setLeft(t)}>{t === 'assistant' ? 'AI Assistant' : t === 'library' ? 'Library' : 'Examples'}</button>)}
        </nav>
        <div className="panel">
          {left === 'assistant' && <AssistantPanel studio={studio} onGenerated={() => setFitSignal(n => n + 1)} />}
          {left === 'library' && <LibraryPanel studio={studio} />}
          {left === 'examples' && <ExamplesPanel studio={studio} onOpened={() => setFitSignal(n => n + 1)} />}
        </div>
      </aside>

      <main className="center">
        <nav className="tabs">
          <button className={center === 'schematic' ? 'on' : ''} onClick={() => setCenter('schematic')}>Schematic</button>
          <button className={center === 'physical' ? 'on' : ''} onClick={() => setCenter('physical')}>Physical preview (3D, experimental)</button>
          {state.tool === 'wire' && <span className="toolhint">{state.wireStart ? `Wiring from ${state.wireStart} - click the target pin (Esc to cancel)` : 'Wire tool: click a pin to start a connection'}</span>}
        </nav>
        <div className="stage">
          {!st && <div className="empty">{state.error ?? 'Loading…'}</div>}
          {st && center === 'schematic' && <SchematicCanvas studio={studio} fitSignal={fitSignal} />}
          {st && center === 'physical' && (
            <ErrorBoundary fallback="3D preview unavailable for this design">
              <Suspense fallback={<div className="empty">Loading 3D…</div>}>
                <PhysicalPreview design={st.document.design} selected={state.selection?.kind === 'component' ? state.selection.id : null}
                                 onSelect={id => dispatch({ type: 'select', selection: id ? { kind: 'component', id } : null })} />
              </Suspense>
            </ErrorBoundary>
          )}
          {state.busy && <div className="busy">updating…</div>}
        </div>
        <footer className="status">
          {state.error ? <span className="err-msg">⚠ {state.error} <button className="link" onClick={() => dispatch({ type: 'error', error: null })}>dismiss</button></span>
            : <span>{state.notice ?? 'Ready'}</span>}
          {st && <span className="right">{st.schematic.components.length} parts · {st.document.design.nets.length} nets · drawing {st.verification.ok ? 'matches netlist ✓' : 'MISMATCH ✕'}</span>}
        </footer>
      </main>

      <aside className="right">
        <nav className="tabs">
          {(['inspect', 'function', 'validation', 'explain'] as const).map(t => (
            <button key={t} className={right === t ? 'on' : ''} onClick={() => setRight(t)}>
              {t === 'inspect' ? 'Inspector' : t === 'function' ? `Function${fs === 'FAIL' ? ' ✕' : ''}`
                : t === 'validation' ? `Electrical${v && v.errors.length ? ` (${v.errors.length})` : ''}` : 'Explain'}
            </button>
          ))}
        </nav>
        <div className="panel">
          {right === 'inspect' && <Inspector studio={studio} />}
          {right === 'function' && <FunctionPanel studio={studio} />}
          {right === 'validation' && <ValidationPanel studio={studio} />}
          {right === 'explain' && <ExplainPanel studio={studio} />}
        </div>
      </aside>
    </div>
  );
}
