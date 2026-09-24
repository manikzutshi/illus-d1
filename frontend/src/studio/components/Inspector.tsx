import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Studio } from '../store';
import type { ComponentDetails } from '../types';

const detailsCache = new Map<string, ComponentDetails>();

function useComponentDetails(typeId: string | undefined) {
  const [details, setDetails] = useState<ComponentDetails | null>(typeId ? detailsCache.get(typeId) ?? null : null);
  useEffect(() => {
    if (!typeId) { setDetails(null); return; }
    const cached = detailsCache.get(typeId);
    if (cached) { setDetails(cached); return; }
    let live = true;
    api.component(typeId).then(d => { detailsCache.set(typeId, d); if (live) setDetails(d); }).catch(() => live && setDetails(null));
    return () => { live = false; };
  }, [typeId]);
  return details;
}

function EditableField({ value, onCommit, placeholder, mono }: { value: string; onCommit: (v: string) => void; placeholder?: string; mono?: boolean }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const commit = () => { if (draft !== value) onCommit(draft); };
  return (
    <input className={`field${mono ? ' mono' : ''}`} value={draft} placeholder={placeholder}
           onChange={e => setDraft(e.target.value)} onBlur={commit}
           onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') setDraft(value); }} />
  );
}

export function Inspector({ studio }: { studio: Studio }) {
  const { state, dispatch, applyOps } = studio;
  const st = state.studio;
  const sel = state.selection;
  const compId = sel?.kind === 'component' ? sel.id : sel?.kind === 'pin' ? sel.id.split('.')[0] : undefined;
  const comp = st?.document.design.components.find(c => c.instance_id === compId);
  const details = useComponentDetails(comp?.component_type);
  if (!st) return null;

  if (sel?.kind === 'net') {
    const trace = st.schematic.nets[sel.id];
    const net = st.document.design.nets.find(n => n.net_id === sel.id);
    if (!trace || !net) return <div className="empty">Net no longer exists.</div>;
    const refOf = (iid: string) => st.schematic.components.find(c => c.instance_id === iid)?.reference ?? iid;
    return (
      <div className="inspector">
        <div className="insp-head"><span className={`chip net-${trace.net_class}`}>{trace.net_class}</span><h3>Net</h3></div>
        <label className="lbl">Name</label>
        <EditableField value={net.net_id} mono onCommit={v => applyOps([{ op: 'rename_net', net_id: net.net_id, new_net_id: v }])} />
        {trace.display_name !== net.net_id && <div className="muted">Drawn as <b>{trace.display_name}</b>{trace.voltage != null ? ` (${trace.voltage} V)` : ''}</div>}
        {trace.net_class === 'signal' && (
          <>
            <label className="lbl">Drawing style</label>
            <div className="seg">
              {(['auto', 'wire', 'label'] as const).map(s => (
                <button key={s} className={(st.document.layout.net_styles[net.net_id] ?? 'auto') === s ? 'on' : ''}
                        onClick={() => applyOps([{ op: 'set_net_style', net_id: net.net_id, style: s }])}>{s}</button>
              ))}
            </div>
          </>
        )}
        <label className="lbl">Connected pins ({net.connections.length})</label>
        <ul className="pinlist">
          {net.connections.map(pr => (
            <li key={`${pr.instance_id}.${pr.pin_id}`}>
              <button className="link" onClick={() => dispatch({ type: 'select', selection: { kind: 'component', id: pr.instance_id } })}>
                {refOf(pr.instance_id)}.{pr.pin_id}
              </button>
              <button className="icon" title="Disconnect this pin" onClick={() => applyOps([{ op: 'disconnect', pin: `${pr.instance_id}.${pr.pin_id}` }])}>✕</button>
            </li>
          ))}
        </ul>
        <div className="actions"><button className="danger" onClick={() => applyOps([{ op: 'delete_net', net_id: net.net_id }])}>Delete net</button></div>
      </div>
    );
  }

  if (comp) {
    const sc = st.schematic.components.find(c => c.instance_id === comp.instance_id);
    const pinSel = sel?.kind === 'pin' ? sel.id.split('.')[1] : null;
    const isBox = sc?.symbol_id.startsWith('box:');
    const placement = st.document.layout.placements[comp.instance_id];
    return (
      <div className="inspector">
        <div className="insp-head">
          <h3>{sc?.reference ?? comp.instance_id}</h3>
          {details && <span className={`chip ${details.object_type === 'PHYSICAL' ? '' : 'ideal'}`}>{details.object_type === 'PHYSICAL' ? details.category.toLowerCase().replace(/_/g, ' ') : 'idealised'}</span>}
        </div>
        <div className="title2">{details?.name ?? comp.component_type}</div>
        <div className="muted mono">{comp.instance_id} · {comp.component_type}</div>
        {(comp.metadata.role || comp.metadata.rationale) && (
          <div className="note">
            {comp.metadata.role && <div><b>Role:</b> {comp.metadata.role}</div>}
            {comp.metadata.rationale && <div><b>Rationale:</b> {comp.metadata.rationale}</div>}
          </div>
        )}
        <div className="actions">
          <button onClick={() => applyOps([{ op: 'rotate_component', instance_id: comp.instance_id }])} title="R">⟳ Rotate</button>
          <button onClick={() => applyOps([{ op: 'mirror_component', instance_id: comp.instance_id }])} title="M">⇋ Mirror</button>
          {isBox && <button onClick={() => applyOps([{ op: 'set_show_all_pins', instance_id: comp.instance_id, value: !placement?.show_all_pins }])}>
            {placement?.show_all_pins ? 'Hide unused pins' : 'Show all pins'}</button>}
          <button className="danger" onClick={() => applyOps([{ op: 'remove_component', instance_id: comp.instance_id }])} title="Delete">Delete</button>
        </div>

        {details && Object.keys(details.configurable_parameters).length > 0 && (
          <>
            <label className="lbl">Parameters</label>
            <table className="kv">
              <tbody>
                {Object.entries(details.configurable_parameters).map(([k, unit]) => (
                  <tr key={k}><td>{k}<span className="unit">{unit !== 'enum' ? ` (${unit})` : ''}</span></td>
                    <td><EditableField value={comp.parameters[k] ?? ''} placeholder="not set"
                                       onCommit={v => applyOps([{ op: 'set_parameter', instance_id: comp.instance_id, key: k, value: v || null }])} /></td></tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        <label className="lbl">Pins</label>
        <table className="pins">
          <tbody>
            {(details?.pins ?? sc?.pins.map(p => ({ pin_id: p.pin_id, name: p.name, direction: '', description: '' })) ?? []).map(p => {
              const netId = sc?.pins.find(q => q.pin_id === p.pin_id)?.net_id;
              return (
                <tr key={p.pin_id} className={pinSel === p.pin_id ? 'hl' : ''}>
                  <td className="mono">{p.pin_id}</td>
                  <td className="dir">{p.direction?.toLowerCase()}</td>
                  <td>{netId
                    ? <><button className="link" onClick={() => dispatch({ type: 'select', selection: { kind: 'net', id: netId } })}>{netId}</button>
                        <button className="icon" title="Disconnect" onClick={() => applyOps([{ op: 'disconnect', pin: `${comp.instance_id}.${p.pin_id}` }])}>✕</button></>
                    : <button className="link subtle" onClick={() => { dispatch({ type: 'tool', tool: 'wire' }); dispatch({ type: 'wireStart', pin: `${comp.instance_id}.${p.pin_id}` }); }}>connect…</button>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {details && (
          <>
            <label className="lbl">Electrical characteristics (registry)</label>
            {Object.keys(details.electrical_properties).length === 0
              ? <div className="muted">No electrical data recorded - treated as unknown, never assumed.</div>
              : <table className="kv"><tbody>{Object.entries(details.electrical_properties).map(([k, v]) => (
                  <tr key={k}><td>{k.replace(/_/g, ' ')}</td><td className="mono">{v}</td></tr>))}</tbody></table>}
            {details.design_constraints.length > 0 && (
              <>
                <label className="lbl">Design rules</label>
                <ul className="bul">{details.design_constraints.map((c, i) => <li key={i}><span className={`sev ${c.severity}`}>{c.kind.replace(/_/g, ' ')}</span> {c.note}</li>)}</ul>
              </>
            )}
            {details.education && (
              <>
                <label className="lbl">What it does</label>
                <p className="prose">{details.education.summary}</p>
                {details.education.how_it_works && <p className="prose muted">{details.education.how_it_works}</p>}
                {details.education.common_mistakes.length > 0 && <ul className="bul warnlist">{details.education.common_mistakes.map((m, i) => <li key={i}>{m}</li>)}</ul>}
              </>
            )}
            {details.physical?.package && <div className="muted">Package: {details.physical.package}{details.physical.mounting ? ` · ${details.physical.mounting}` : ''}</div>}
            {details.concepts.length > 0 && (
              <>
                <label className="lbl">Curriculum concepts</label>
                <div className="chips">{details.concepts.map(c => <span className="chip concept" key={c.concept_id}>{c.name}</span>)}</div>
              </>
            )}
          </>
        )}
      </div>
    );
  }

  // Nothing selected: design overview.
  const d = st.document.design;
  const prov = st.document.provenance;
  return (
    <div className="inspector">
      <div className="insp-head"><h3>Design</h3></div>
      <label className="lbl">Name</label>
      <EditableField value={d.name} onCommit={v => applyOps([{ op: 'set_design_info', name: v }])} />
      <label className="lbl">Description</label>
      <EditableField value={d.description} onCommit={v => applyOps([{ op: 'set_design_info', description: v }])} />
      <table className="kv"><tbody>
        <tr><td>Components</td><td>{d.components.length}</td></tr>
        <tr><td>Nets</td><td>{d.nets.length}</td></tr>
        <tr><td>Source</td><td>{prov.source}{prov.model ? ` · ${prov.model}` : ''}{prov.example ? ` · ${prov.example}` : ''}</td></tr>
        <tr><td>Revision</td><td>{st.document.revision}</td></tr>
        <tr><td>Drawing ↔ netlist</td><td className={st.verification.ok ? 'ok' : 'bad'}>{st.verification.ok ? 'consistent' : 'MISMATCH'}</td></tr>
        <tr><td>Layout</td><td>{st.schematic.stats.crossings} crossings · {st.schematic.stats.elapsed_ms} ms</td></tr>
      </tbody></table>
      {prov.prompt && <><label className="lbl">Prompt</label><p className="prose muted">“{prov.prompt}”</p></>}
      {st.schematic.diagnostics.length > 0 && <><label className="lbl">Drawing notes</label><ul className="bul">{st.schematic.diagnostics.map((x, i) => <li key={i}>{x}</li>)}</ul></>}
      <p className="hint">Click a part, wire or pin to inspect it. <kbd>W</kbd> wire tool · <kbd>R</kbd> rotate · <kbd>M</kbd> mirror · <kbd>Del</kbd> delete · <kbd>F</kbd> fit · <kbd>Ctrl+Z</kbd> undo</p>
    </div>
  );
}
