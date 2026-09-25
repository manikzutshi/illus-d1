// "Is this design right?" in one place: the three deterministic checks side by side, each opening
// its existing detail panel (reused unchanged), plus what is assumed or cannot be checked.
import type { Studio } from '../store';
import { checkCards } from '../ui/checks';
import { FunctionPanel } from './FunctionPanel';
import { ValidationPanel } from './Panels';

export type CheckTab = 'electrical' | 'function' | 'physical';

function PhysicalChecks({ studio, openView }: { studio: Studio; openView: (v: 'schematic' | 'physical') => void }) {
  const { state, dispatch } = studio;
  const phys = state.studio?.physical;
  if (!phys) {
    return <div className="empty-card">The breadboard build has not been generated yet.
      <button onClick={() => openView('physical')}>Build it in the Physical 3D view</button></div>;
  }
  const v = phys.verification;
  if (!v) return null;
  const pick = (iid?: string, net?: string) => {
    if (iid) dispatch({ type: 'select', selection: { kind: 'component', id: iid }, source: 'panel' });
    else if (net) dispatch({ type: 'select', selection: { kind: 'net', id: net }, source: 'panel' });
  };
  return (
    <div className="physchecks">
      <div className={`fstatus ${v.status === 'PASS' ? 'pass' : v.status === 'FAIL' ? 'fail' : v.status === 'WARN' ? 'warn' : 'not_checkable'}`}>
        <b>{v.ok ? '✓ The breadboard build matches the netlist' : '✕ The build does not match the netlist'}</b><span>{v.summary}</span>
      </div>
      <p className="muted small">Connectivity is rebuilt from holes, strips, rails, leads and jumpers and compared with the engineering nets.</p>
      <ul className="issues">
        {v.findings.filter(f => f.severity !== 'INFO').map((f, i) => (
          <li key={i} className={`issue ${f.severity === 'ERROR' ? 'error' : 'warning'}`} onClick={() => pick(f.instances[0], f.nets[0])}>
            <span className="code">{f.code}</span>{f.message}</li>
        ))}
      </ul>
      <details><summary className="small">{v.checks.length} checks run</summary>
        <table className="checks"><tbody>{v.checks.map(c => <tr key={c.code} className={c.outcome.toLowerCase()}><td className="mono">{c.code}</td><td>{c.name}</td><td>{c.outcome.toLowerCase()}</td></tr>)}</tbody></table>
      </details>
    </div>
  );
}

export function ChecksPanel({ studio, tab, onTab, openView }: {
  studio: Studio; tab: CheckTab; onTab: (t: CheckTab) => void; openView: (v: 'schematic' | 'physical') => void;
}) {
  const st = studio.state.studio;
  if (!st) return null;
  const cards = checkCards(st);
  const ex = st.explanation;
  const notCheckable = [
    ...st.functional.findings.filter(f => f.status === 'NOT_CHECKABLE').map(f => `${f.code}: ${f.message}`),
    ...(st.validation.warnings.some(w => w.code === 'W002') ? [`${st.validation.warnings.filter(w => w.code === 'W002').length} pin(s) have no voltage data (electrical check skipped for them)`] : []),
  ];
  return (
    <div className="checks-hub">
      <div className="check-cards">
        {cards.map(c => (
          <button key={c.id} className={`check-card ${c.tone}${tab === c.id ? ' on' : ''}`} data-check={c.id} onClick={() => onTab(c.id)}>
            <span className="cc-title">{c.title}</span>
            <span className="cc-verdict">{c.verdict}</span>
            <span className="cc-detail">{c.detail}</span>
          </button>
        ))}
      </div>
      <p className="muted small principle">All three are deterministic checks run on the engineering design. The AI never grades its own work.</p>
      <div className="check-body">
        {tab === 'electrical' && <ValidationPanel studio={studio} />}
        {tab === 'function' && <FunctionPanel studio={studio} />}
        {tab === 'physical' && <PhysicalChecks studio={studio} openView={openView} />}
      </div>
      {(ex.assumptions.length > 0 || notCheckable.length > 0) && (
        <div className="assumptions">
          <h4>Assumptions and limits</h4>
          {ex.assumptions.length > 0 && <ul className="bul">{ex.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>}
          {notCheckable.length > 0 && <><div className="muted small">Not checkable:</div><ul className="bul small">{notCheckable.map((a, i) => <li key={i}>{a}</li>)}</ul></>}
        </div>
      )}
    </div>
  );
}
