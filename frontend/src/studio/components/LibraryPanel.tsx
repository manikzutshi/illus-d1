// Component / knowledge library: "what can I build with this system?"
// Parts come grouped by registry category (data-driven, scales with the registry); building blocks
// are the design patterns. Adding a part or a block is an ordinary engineering edit op.
import { Fragment, useEffect, useMemo, useState } from 'react';
import { api } from '../api';
import type { Studio } from '../store';
import type { ComponentDetails, DesignPatternInfo, LibraryItem } from '../types';
import { viewCenter } from '../geometry';
import { groupLibrary, searchLibrary, type KindFilter } from '../ui/library';
import { SymbolThumbnail } from './SymbolGraphics';

const detailsCache = new Map<string, ComponentDetails>();

function PartDetail({ id, onAdd, disabled }: { id: string; onAdd: () => void; disabled: boolean }) {
  const [d, setD] = useState<ComponentDetails | null>(detailsCache.get(id) ?? null);
  useEffect(() => {
    if (d) return;
    let live = true;
    api.component(id).then(x => { detailsCache.set(id, x); if (live) setD(x); }).catch(() => {});
    return () => { live = false; };
  }, [id, d]);
  if (!d) return <div className="libdetail muted small">Loading…</div>;
  const ph = d.physical;
  return (
    <div className="libdetail">
      {d.education?.summary && <p className="prose">{d.education.summary}</p>}
      {!d.education?.summary && d.description && <p className="prose muted">{d.description}</p>}
      <div className="kvgrid">
        <span>Pins</span><b>{d.pins.length}</b>
        {d.family && <><span>Family</span><b>{d.family.replace(/_/g, ' ')}</b></>}
        {ph?.package && <><span>Package</span><b>{ph.package}{ph.mounting ? ` · ${ph.mounting}` : ''}</b></>}
        {ph && ph.breadboard_compatible !== null && ph.breadboard_compatible !== undefined &&
          <><span>Breadboard</span><b>{ph.breadboard_compatible ? 'fits' : 'wired beside the board'}</b></>}
        {d.interfaces.length > 0 && <><span>Interfaces</span><b>{d.interfaces.join(', ')}</b></>}
        {Object.entries(d.electrical_properties).slice(0, 3).map(([k, v]) => <Fragment key={k}><span>{k.replace(/_/g, ' ')}</span><b className="mono">{v}</b></Fragment>)}
      </div>
      {d.concepts.length > 0 && <div className="chips">{d.concepts.slice(0, 4).map(c => <span key={c.concept_id} className="chip concept">{c.name}</span>)}</div>}
      <button className="primary small-btn" disabled={disabled} onClick={onAdd}>＋ Add to design</button>
    </div>
  );
}

function Parts({ studio }: { studio: Studio }) {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<KindFilter>('all');
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [detail, setDetail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.library().then(setItems).catch(e => setError(String(e.message ?? e))); }, []);
  const results = useMemo(() => searchLibrary(items, query, kind), [items, query, kind]);
  const groups = useMemo(() => groupLibrary(results), [results]);
  const searching = query.trim().length > 0;
  const disabled = !studio.state.studio;
  const add = (it: LibraryItem) => studio.applyOps([{ op: 'add_component', component_type: it.id, x: viewCenter.x, y: viewCenter.y }]);
  return (
    <div className="library">
      <div className="lib-head">
        <input className="search" placeholder={`Search ${items.length} parts - name, function, package…`} value={query}
               onChange={e => setQuery(e.target.value)} aria-label="Search the component library" />
        <div className="seg small-seg" role="group" aria-label="Kind">
          {(['all', 'physical', 'ideal'] as const).map(k => (
            <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{k === 'all' ? 'All' : k === 'physical' ? 'Real parts' : 'Idealised'}</button>
          ))}
        </div>
      </div>
      {error && <div className="err-msg">{error}</div>}
      {disabled && <div className="muted small">Open a design to add parts.</div>}
      {searching && <div className="muted small lib-count">{results.length} match{results.length === 1 ? '' : 'es'}</div>}
      {groups.map(g => {
        const isOpen = searching || open[g.category];
        return (
          <div key={g.category} className={`libgroup${isOpen ? ' open' : ''}`}>
            <button className="libcat" onClick={() => setOpen(o => ({ ...o, [g.category]: !o[g.category] }))} aria-expanded={!!isOpen}>
              <span className="caret">{isOpen ? '▾' : '▸'}</span>{g.label}<span className="count">{g.items.length}</span>
            </button>
            {isOpen && g.items.map(it => (
              <div key={it.id} className={`libitem${detail === it.id ? ' expanded' : ''}`}>
                <div className="librow" onClick={() => setDetail(d => (d === it.id ? null : it.id))} title={it.description}>
                  <SymbolThumbnail symbol={it.symbol} size={40} />
                  <div className="libtext">
                    <div className="libname">{it.short_name || it.name}
                      {it.object_type !== 'PHYSICAL' && <span className="chip ideal">ideal</span>}</div>
                    <div className="muted small">{it.name}</div>
                  </div>
                  <button className="add" disabled={disabled} title="Add to design"
                          onClick={e => { e.stopPropagation(); void add(it); }}>＋</button>
                </div>
                {detail === it.id && <PartDetail id={it.id} disabled={disabled} onAdd={() => void add(it)} />}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

function Blocks({ studio }: { studio: Studio }) {
  const [patterns, setPatterns] = useState<DesignPatternInfo[]>([]);
  const [query, setQuery] = useState('');
  useEffect(() => { api.patterns().then(setPatterns).catch(() => setPatterns([])); }, []);
  const q = query.trim().toLowerCase();
  const list = patterns.filter(p => !q || [p.name, p.purpose, p.category, ...p.concepts].join(' ').toLowerCase().includes(q));
  const disabled = !studio.state.studio;
  return (
    <div className="library blocks">
      <p className="muted small">Proven circuit building blocks from the knowledge base. Inserting one adds its parts and internal
        connections; wire its open ports to your design (the checks will tell you what is still missing).</p>
      <input className="search" placeholder={`Search ${patterns.length} building blocks…`} value={query} onChange={e => setQuery(e.target.value)} />
      {list.map(p => (
        <div key={p.pattern_id} className="block-card">
          <div className="block-head"><b>{p.name}</b>{p.category && <span className="chip">{p.category.replace(/_/g, ' ')}</span>}</div>
          <div className="muted small">{p.purpose}</div>
          <div className="block-parts">{p.parts.map(pp => <span key={pp.role} className="chip">{pp.role}</span>)}</div>
          {p.ports.length > 0 && <div className="muted small">Ports: {p.ports.map(x => x.name).join(', ')}</div>}
          <button className="small-btn" disabled={disabled} onClick={() => void studio.applyOps([{ op: 'insert_pattern', pattern_id: p.pattern_id }])}>＋ Insert block</button>
        </div>
      ))}
    </div>
  );
}

export function LibraryPanel({ studio, mode }: { studio: Studio; mode: 'parts' | 'blocks' }) {
  return mode === 'parts' ? <Parts studio={studio} /> : <Blocks studio={studio} />;
}
