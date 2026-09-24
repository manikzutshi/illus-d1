import type { Studio } from '../store';
import type { BehaviorResult, FunctionalFinding, FunctionalIntent, FunctionalStatus } from '../types';

const LABEL: Record<FunctionalStatus, string> = {
  PASS: '✓ does what was asked', FAIL: '✕ does not do what was asked', WARN: '⚠ works, with caveats', NOT_CHECKABLE: '? cannot be fully verified',
};

function intentText(intent: FunctionalIntent, b: FunctionalIntent['behaviors'][number]): string {
  const sig = (id?: string | null) => intent.signals.find(s => s.id === id);
  const inp = sig(b.when.input), out = sig(b.then.output);
  const thr = b.when.threshold?.kind === 'adjustable' ? ' an adjustable threshold' : b.when.threshold?.value ? ` ${b.when.threshold.value}` : ' the threshold';
  const cond = !b.when.input ? `${b.when.relation}` :
    ['above', 'below'].includes(b.when.relation) ? `${inp?.quantity ?? b.when.input} is ${b.when.relation}${thr}` : `${inp?.quantity ?? b.when.input} ${b.when.relation}`;
  return `${(out?.quantity ?? b.then.output).replace(/_/g, ' ')} ${b.then.effect.toUpperCase()} when ${cond}`;
}

export function FunctionPanel({ studio }: { studio: Studio }) {
  const { state, dispatch } = studio;
  const st = state.studio;
  if (!st) return null;
  const f = st.functional;
  if (!f) return <div className="empty">This server does not provide functional analysis - restart it with the current version (.\studio).</div>;
  const intent = st.document.intent;
  const refOf = (iid: string) => st.schematic.components.find(c => c.instance_id === iid)?.reference ?? iid;

  const highlightBehavior = (b: BehaviorResult) => {
    const instances = [...new Set([...b.input_instances, ...b.output_instances, ...b.path.map(p => p.instance),
                                   ...(b.threshold_set_by ? [b.threshold_set_by] : [])])];
    const nets = [...new Set(b.path.flatMap(p => [p.from_node, p.to_node]).filter(n => n.startsWith('net:')).map(n => n.slice(4)))];
    dispatch({ type: 'highlight', highlight: { instances, nets } });
  };
  const highlightFinding = (x: FunctionalFinding) =>
    dispatch({ type: 'highlight', highlight: { instances: x.affected_instances, nets: x.affected_nets } });

  return (
    <div className="function">
      <div className={`fstatus ${f.status.toLowerCase()}`}>
        <b>{f.intent_present ? LABEL[f.status] : 'No functional intent recorded'}</b>
        <span>{f.summary}</span>
      </div>
      <p className="muted small">Electrical validation checks that the circuit is safe and well-formed. This functional check traces
        signal paths through the netlist (device physics, no AI) to see whether it does what was requested.</p>

      {intent && intent.behaviors.length > 0 && (
        <>
          <h4>Requested behaviour</h4>
          {(f.intent_notes ?? []).length > 0 && (
            <ul className="bul small muted">{(f.intent_notes ?? []).map((n, i) => <li key={i}>Interpreted: {n}</li>)}</ul>
          )}
          {f.behaviors.map(b => {
            const spec = intent.behaviors.find(x => x.id === b.behavior_id);
            return (
              <div key={b.behavior_id} className={`behavior ${b.status.toLowerCase()}`} onClick={() => highlightBehavior(b)}
                   title="Click to highlight the functional path">
                <div className="bhead"><span className={`fchip ${b.status.toLowerCase()}`}>{b.status.replace('_', ' ')}</span>
                  <b>{spec ? intentText(intent, spec) : b.description}</b></div>
                {b.path.length > 0 && (
                  <div className="fpath">{[...new Set([b.input_instances[0], ...b.path.map(p => p.instance)])].map((i, k, arr) => (
                    <span key={i}><span className={`node ${i === b.decision_instance ? 'dec' : i === b.driver_instance ? 'drv' : ''}`}>{refOf(i)}</span>{k < arr.length - 1 && ' → '}</span>
                  ))}</div>
                )}
                <ul className="bul small">{b.explanation.map((l, i) => <li key={i}>{l}</li>)}</ul>
              </div>
            );
          })}
        </>
      )}

      {f.findings.length > 0 && (
        <>
          <h4>Findings</h4>
          <ul className="issues">
            {f.findings.map((x, i) => (
              <li key={i} className={`issue ${x.status === 'FAIL' ? 'error' : x.status === 'WARN' ? 'warning' : 'info'}`} onClick={() => highlightFinding(x)}>
                <span className="code">{x.code}</span>{x.message}
                {x.repair_hint && <div className="hint2">↳ {x.repair_hint}</div>}
                {x.patterns.length > 0 && <div className="small muted">related patterns: {x.patterns.join(', ')}</div>}
              </li>
            ))}
          </ul>
        </>
      )}

      {f.inferred.length > 0 && (
        <>
          <h4>{f.intent_present ? 'All behaviour found in the circuit' : 'Behaviour inferred from the circuit'}</h4>
          <ul className="bul small">{f.inferred.map((i, k) => (
            <li key={k} className="clickable" onClick={() => dispatch({ type: 'highlight', highlight: { instances: [i.input_instance, ...i.via, i.output_instance], nets: [] } })}>{i.statement}</li>
          ))}</ul>
        </>
      )}
      {state.highlight && <button className="link" onClick={() => dispatch({ type: 'highlight', highlight: null })}>clear highlight</button>}
    </div>
  );
}
