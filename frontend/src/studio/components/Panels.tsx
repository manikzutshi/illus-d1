import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Studio } from '../store';
import type { ExampleInfo, ValidationIssue } from '../types';

// ── Validation ────────────────────────────────────────────────────────────

export function ValidationPanel({ studio }: { studio: Studio }) {
  const { state, dispatch } = studio;
  const v = state.studio?.validation;
  const [showChecks, setShowChecks] = useState(false);
  if (!v) return null;
  const focus = (e: ValidationIssue) => {
    if (e.affected_instances[0]) dispatch({ type: 'select', selection: { kind: 'component', id: e.affected_instances[0] }, source: 'panel' });
    else if (e.affected_pins[0]) dispatch({ type: 'select', selection: { kind: 'pin', id: e.affected_pins[0] }, source: 'panel' });
    else if (e.affected_nets[0]) dispatch({ type: 'select', selection: { kind: 'net', id: e.affected_nets[0] }, source: 'panel' });
  };
  const applied = v.checks_run.filter(c => c.outcome !== 'NOT_APPLICABLE');
  const notCheckable = v.warnings.filter(w => w.code === 'W002');
  const Item = ({ e, cls }: { e: ValidationIssue; cls: string }) => (
    <li className={`issue ${cls}`} onClick={() => focus(e)}><span className="code">{e.code}</span>{e.message}</li>
  );
  return (
    <div className="validation">
      <div className={`vstatus ${v.status === 'PASS' ? 'pass' : 'fail'}`}>
        <b>{v.status === 'PASS' ? '✓ Valid design' : '✕ Design has errors'}</b>
        <span>{v.errors.length} errors · {v.warnings.length - notCheckable.length} warnings · {applied.length} checks applied</span>
      </div>
      <ul className="issues">
        {v.errors.map((e, i) => <Item key={`e${i}`} e={e} cls="error" />)}
        {v.warnings.filter(w => w.code !== 'W002').map((e, i) => <Item key={`w${i}`} e={e} cls="warning" />)}
        {v.infos.map((e, i) => <Item key={`i${i}`} e={e} cls="info" />)}
      </ul>
      {notCheckable.length > 0 && (
        <details className="nc"><summary>{notCheckable.length} pin(s) not checkable - missing voltage data</summary>
          <ul>{notCheckable.map((w, i) => <li key={i} onClick={() => focus(w)}>{w.affected_pins.join(', ')}</li>)}</ul>
        </details>
      )}
      <button className="link" onClick={() => setShowChecks(s => !s)}>{showChecks ? 'Hide' : 'Show'} checks performed</button>
      {showChecks && (
        <table className="checks"><tbody>
          {v.checks_run.map(c => <tr key={c.code} className={c.outcome.toLowerCase()}><td className="mono">{c.code}</td><td>{c.name}</td><td>{c.outcome.replace('_', ' ').toLowerCase()}</td></tr>)}
        </tbody></table>
      )}
    </div>
  );
}

// ── Explanation ───────────────────────────────────────────────────────────

export function ExplainPanel({ studio }: { studio: Studio }) {
  const { state, dispatch } = studio;
  const ex = state.studio?.explanation;
  if (!ex) return null;
  return (
    <div className="explain">
      <p className="prose">{ex.summary}</p>
      <h4>Parts and their roles</h4>
      <table className="parts"><tbody>
        {ex.parts.map(p => (
          <tr key={p.instance_id} onClick={() => dispatch({ type: 'select', selection: { kind: 'component', id: p.instance_id }, source: 'panel' })}>
            <td className="mono">{p.reference}</td>
            <td><b>{p.name}</b>{!p.physical && <span className="chip ideal">idealised</span>}
              <div className="muted">{p.role || p.what_it_does}</div>
              {p.rationale && <div className="muted small">↳ {p.rationale}</div>}</td>
          </tr>
        ))}
      </tbody></table>
      <h4>Power</h4>
      <ul className="bul">{ex.power_rails.map(r => <li key={r.net_id}><b>{r.name}</b> → {r.members.join(', ')}</li>)}</ul>
      <h4>Signals</h4>
      <ul className="bul">{ex.signals.map(sg => (
        <li key={sg.net_id}><span className="mono">{sg.net_id}</span>: {sg.drivers.length ? `${sg.drivers.join(', ')} → ` : ''}{sg.members.filter(m => !sg.drivers.includes(m)).join(', ')}</li>
      ))}</ul>
      {ex.assumptions.length > 0 && <><h4>Assumptions</h4><ul className="bul">{ex.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul></>}
      <h4>What was checked</h4>
      <p className="muted">{ex.checks.filter(c => c.outcome !== 'NOT_APPLICABLE').map(c => c.name).join(' · ')}</p>
      <h4>Limitations</h4>
      <ul className="bul">{ex.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
      {ex.concepts.length > 0 && <><h4>Concepts</h4><div className="chips">{ex.concepts.map(c => <span className="chip concept" key={c.concept_id}>{c.name}</span>)}</div></>}
    </div>
  );
}

// ── Examples ──────────────────────────────────────────────────────────────

export function ExamplesPanel({ studio, onOpened }: { studio: Studio; onOpened: () => void }) {
  const [examples, setExamples] = useState<ExampleInfo[]>([]);
  useEffect(() => { api.examples().then(setExamples).catch(() => setExamples([])); }, []);
  return (
    <div className="examples">
      <p className="muted small">Hand-checked reference designs covering the curriculum. They open instantly and work offline.</p>
      {examples.map(ex => (
        <button key={ex.id} className="example" onClick={async () => { await studio.load(() => api.openExample(ex.id), `Opened example: ${ex.name}`); onOpened(); }}>
          <b>{ex.name}</b>
          <span className="muted small">{ex.description}</span>
          <span className="chips">{ex.concept && <span className="chip concept">{ex.concept}</span>}<span className="chip">{ex.components} parts</span></span>
        </button>
      ))}
    </div>
  );
}
