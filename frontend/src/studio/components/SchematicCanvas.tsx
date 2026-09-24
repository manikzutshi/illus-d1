import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fitView, VEC, viewCenter, zoomAt, type ViewBox } from '../geometry';
import type { Studio } from '../store';
import type { SchematicComponent, SchematicProject, ValidationResult } from '../types';
import { NetLabelShape, PowerPortShape, SymbolBody } from './SymbolGraphics';

interface Props { studio: Studio; fitSignal: number }

type Drag =
  | { kind: 'pan'; sx: number; sy: number; view: ViewBox; moved: boolean }
  | { kind: 'part'; iid: string; sx: number; sy: number; ox: number; oy: number; dx: number; dy: number };

function issueMaps(v: ValidationResult) {
  const inst = new Map<string, 'error' | 'warning'>();
  const nets = new Map<string, 'error' | 'warning'>();
  const pins = new Map<string, 'error' | 'warning'>();
  const add = (m: Map<string, 'error' | 'warning'>, k: string, sev: 'error' | 'warning') => {
    if (sev === 'error' || !m.has(k)) m.set(k, sev);
  };
  for (const [list, sev] of [[v.errors, 'error'], [v.warnings.filter(w => w.code !== 'W002'), 'warning']] as const) {
    for (const e of list) {
      e.affected_instances.forEach(i => add(inst, i, sev));
      e.affected_nets.forEach(n => add(nets, n, sev));
      e.affected_pins.forEach(p => { add(pins, p, sev); add(inst, p.split('.')[0], sev); });
    }
  }
  return { inst, nets, pins };
}

