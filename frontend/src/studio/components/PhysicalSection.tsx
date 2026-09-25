// Inspector section: how the selected engineering component is realised physically.
import { useState } from 'react';
import type { Studio } from '../store';
import { findingsFor, physicalSummary } from '../physical/trace';

const SOURCE_TEXT: Record<string, string> = {
  datasheet: 'from the datasheet', standard: 'standard package dimensions',
  typical: 'typical part - real parts vary', assumed: 'stand-in: no real data recorded',
};

export function PhysicalSection({ studio, instanceId }: { studio: Studio; instanceId: string }) {
  const { state, dispatch, applyOps } = studio;
  const phys = state.studio?.physical;
  const [target, setTarget] = useState('');
  const info = physicalSummary(phys, instanceId);
  if (!phys || !info) return null;
  const { part, pins, wires } = info;
  const findings = findingsFor(phys, instanceId).filter(f => f.severity !== 'INFO');
  if (part.mount === 'virtual') {
    return (<><label className="lbl">Physical</label><div className="muted">Idealised primitive: no physical form.</div></>);
  }
  const where = part.mount === 'breadboard'
    ? `on the breadboard, first pin in ${part.anchor} (${part.orientation === 'dip' ? 'across the centre gap' : part.orientation === 'rail' ? 'into a power rail' : part.orientation === 'cross' ? 'across the rows' : 'along a row'})`
    : part.mount === 'offboard' ? 'beside the breadboard, wired with leads / jumpers' : 'not placed';
  return (
    <div className="phys-section">
      <label className="lbl">Physical build</label>
      <div className="muted small">{part.reference} is {where}.</div>
      <div className="muted small">Geometry: {SOURCE_TEXT[part.geometry.source]}{part.visual.fallback ? ' · shown as a generic block' : ''}</div>
      {part.geometry.variant_note && <div className="note small">⚠ {part.geometry.variant_note}</div>}
      <table className="pins"><tbody>
        {pins.map(p => (
          <tr key={p.pin}>
            <td className="mono">{p.pin}</td>
            <td className="mono">{p.where}</td>
            <td>{p.net ? <button className="link" onClick={() => dispatch({ type: 'select', selection: { kind: 'net', id: p.net! } })}>{p.net}</button> : <span className="muted">—</span>}</td>
          </tr>
        ))}
      </tbody></table>
      {wires.length > 0 && <div className="muted small">{wires.length} lead/wire(s) attach to this part.</div>}
      {part.mount === 'breadboard' && (
        <div className="actions">
          <button onClick={() => applyOps([{ op: 'physical_rotate', instance_id: instanceId }])} title="R in the 3D view">⟳ Rotate on board</button>
          <input className="hole-input" value={target} placeholder="hole, e.g. c12" onChange={e => setTarget(e.target.value)}
                 onKeyDown={e => { if (e.key === 'Enter' && target.trim()) void applyOps([{ op: 'physical_move', instance_id: instanceId, anchor: target.trim() }]); }} />
          <button disabled={!target.trim()} onClick={() => applyOps([{ op: 'physical_move', instance_id: instanceId, anchor: target.trim() }])}>Move</button>
        </div>
      )}
      {part.notes.map((n, i) => <div key={i} className="note small">{n}</div>)}
      {findings.map((f, i) => <div key={i} className={`issue ${f.severity === 'ERROR' ? 'error' : 'warn'}`}><b>{f.code}</b> {f.message}</div>)}
    </div>
  );
}
