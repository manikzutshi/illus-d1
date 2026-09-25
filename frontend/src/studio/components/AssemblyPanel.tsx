// Assembly tab: physical verification + board choice + step-by-step build instructions.
import type { Studio } from '../store';

const LABEL: Record<string, string> = {
  PASS: '✓ The build matches the netlist', WARN: '⚠ The build matches the netlist - check flagged parts',
  FAIL: '✕ The build does not match the netlist', NOT_APPLICABLE: 'No physical form',
};

export function AssemblyPanel({ studio, openView }: { studio: Studio; openView?: (v: 'schematic' | 'physical') => void }) {
  const { state, dispatch, applyOps } = studio;
  const phys = state.studio?.physical;
  if (!phys) {
    return <div className="empty-card">The breadboard build has not been generated yet.
      {openView && <button onClick={() => openView('physical')}>Build it in the Physical 3D view</button>}</div>;
  }
  const v = phys.verification;
  const board = state.studio?.document.physical?.board ?? 'auto';
  const pick = (iid?: string | null, net?: string | null) => {
    if (iid) dispatch({ type: 'select', selection: { kind: 'component', id: iid }, source: 'panel' });
    else if (net) dispatch({ type: 'select', selection: { kind: 'net', id: net }, source: 'panel' });
  };
  return (
    <div className="assembly">
      {v && (
        <div className={`fstatus ${v.status === 'PASS' ? 'pass' : v.status === 'FAIL' ? 'fail' : v.status === 'WARN' ? 'warn' : 'not_checkable'}`}>
          <b>{LABEL[v.status]}</b>
          <span>{v.summary}</span>
        </div>
      )}
      <p className="muted small">Physical check (deterministic): connectivity is rebuilt from holes, strips, rails, leads and wires and
        compared with the engineering nets - like the schematic's drawing check, for the breadboard.</p>
      {phys.applicable && (
        <div className="actions">
          <label className="small">Board&nbsp;
            <select value={board} onChange={e => applyOps([{ op: 'set_breadboard', board: e.target.value as 'auto' | 'half' | 'full' }])}>
              <option value="auto">automatic</option><option value="half">half-size (400)</option><option value="full">full-size (830)</option>
            </select>
          </label>
          <button onClick={() => applyOps([{ op: 'physical_auto_arrange', keep_locked: false }])}>✦ Re-arrange build</button>
        </div>
      )}
      {v && v.findings.filter(f => f.severity !== 'INFO').length > 0 && (
        <>
          <h4>Findings</h4>
          {v.findings.filter(f => f.severity !== 'INFO').map((f, i) => (
            <div key={i} className={`issue ${f.severity === 'ERROR' ? 'error' : 'warn'}`} onClick={() => pick(f.instances[0], f.nets[0])}>
              <b>{f.code}</b> {f.message}
            </div>
          ))}
        </>
      )}
      {v && v.checks.length > 0 && (
        <details>
          <summary className="small">{v.checks.length} checks run</summary>
          <ul className="bul small">{v.checks.map(c => <li key={c.code}><span className={`sev ${c.outcome === 'PASS' ? 'INFO' : c.outcome === 'FAIL' ? 'ERROR' : 'WARNING'}`}>{c.outcome}</span> {c.code} {c.name}</li>)}</ul>
        </details>
      )}
      {phys.assembly.length > 0 && (
        <>
          <h4>Build steps</h4>
          <ol className="steps">
            {phys.assembly.map(s => (
              <li key={s.step} className={`step ${s.kind}`} onClick={() => pick(s.instance_id, s.net_id)} data-step={s.step}>{s.text}</li>
            ))}
          </ol>
        </>
      )}
      {phys.diagnostics.map((d, i) => <div key={i} className="note small">{d}</div>)}
    </div>
  );
}