export function SchematicCanvas({ studio, fitSignal }: Props) {
  const { state, dispatch, applyOps } = studio;
  const sch = state.studio?.schematic as SchematicProject;
  const validation = state.studio?.validation as ValidationResult;
  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState<ViewBox>({ x: -10, y: -10, w: 80, h: 50 });
  const [drag, setDrag] = useState<Drag | null>(null);
  const [cursor, setCursor] = useState<[number, number] | null>(null);
  useEffect(() => { viewCenter.x = Math.round(view.x + view.w / 2); viewCenter.y = Math.round(view.y + view.h / 2); }, [view]);
  const issues = useMemo(() => validation ? issueMaps(validation)
    : { inst: new Map<string, 'error' | 'warning'>(), nets: new Map<string, 'error' | 'warning'>(), pins: new Map<string, 'error' | 'warning'>() },
  [validation]);

  const aspect = () => {
    const r = svgRef.current?.getBoundingClientRect();
    return r && r.height > 0 ? r.width / r.height : 1.6;
  };

  // Fit when a new design is opened (fitSignal changes) - edits keep the current view.
  useEffect(() => {
    if (sch) setView(fitView(sch.bounds, aspect()));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitSignal]);

  const toWorld = useCallback((cx: number, cy: number): [number, number] => {
    const svg = svgRef.current;
    if (!svg) return [0, 0];
    const pt = svg.createSVGPoint();
    pt.x = cx; pt.y = cy;
    const m = svg.getScreenCTM();
    if (!m) return [0, 0];
    const w = pt.matrixTransform(m.inverse());
    return [w.x, w.y];
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const [wx, wy] = toWorld(e.clientX, e.clientY);
      setView(v => zoomAt(v, e.deltaY > 0 ? 1.12 : 1 / 1.12, wx, wy));
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
  }, [toWorld]);

  if (!sch) return null;

  const sel = state.selection;
  const selectedNet = sel?.kind === 'net' ? sel.id : sel?.kind === 'pin'
    ? sch.components.find(c => c.instance_id === sel.id.split('.')[0])?.pins.find(p => p.pin_id === sel.id.split('.')[1])?.net_id ?? null
    : null;
  const activeNet = state.hoverNet ?? selectedNet;
  const hl = state.highlight;
  const hlParts = new Set(hl?.instances ?? []);
  const hlNets = new Set(hl?.nets ?? []);

  const onBackgroundDown = (e: React.PointerEvent) => {
    if (e.button !== 0 && e.button !== 1) return;
    try { (e.target as Element).setPointerCapture(e.pointerId); } catch { /* synthetic or already-released pointer */ }
    setDrag({ kind: 'pan', sx: e.clientX, sy: e.clientY, view, moved: false });
  };

  const onPartDown = (e: React.PointerEvent, c: SchematicComponent) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    dispatch({ type: 'select', selection: { kind: 'component', id: c.instance_id } });
    if (state.tool !== 'select') return;
    const [wx, wy] = toWorld(e.clientX, e.clientY);
    try { (e.target as Element).setPointerCapture(e.pointerId); } catch { /* synthetic or already-released pointer */ }
    setDrag({ kind: 'part', iid: c.instance_id, sx: wx, sy: wy, ox: c.x, oy: c.y, dx: 0, dy: 0 });
  };

  const onMove = (e: React.PointerEvent) => {
    const [wx, wy] = toWorld(e.clientX, e.clientY);
    if (state.wireStart) setCursor([wx, wy]);
    if (!drag) return;
    if (drag.kind === 'pan') {
      const svg = svgRef.current!;
      const scale = drag.view.w / svg.getBoundingClientRect().width;
      const dx = (e.clientX - drag.sx) * scale, dy = (e.clientY - drag.sy) * scale;
      setView({ ...drag.view, x: drag.view.x - dx, y: drag.view.y - dy });
      if (Math.abs(e.clientX - drag.sx) + Math.abs(e.clientY - drag.sy) > 3 && !drag.moved) setDrag({ ...drag, moved: true });
    } else {
      const dx = Math.round(wx - drag.sx), dy = Math.round(wy - drag.sy);
      if (dx !== drag.dx || dy !== drag.dy) setDrag({ ...drag, dx, dy });
    }
  };

  const onUp = () => {
    if (!drag) return;
    if (drag.kind === 'pan' && !drag.moved) {
      dispatch({ type: 'select', selection: null });
      dispatch({ type: 'wireStart', pin: null });
    }
    if (drag.kind === 'part' && (drag.dx || drag.dy)) {
      void applyOps([{ op: 'move_component', instance_id: drag.iid, x: drag.ox + drag.dx, y: drag.oy + drag.dy }]);
    }
    setDrag(null);
  };

  const onPinClick = (e: React.MouseEvent, ref: string) => {
    e.stopPropagation();
    if (state.tool === 'wire') {
      if (!state.wireStart) dispatch({ type: 'wireStart', pin: ref });
      else if (state.wireStart !== ref) void applyOps([{ op: 'connect', a: state.wireStart, b: ref }]);
      else dispatch({ type: 'wireStart', pin: null });
    } else {
      dispatch({ type: 'select', selection: { kind: 'pin', id: ref } });
    }
  };

  const netColor = (netId: string | null | undefined, base: string) => {
    if (!netId) return base;
    if (activeNet === netId || hlNets.has(netId)) return 'var(--net-active)';
    const iss = issues.nets.get(netId);
    return iss === 'error' ? 'var(--err)' : iss === 'warning' ? 'var(--warn)' : base;
  };

  const startPin = state.wireStart
    ? (() => { const [i, p] = state.wireStart.split('.'); return sch.components.find(c => c.instance_id === i)?.pins.find(q => q.pin_id === p); })()
    : undefined;

  return (
    <svg ref={svgRef} className={`canvas tool-${state.tool}`} viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
         onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={() => dispatch({ type: 'hoverNet', net: null })}>
      <defs>
        <pattern id="grid" width={2} height={2} patternUnits="userSpaceOnUse">
          <circle cx={0} cy={0} r={0.07} fill="var(--grid)" />
        </pattern>
      </defs>
      <rect x={view.x} y={view.y} width={view.w} height={view.h} fill="url(#grid)" onPointerDown={onBackgroundDown} className="bg" />

      {sch.text_annotations.map(a => (
        <text key={a.annotation_id} x={a.x} y={a.y} fontSize={a.size} fontWeight={700} fill="var(--title)">{a.text}</text>
      ))}

      {/* wires (wide invisible hit area + visible line) */}
      <g>
        {sch.wires.map(w => (
          <g key={w.wire_id} onPointerDown={e => { e.stopPropagation(); dispatch({ type: 'select', selection: { kind: 'net', id: w.net_id } }); }}
             onPointerEnter={() => dispatch({ type: 'hoverNet', net: w.net_id })} onPointerLeave={() => dispatch({ type: 'hoverNet', net: null })}
             className="wire">
            <line x1={w.x1} y1={w.y1} x2={w.x2} y2={w.y2} stroke="transparent" strokeWidth={1.2} />
            <line x1={w.x1} y1={w.y1} x2={w.x2} y2={w.y2} stroke={netColor(w.net_id, 'var(--wire)')}
                  strokeWidth={activeNet === w.net_id || hlNets.has(w.net_id) ? 0.3 : 0.18} strokeLinecap="round" />
          </g>
        ))}
        {sch.junctions.map(j => <circle key={j.junction_id} cx={j.x} cy={j.y} r={0.38} fill={netColor(j.net_id, 'var(--wire)')} />)}
      </g>

      {/* power ports and net labels */}
      {sch.power_ports.map(p => (
        <g key={p.port_id} className="port" onPointerDown={e => { e.stopPropagation(); dispatch({ type: 'select', selection: { kind: 'net', id: p.net_id } }); }}
           onPointerEnter={() => dispatch({ type: 'hoverNet', net: p.net_id })} onPointerLeave={() => dispatch({ type: 'hoverNet', net: null })}>
          <PowerPortShape kind={p.kind} x={p.x} y={p.y} direction={p.direction} text={p.text}
                          color={activeNet === p.net_id ? 'var(--net-active)' : p.kind === 'power' ? 'var(--power)' : 'var(--ground)'} />
        </g>
      ))}
      {sch.net_labels.map(l => (
        <g key={l.label_id} className="label" onPointerDown={e => { e.stopPropagation(); dispatch({ type: 'select', selection: { kind: 'net', id: l.net_id } }); }}
           onPointerEnter={() => dispatch({ type: 'hoverNet', net: l.net_id })} onPointerLeave={() => dispatch({ type: 'hoverNet', net: null })}>
          <NetLabelShape x={l.x} y={l.y} direction={l.direction} text={l.text} color={netColor(l.net_id, 'var(--label)')} />
        </g>
      ))}

      {/* components */}
      {sch.components.map(c => {
        const sym = sch.symbols[c.symbol_id];
        const dragging = drag?.kind === 'part' && drag.iid === c.instance_id ? drag : null;
        const ox = dragging ? dragging.dx : 0, oy = dragging ? dragging.dy : 0;
        const selected = sel?.kind === 'component' && sel.id === c.instance_id;
        const iss = issues.inst.get(c.instance_id);
        const stroke = iss === 'error' ? 'var(--err)' : 'var(--sym-stroke)';
        const [bx0, by0, bx1, by1] = c.bbox;
        return (
          <g key={c.instance_id} className={`part${selected ? ' selected' : ''}`} transform={`translate(${ox} ${oy})`}
             onPointerDown={e => onPartDown(e, c)}>
            {hlParts.has(c.instance_id) && !selected && (
              <rect x={bx0 - 0.9} y={by0 - 0.9} width={bx1 - bx0 + 1.8} height={by1 - by0 + 1.8} rx={0.8} className="hl-box" />
            )}
            {(selected || iss) && (
              <rect x={bx0 - 0.6} y={by0 - 0.6} width={bx1 - bx0 + 1.2} height={by1 - by0 + 1.2} rx={0.6}
                    className={selected ? 'sel-box' : `issue-box ${iss}`} />
            )}
            <rect x={bx0} y={by0} width={bx1 - bx0} height={by1 - by0} fill="transparent" />
            <SymbolBody symbol={sym} x={c.x} y={c.y} rotation={c.rotation} mirror={c.mirror} stroke={stroke} textColor="var(--sym-text)" />
            {c.pins.filter(p => !p.hidden).map(p => {
              const sp = sym.pins.find(q => q.name === p.symbol_pin);
              const len = sp?.length ?? 2;
              const [vx, vy] = VEC[p.orientation];
              const ref = `${c.instance_id}.${p.pin_id}`;
              const pinIssue = issues.pins.get(ref);
              return (
                <g key={p.pin_id}>
                  {len > 0 && <line x1={p.x} y1={p.y} x2={p.x - vx * len} y2={p.y - vy * len}
                                    stroke={netColor(p.net_id, stroke)} strokeWidth={0.15} />}
                  {pinIssue && <circle cx={p.x} cy={p.y} r={0.45} className={`pin-issue ${pinIssue}`} />}
                  {!p.net_id && !c.port_text && <circle cx={p.x} cy={p.y} r={0.22} className="pin-open" />}
                  <circle cx={p.x} cy={p.y} r={0.7} className={`pin-hit${state.wireStart === ref ? ' armed' : ''}`}
                          onPointerDown={e => e.stopPropagation()} onClick={e => onPinClick(e, ref)}
                          onPointerEnter={() => p.net_id && dispatch({ type: 'hoverNet', net: p.net_id })}>
                    <title>{`${c.reference}.${p.pin_id}${p.name && p.name !== p.pin_id ? ` (${p.name})` : ''}${p.net_id ? ` - net ${p.net_id}` : ' - unconnected'}`}</title>
                  </circle>
                </g>
              );
            })}
            {c.ref_label && <text x={c.ref_label.x} y={c.ref_label.y} fontSize={c.ref_label.size} textAnchor={c.ref_label.anchor}
                                  className="ref">{c.ref_label.text}</text>}
            {c.value_label && <text x={c.value_label.x} y={c.value_label.y} fontSize={c.value_label.size}
                                    textAnchor={c.value_label.anchor} className={c.port_text ? 'flag-text' : 'value'}>{c.value_label.text}</text>}
          </g>
        );
      })}

      {startPin && cursor && (
        <line x1={startPin.x} y1={startPin.y} x2={cursor[0]} y2={cursor[1]} className="rubber" />
      )}
    </svg>
  );
}
