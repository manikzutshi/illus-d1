import React, { Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { api, setIncludePhysical } from './api';
import { useStudio } from './store';
import { Inspector } from './components/Inspector';
import { ExamplesPanel, ExplainPanel } from './components/Panels';
import { LibraryPanel } from './components/LibraryPanel';
import { AssistantPanel } from './components/AssistantPanel';
import { ChecksPanel, type CheckTab } from './components/ChecksPanel';
import { SchematicCanvas } from './components/SchematicCanvas';
import { AssemblyPanel } from './components/AssemblyPanel';
import { CanvasToolbar, type CanvasCmd } from './components/CanvasToolbar';
import { checkCards } from './ui/checks';
import './studio.css';

// The 3D view (three.js) is its own chunk: loaded only when the Physical 3D view is opened.
const PhysicalView = React.lazy(() => import('./physical/PhysicalView'));

type LeftTab = 'library' | 'blocks' | 'examples';
type RightTab = 'assistant' | 'inspect' | 'checks' | 'build' | 'explain';
export type CenterView = 'schematic' | 'physical';

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

function ExportMenu({ onSvg, onIr, onBuild, canBuild }: { onSvg: () => void; onIr: () => void; onBuild: () => void; canBuild: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, []);
  return (
    <div className="menu" ref={ref}>
      <button className="ghost" onClick={() => setOpen(o => !o)} aria-haspopup="menu">Export ▾</button>
      {open && (
        <div className="menu-pop" role="menu">
          <button onClick={() => { setOpen(false); onSvg(); }}>Schematic (SVG)</button>
          <button onClick={() => { setOpen(false); onIr(); }}>Engineering design (JSON)</button>
          <button disabled={!canBuild} onClick={() => { setOpen(false); onBuild(); }}>Physical build (JSON)</button>
        </div>
      )}
    </div>
  );
}

export default function StudioApp() {
  const studio = useStudio();
  const { state, dispatch, applyOps, undo, redo } = studio;
  const [left, setLeft] = useState<LeftTab>('library');
  const [right, setRight] = useState<RightTab>('assistant');
  const [checkTab, setCheckTab] = useState<CheckTab>('electrical');
  const [center, setCenter] = useState<CenterView>('schematic');
  const [fitSignal, setFitSignal] = useState(0);
  const [cmd, setCmd] = useState<CanvasCmd>({ n: 0, kind: 'fit' });
  const [zoom, setZoom] = useState<number | null>(null);
  const [labels, setLabels] = useState(true);
  const st = state.studio;

  // Open a starter design so the workspace is never blank.
  useEffect(() => { void studio.load(() => api.openExample('night_light_transistor')).then(() => setFitSignal(n => n + 1)); // eslint-disable-line
  }, []);

  // Selecting on a canvas shows it in the Inspector; selecting from a list (assembly steps, checks,
  // explanation) keeps that list open. Never while the AI is mid-generation.
  const genRunning = useRef(false);
  const rightRef = useRef(right);
  rightRef.current = right;
  useEffect(() => {
    if (state.selection && !genRunning.current && (state.selectionSource === 'canvas' || rightRef.current === 'assistant')) setRight('inspect');
  }, [state.selection, state.selectionSource]);

  const send = (kind: CanvasCmd['kind']) => setCmd(c => ({ n: c.n + 1, kind }));

  // Switching views keeps the selection and looks at it: one design, two views.
  const openView = (view: CenterView) => {
    setCenter(view);
    if (view === 'physical') {
      setIncludePhysical(true);                      // from now on every state includes the build
      if (st && !st.physical) void studio.refresh();
    }
    if (state.selection) setTimeout(() => send('locate'), 60);
  };
  const locate = (view: CenterView) => {
    if (view !== center) openView(view);
    else send('locate');
  };
  const openCheck = (tab: CheckTab) => { setCheckTab(tab); setRight('checks'); };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) return;
      const sel = state.selection;
      const key = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && key === 'z') { e.preventDefault(); void (e.shiftKey ? redo() : undo()); return; }
      if ((e.ctrlKey || e.metaKey) && key === 'y') { e.preventDefault(); void redo(); return; }
      if (key === 'w' && center === 'schematic') dispatch({ type: 'tool', tool: 'wire' });
      else if (key === 'v') dispatch({ type: 'tool', tool: 'select' });
      else if (key === 'escape') { dispatch({ type: 'wireStart', pin: null }); dispatch({ type: 'tool', tool: 'select' }); }
      else if (key === 'f') { send('fit'); setFitSignal(n => n + 1); }
      else if (key === 'l' && sel) send('locate');
      else if (key === 'r' && sel?.kind === 'component') void applyOps([center === 'physical'
        ? { op: 'physical_rotate', instance_id: sel.id } : { op: 'rotate_component', instance_id: sel.id }]);
      else if (key === 'm' && sel?.kind === 'component' && center === 'schematic') void applyOps([{ op: 'mirror_component', instance_id: sel.id }]);
      else if ((key === 'delete' || key === 'backspace') && sel) {
        if (sel.kind === 'component') void applyOps([{ op: 'remove_component', instance_id: sel.id }]);
        else if (sel.kind === 'net') void applyOps([{ op: 'delete_net', net_id: sel.id }]);
        else void applyOps([{ op: 'disconnect', pin: sel.id }]);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [state.selection, applyOps, undo, redo, dispatch, center]);

  const cards = useMemo(() => (st ? checkCards(st) : []), [st]);
  const v = st?.validation;
  const fs = st?.functional?.status;
  const pv = st?.physical?.verification;
  const pill = (id: CheckTab, tone: string, label: string, title: string) => (
    <span className={`badge ${tone}`} data-check={id} title={title} onClick={() => openCheck(id)}>{label}</span>
  );
  const warnCount = v ? v.warnings.filter(w => w.code !== 'W002').length : 0;
  const badge = v && pill('electrical', v.status === 'PASS' ? 'ok' : 'bad',
    v.status === 'PASS' ? `✓ valid${warnCount ? ` · ${warnCount} warning${warnCount > 1 ? 's' : ''}` : ''}` : `✕ ${v.errors.length} error${v.errors.length > 1 ? 's' : ''}`,
    'Electrical validation (deterministic)');
  const fbadge = st?.functional?.intent_present
    ? pill('function', fs === 'PASS' ? 'ok' : fs === 'FAIL' ? 'bad' : 'warn',
      fs === 'PASS' ? '✓ function' : fs === 'FAIL' ? '✕ function' : fs === 'WARN' ? '⚠ function' : '? function', 'Functional validation (deterministic)')
    : null;
  const pbadge = !pv || pv.status === 'NOT_APPLICABLE' ? null
    : pill('physical', pv.status === 'PASS' ? 'ok' : pv.status === 'FAIL' ? 'bad' : 'warn',
      pv.status === 'FAIL' ? '✕ build' : pv.status === 'WARN' ? '⚠ build' : '✓ build', 'Physical build verification (deterministic)');

  const d = st?.document.design;
  const caption = !st ? '' : center === 'schematic'
    ? `${st.schematic.components.length} parts · ${d!.nets.length} nets · drawing ${st.verification.ok ? 'matches' : 'does not match'} the netlist`
    : st.physical?.applicable
      ? `${st.physical.board?.name ?? ''} · ${st.physical.stats.parts_on_board} on the board · ${st.physical.stats.parts_offboard} beside · ${st.physical.stats.wires} wires`
      : 'no physical form';

  return (
    <div className={`studio view-${center}`}>
      <header className="topbar">
        <div className="brand"><span className="logo">◆</span> Illustration Engine</div>
        <div className="docname" title={d?.description}>
          <span className="projname">{d?.name ?? '—'}</span>
          <span className="health">{badge}{fbadge}{pbadge}</span>
        </div>
        <nav className="viewswitch" aria-label="View">
          <button data-view="schematic" className={center === 'schematic' ? 'on' : ''} onClick={() => openView('schematic')}>
            <span className="vs-ico">⌁</span> Schematic</button>
          <button data-view="physical" className={center === 'physical' ? 'on' : ''} onClick={() => openView('physical')}>
            <span className="vs-ico">⬡</span> Physical 3D</button>
        </nav>
        <div className="tools">
          <ExportMenu canBuild={!!st?.physical?.applicable}
            onSvg={async () => st && download(`${st.document.design.project_id}.svg`, await api.exportSvg(st.document), 'image/svg+xml')}
            onIr={() => st && download(`${st.document.design.project_id}.design.json`, JSON.stringify(st.document.design, null, 2), 'application/json')}
            onBuild={() => st?.physical && download(`${st.document.design.project_id}.build.json`, JSON.stringify(st.physical, null, 2), 'application/json')} />
          <button className={`ghost ai-toggle${right === 'assistant' ? ' on' : ''}`} onClick={() => setRight('assistant')} title="AI Assistant">✦ AI Assistant</button>
        </div>
      </header>

      <aside className="left">
        <nav className="tabs">
          {(['library', 'blocks', 'examples'] as const).map(t => (
            <button key={t} className={left === t ? 'on' : ''} onClick={() => setLeft(t)}>
              {t === 'library' ? 'Library' : t === 'blocks' ? 'Building blocks' : 'Examples'}</button>
          ))}
        </nav>
        <div className="panel">
          {left === 'library' && <LibraryPanel studio={studio} mode="parts" />}
          {left === 'blocks' && <LibraryPanel studio={studio} mode="blocks" />}
          {left === 'examples' && <ExamplesPanel studio={studio} onOpened={() => { setFitSignal(n => n + 1); send('fit'); }} />}
        </div>
      </aside>

      <main className="center">
        <div className="stage">
          {st && (
            <div className="canvas-caption">
              <b>{center === 'schematic' ? 'Schematic' : 'Physical build'}</b><span>{caption}</span>
            </div>
          )}
          {state.tool === 'wire' && center === 'schematic' && <span className="toolhint">{state.wireStart
            ? `Wiring from ${state.wireStart} - click the target pin (Esc to cancel)` : 'Wire tool: click a pin to start a connection'}</span>}
          {!st && <div className="empty">{state.error ?? 'Loading…'}</div>}
          {st && center === 'schematic' && <SchematicCanvas studio={studio} fitSignal={fitSignal} cmd={cmd} onZoom={setZoom} />}
          {st && center === 'physical' && (
            <ErrorBoundary fallback="3D view unavailable">
              <Suspense fallback={<div className="empty">Loading 3D…</div>}>
                <PhysicalView studio={studio} fitSignal={fitSignal} cmd={cmd} labels={labels} />
              </Suspense>
            </ErrorBoundary>
          )}
          {st && <CanvasToolbar studio={studio} view={center} zoom={zoom} labels={labels} onLabels={setLabels} send={send} />}
          {state.busy && <div className="busy">updating…</div>}
        </div>
        <footer className="status">
          {state.error ? <span className="err-msg">⚠ {state.error} <button className="link" onClick={() => dispatch({ type: 'error', error: null })}>dismiss</button></span>
            : <span>{state.notice ?? 'Ready'}</span>}
          {st && <span className="right">{st.schematic.components.length} parts · {st.document.design.nets.length} nets · drawing {st.verification.ok ? 'matches netlist ✓' : 'MISMATCH ✕'}
            {st.physical?.verification && st.physical.applicable ? ` · build ${st.physical.verification.ok ? 'matches netlist ✓' : 'MISMATCH ✕'}` : ''}</span>}
        </footer>
      </main>

      <aside className="right">
        <nav className="tabs">
          {(['assistant', 'inspect', 'checks', 'build', 'explain'] as const).map(t => {
            const bad = t === 'checks' && cards.some(c => c.tone === 'bad');
            return (
              <button key={t} className={right === t ? 'on' : ''} data-tab={t} onClick={() => setRight(t)}>
                {t === 'assistant' ? 'Assistant' : t === 'inspect' ? 'Inspector' : t === 'checks' ? `Checks${bad ? ' ✕' : ''}`
                  : t === 'build' ? `Assembly${pv?.status === 'FAIL' ? ' ✕' : ''}` : 'Explain'}
              </button>
            );
          })}
        </nav>
        <div className="panel">
          <div hidden={right !== 'assistant'} className="panel-fill">
            <AssistantPanel studio={studio} onRunning={r => { genRunning.current = r; }}
                            onGenerated={() => { setFitSignal(n => n + 1); send('fit'); }} openView={openView} openCheck={openCheck} />
          </div>
          {right === 'inspect' && <Inspector studio={studio} locate={locate} view={center} />}
          {right === 'checks' && <ChecksPanel studio={studio} tab={checkTab} onTab={setCheckTab} openView={openView} />}
          {right === 'build' && <AssemblyPanel studio={studio} openView={openView} />}
          {right === 'explain' && <ExplainPanel studio={studio} />}
        </div>
      </aside>
    </div>
  );
}
