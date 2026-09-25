// Interactive 3D view of the physical (breadboard) build.
//
// Everything drawn comes from the backend Physical IR (state.physical): parts, pin holes, leads,
// wires. The view never decides where anything goes; dragging a part proposes a hole and sends a
// `physical_move` op, which the backend placement engine accepts or refuses (e.g. "would short").
// Selection is the studio's engineering selection, shared with the schematic; "locate" eases the
// camera to the selected part or net.
import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { ContactShadows, Html, OrbitControls } from '@react-three/drei';
import type { Studio } from '../store';
import type { BoardInfo, PhysicalPart, PhysicalProject, PhysicalWire } from '../types';
import type { CanvasCmd } from '../components/CanvasToolbar';
import { LYING_KINDS, PartBody } from './assets';
import { boardHoles, boundsCenter, fitDistance, focusTarget, nearestHole, rotY, snappedAnchor, toThree, wireArc, type HolePos } from './coords';
import { highlightFor, selectionForWire, type PhysicalHighlight } from './trace';

const ACCENT = '#ffa94d';
const HOVER = '#7cb4ff';
type View = 'iso' | 'top' | 'front';

class AssetBoundary extends React.Component<{ children: React.ReactNode; fallback: React.ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

/** Column numbers, row letters and rail signs printed on the board (canvas texture, no downloads). */
function useBoardPrint(board: BoardInfo, holes: HolePos[]) {
  return useMemo(() => {
    if (typeof document === 'undefined') return null;
    const [L, W] = board.size_mm;
    const px = 12;                                   // texture pixels per mm
    const c = document.createElement('canvas');
    c.width = Math.round(L * px); c.height = Math.round(W * px);
    const g = c.getContext('2d');
    if (!g) return null;
    const X = (x: number) => (x + L / 2) * px, Y = (y: number) => (y + W / 2) * px;
    g.clearRect(0, 0, c.width, c.height);
    // hole recesses
    for (const h of holes) {
      g.fillStyle = '#4a4b50';
      g.fillRect(X(h.x) - 0.45 * px, Y(h.y) - 0.45 * px, 0.9 * px, 0.9 * px);
      g.fillStyle = '#26272a';
      g.fillRect(X(h.x) - 0.3 * px, Y(h.y) - 0.3 * px, 0.6 * px, 0.6 * px);
    }
    // rail lines
    for (const r of board.rails) {
      const off = (r.rail_id.startsWith('T') ? -1 : 1) * (r.polarity === '-' ? 1.55 : -1.55);
      g.strokeStyle = r.polarity === '+' ? '#d9534f' : '#3b7dd8';
      g.lineWidth = 0.35 * px;
      g.beginPath(); g.moveTo(X(-L / 2 + 5), Y(r.y + off)); g.lineTo(X(L / 2 - 5), Y(r.y + off)); g.stroke();
      g.fillStyle = g.strokeStyle;
      g.font = `bold ${2.2 * px}px sans-serif`;
      g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(r.polarity === '+' ? '+' : '−', X(-L / 2 + 2.6), Y(r.y));
    }
    // column numbers and row letters
    g.fillStyle = '#8a8d93';
    g.font = `${1.5 * px}px sans-serif`;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    board.column_x.forEach((x, i) => {
      const col = i + 1;
      if (col === 1 || col % 5 === 0) {
        g.fillText(String(col), X(x), Y(board.row_y.a - 2.1));
        g.fillText(String(col), X(x), Y(board.row_y.j + 2.1));
      }
    });
    for (const r of board.rows) {
      const y = board.row_y[r];
      g.fillText(r, X(board.column_x[0] - 2.6), Y(y));
      g.fillText(r, X(board.column_x[board.column_x.length - 1] + 2.6), Y(y));
    }
    const t = new THREE.CanvasTexture(c);
    t.anisotropy = 8;
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, [board, holes]);
}

function BoardMesh({ board, holes }: { board: BoardInfo; holes: HolePos[] }) {
  const [L, W, H] = board.size_mm;
  const print = useBoardPrint(board, holes);
  return (
    <group>
      <mesh position={[0, -H / 2 - 0.2, 0]} castShadow receiveShadow>
        <boxGeometry args={[L, H - 0.4, W]} />
        <meshStandardMaterial color="#e9e6de" roughness={0.85} />
      </mesh>
      <mesh position={[0, -0.2, 0]} receiveShadow>
        <boxGeometry args={[L - 0.6, 0.4, W - 0.6]} />
        <meshStandardMaterial color="#f6f4ee" roughness={0.8} />
      </mesh>
      <mesh position={[0, 0.005, 0]}>
        <boxGeometry args={[L - 6, 0.02, 2.4]} />
        <meshStandardMaterial color="#dcd8cd" roughness={0.9} />
      </mesh>
      {print && (
        <mesh position={[0, 0.012, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[L, W]} />
          <meshStandardMaterial map={print} transparent roughness={0.9} depthWrite={false} />
        </mesh>
      )}
    </group>
  );
}

function Legs({ part, color }: { part: PhysicalPart; color: string }) {
  const segs = useMemo(() => {
    if (part.mount !== 'breadboard' || !part.body) return [];
    const b = part.body;
    const lying = LYING_KINDS.has(part.visual.kind);
    const top = lying ? b.center[2] : b.center[2] - b.size[2] / 2;
    const out: THREE.Vector3[][] = [];
    for (const p of part.pins) {
      if (!p.hole) continue;
      const [x, y] = p.position;
      const cx = Math.min(Math.max(x, b.center[0] - b.size[0] / 2 + 0.3), b.center[0] + b.size[0] / 2 - 0.3);
      const cy = Math.min(Math.max(y, b.center[1] - b.size[1] / 2 + 0.3), b.center[1] + b.size[1] / 2 - 0.3);
      const pts = [new THREE.Vector3(x, -2, y), new THREE.Vector3(x, top, y)];
      if (Math.hypot(cx - x, cy - y) > 0.05) pts.push(new THREE.Vector3(cx, top, cy));
      out.push(pts);
    }
    return out;
  }, [part]);
  return (
    <group>
      {segs.map((pts, i) => pts.slice(1).map((q, j) => {
        const p = pts[j];
        const len = p.distanceTo(q);
        const mid = p.clone().add(q).multiplyScalar(0.5);
        const dir = q.clone().sub(p).normalize();
        const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
        return (
          <mesh key={`${i}-${j}`} position={mid} quaternion={quat} castShadow>
            <cylinderGeometry args={[0.24, 0.24, len, 8]} />
            <meshStandardMaterial color={color} metalness={0.9} roughness={0.25} />
          </mesh>
        );
      }))}
    </group>
  );
}

function Terminals({ part, highlight }: { part: PhysicalPart; highlight: PhysicalHighlight }) {
  if (part.mount !== 'offboard') return null;
  return (
    <group>
      {part.pins.filter(p => p.terminal && p.terminal !== 'lead').map(p => {
        const on = highlight.pins.has(`${part.instance_id}.${p.pin_id}`);
        return (
          <mesh key={p.pin_id} position={toThree(p.position)} castShadow>
            <boxGeometry args={[0.7, p.terminal === 'screw' ? 2 : 3.2, 0.7]} />
            <meshStandardMaterial color={on ? ACCENT : p.terminal === 'screw' ? '#9e9e9e' : '#d6b25e'} metalness={0.85} roughness={0.25} />
          </mesh>
        );
      })}
    </group>
  );
}

interface DragState { iid: string; start: THREE.Vector3; dx: number; dy: number; moved: boolean }

function PartNode({ part, highlight, selected, hovered, showPins, showLabel, dragOffset, onDown, onHover, onSelectPin }: {
  part: PhysicalPart; highlight: PhysicalHighlight; selected: boolean; hovered: boolean; showPins: boolean; showLabel: boolean;
  dragOffset: [number, number] | null; onDown: (e: ThreeEvent<PointerEvent>, part: PhysicalPart) => void;
  onHover: (iid: string | null) => void; onSelectPin: (ref: string) => void;
}) {
  if (!part.body || part.mount === 'virtual') return null;
  const b = part.body;
  const lit = selected || highlight.parts.has(part.instance_id);
  const off: [number, number, number] = dragOffset ? [dragOffset[0], 0, dragOffset[1]] : [0, 0, 0];
  const labelZ = b.center[2] + b.size[2] / 2 + 3;
  const outline = lit || hovered;
  return (
    <group position={off}>
      <group position={toThree(b.center)} rotation={[0, rotY(part.rotation), 0]}
             onPointerDown={e => onDown(e, part)}
             onPointerOver={e => { e.stopPropagation(); onHover(part.instance_id); }}
             onPointerOut={() => onHover(null)} userData={{ instance: part.instance_id }}>
        <AssetBoundary fallback={null}><PartBody part={part} /></AssetBoundary>
        {outline && (
          <lineSegments>
            <edgesGeometry args={[new THREE.BoxGeometry(...(part.rotation % 180
              ? [b.size[1] + 1.2, b.size[2] + 1.2, b.size[0] + 1.2]
              : [b.size[0] + 1.2, b.size[2] + 1.2, b.size[1] + 1.2]) as [number, number, number])]} />
            <lineBasicMaterial color={lit ? ACCENT : HOVER} />
          </lineSegments>
        )}
      </group>
      <Legs part={part} color={lit ? '#ffd8a8' : '#c9ccd1'} />
      <Terminals part={part} highlight={highlight} />
      {showPins && part.pins.filter(p => p.hole || p.terminal).map(p => {
        const ref = `${part.instance_id}.${p.pin_id}`;
        const on = highlight.pins.has(ref);
        return (
          <mesh key={p.pin_id} position={toThree([p.position[0], p.position[1], p.position[2] + 0.8])}
                onPointerDown={e => { e.stopPropagation(); onSelectPin(ref); }}>
            <sphereGeometry args={[0.45, 12, 10]} />
            <meshBasicMaterial color={on ? ACCENT : '#22d3ee'} />
          </mesh>
        );
      })}
      {(showLabel || lit || hovered) && (
        <Html position={[b.center[0], labelZ, b.center[1]]} center zIndexRange={[10, 0]} style={{ pointerEvents: 'none' }}>
          <div className={`phys-label${lit ? ' on' : ''}${hovered && !lit ? ' hover' : ''}${part.visual.fallback ? ' fallback' : ''}`}>
            {part.reference}{part.visual.fallback ? ' ?' : ''}
            {(hovered || lit) && <span className="pl-sub">{part.visual.params.text ?? ''}{part.value && part.value !== part.visual.params.text ? ` · ${part.value}` : ''}</span>}
          </div>
        </Html>
      )}
    </group>
  );
}

function WireTube({ wire, lit, dim, onPick }: { wire: PhysicalWire; lit: boolean; dim: boolean; onPick: (w: PhysicalWire) => void }) {
  const geo = useMemo(() => {
    const pts = wireArc(wire.path).map(p => new THREE.Vector3(...toThree(p)));
    if (pts.length < 2) return null;
    const curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal');
    return new THREE.TubeGeometry(curve, Math.max(48, pts.length * 4), lit ? 0.62 : 0.5, 10, false);
  }, [wire, lit]);
  useEffect(() => () => geo?.dispose(), [geo]);
  if (!geo) return null;
  const ends = [wire.a, wire.b].filter(e => e.kind === 'hole');
  return (
    <group>
      <mesh geometry={geo} castShadow onPointerDown={e => { e.stopPropagation(); onPick(wire); }} userData={{ wire: wire.wire_id }}>
        <meshStandardMaterial color={wire.color} emissive={lit ? ACCENT : '#000000'} emissiveIntensity={lit ? 0.3 : 0}
                              transparent={dim} opacity={dim ? 0.18 : 1} roughness={0.35} metalness={0.05} />
      </mesh>
      {ends.map((e, i) => (
        <mesh key={i} position={toThree([e.position[0], e.position[1], 1.2])}>
          <cylinderGeometry args={[0.55, 0.55, 2.4, 10]} />
          <meshStandardMaterial color={dim ? '#555' : '#1d1d1f'} roughness={0.5} transparent={dim} opacity={dim ? 0.3 : 1} />
        </mesh>
      ))}
    </group>
  );
}

/** Camera presets and "look at the selection", eased over a few frames. */
function CameraRig({ bounds, view, viewSignal, focus }: {
  bounds: [number, number, number, number]; view: View; viewSignal: number;
  focus: { center: [number, number, number]; radius: number; n: number } | null;
}) {
  const { camera, controls } = useThree() as unknown as { camera: THREE.PerspectiveCamera; controls: { target: THREE.Vector3; update: () => void } | null };
  const goal = useRef<{ pos: THREE.Vector3; target: THREE.Vector3; t: number } | null>(null);

  useEffect(() => {
    const [cx, cy] = boundsCenter(bounds);
    const d = fitDistance(bounds, 40);
    const target = new THREE.Vector3(cx, 0, cy);
    const pos = view === 'top' ? new THREE.Vector3(cx, d * 1.05, cy + 0.01)
      : view === 'front' ? new THREE.Vector3(cx, d * 0.35, cy + d)
        : new THREE.Vector3(cx, d * 0.66, cy + d * 0.82);
    camera.near = 1; camera.far = d * 30;
    camera.updateProjectionMatrix();
    goal.current = { pos, target, t: 0 };
  }, [bounds, view, viewSignal, camera]);

  useEffect(() => {
    if (!focus) return;
    const target = new THREE.Vector3(...toThree(focus.center));
    const dist = Math.max(focus.radius * 4, 60);
    const cur = controls?.target ?? new THREE.Vector3();
    const dir = camera.position.clone().sub(cur).normalize();
    if (dir.y < 0.35) dir.y = 0.55;
    dir.normalize();
    goal.current = { pos: target.clone().add(dir.multiplyScalar(dist)), target, t: 0 };
  }, [focus, camera, controls]);

  useFrame((_, dt) => {
    const g = goal.current;
    if (!g) return;
    g.t = Math.min(1, g.t + dt * 3.2);
    const k = 1 - Math.pow(1 - g.t, 3);
    camera.position.lerp(g.pos, k);
    if (controls) { controls.target.lerp(g.target, k); controls.update(); } else camera.lookAt(g.target);
    if (g.t >= 1) goal.current = null;
  });
  return null;
}

export default function PhysicalView({ studio, fitSignal, cmd, labels = true }: { studio: Studio; fitSignal: number; cmd?: CanvasCmd; labels?: boolean }) {
  const { state, dispatch, applyOps } = studio;
  const phys = state.studio?.physical as PhysicalProject | null | undefined;
  const [view, setView] = useState<View>('iso');
  const [viewSignal, setViewSignal] = useState(0);
  const [focus, setFocus] = useState<{ center: [number, number, number]; radius: number; n: number } | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [hover, setHover] = useState<HolePos | null>(null);
  const [hoverPart, setHoverPart] = useState<string | null>(null);
  const dragRef = useRef<DragState | null>(null);
  dragRef.current = drag;

  const holes = useMemo(() => (phys?.board ? boardHoles(phys.board) : []), [phys?.board]);
  const sel = state.selection;
  const highlight = useMemo(() => highlightFor(sel, phys, state.highlight), [sel, phys, state.highlight]);
  const netFocus = highlight.nets.size > 0;

  const locate = () => {
    const t = focusTarget(phys, sel);
    if (t) setFocus(f => ({ ...t, n: (f?.n ?? 0) + 1 }));
  };

  // A selection made elsewhere (schematic, inspector, assembly steps, checks) brings the camera to it;
  // clicks inside the 3D view do not move the camera.
  const localSelect = useRef(false);
  const selKey = sel ? `${sel.kind}:${sel.id}` : '';
  useEffect(() => {
    if (localSelect.current) { localSelect.current = false; return; }
    if (sel) locate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selKey]);

  // Toolbar commands (view-only).
  useEffect(() => {
    if (!cmd || !cmd.n) return;
    if (cmd.kind === 'fit') { setViewSignal(n => n + 1); setFocus(null); }
    else if (cmd.kind === 'locate') locate();
    else if (cmd.kind.startsWith('view-')) { setView(cmd.kind.slice(5) as View); setViewSignal(n => n + 1); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cmd?.n]);
  useEffect(() => { setViewSignal(n => n + 1); }, [fitSignal]);

  // Expose a small, stable summary for automated UI checks (no engineering authority).
  useEffect(() => {
    (window as unknown as { __physicalView?: object | null }).__physicalView = phys ? {
      parts: phys.parts.filter(p => p.mount !== 'virtual').length, wires: phys.wires.length,
      highlightedParts: [...highlight.parts], highlightedWires: [...highlight.wires], status: phys.verification?.status,
      focusCount: focus?.n ?? 0, focusCenter: focus?.center ?? null,
    } : null;
  }, [phys, highlight, focus]);

  if (!phys) return <div className="empty">Building the physical view…</div>;
  if (!phys.applicable) {
    return <div className="empty">{phys.verification?.summary ?? 'This design has no physical form.'}<br />
      <span className="muted small">Idealised primitives (ideal sources, ideal transistors, logic gates) teach concepts; build a physical version with real parts from the library.</span></div>;
  }

  const onDown = (e: ThreeEvent<PointerEvent>, part: PhysicalPart) => {
    e.stopPropagation();
    if (sel?.kind !== 'component' || sel.id !== part.instance_id) {
      localSelect.current = true;
      dispatch({ type: 'select', selection: { kind: 'component', id: part.instance_id } });
    }
    if (part.mount === 'breadboard' || part.mount === 'offboard') {
      const p = e.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3());
      if (p) setDrag({ iid: part.instance_id, start: p, dx: 0, dy: 0, moved: false });
    }
  };
  const onMove = (e: ThreeEvent<PointerEvent>) => {
    const p = e.point;
    setHover(nearestHole(holes, p.x, p.z, 1.6));
    const d = dragRef.current;
    if (!d) return;
    const dx = p.x - d.start.x, dy = p.z - d.start.z;
    if (Math.hypot(dx, dy) > 1.2 || d.moved) setDrag({ ...d, dx, dy, moved: true });
  };
  const onUp = () => {
    const d = dragRef.current;
    setDrag(null);
    if (!d || !d.moved || !phys) return;
    const part = phys.parts.find(p => p.instance_id === d.iid);
    if (!part) return;
    if (part.mount === 'breadboard') {
      const target = snappedAnchor(holes, part, d.dx, d.dy);
      if (target && target.id !== part.anchor) void applyOps([{ op: 'physical_move', instance_id: part.instance_id, anchor: target.id }]);
    } else {
      void applyOps([{ op: 'physical_move', instance_id: part.instance_id, x: Math.round(part.position[0] + d.dx), y: Math.round(part.position[1] + d.dy) }]);
    }
  };
  const dragOffset = (iid: string): [number, number] | null => {
    if (!drag || drag.iid !== iid || !drag.moved) return null;
    const part = phys.parts.find(p => p.instance_id === iid);
    if (part?.mount === 'breadboard') {
      const a = holes.find(h => h.id === part.anchor);
      const t = snappedAnchor(holes, part, drag.dx, drag.dy);
      return a && t ? [t.x - a.x, t.y - a.y] : [drag.dx, drag.dy];
    }
    return [drag.dx, drag.dy];
  };
  const boardH = phys.board?.size_mm[2] ?? 8.5;
  const b = phys.bounds;
  const hoverOwner = hover ? phys.occupied[hover.id] : undefined;
  const fallbackCount = phys.parts.filter(p => p.visual.fallback).length;
  const span = Math.max(b[2] - b[0], b[3] - b[1]);

  return (
    <div className={`physical3d${hoverPart ? ' hovering' : ''}`} onContextMenu={e => e.preventDefault()}>
      <Canvas shadows dpr={[1, 2]} camera={{ fov: 40, near: 1, far: 5000, position: [0, 200, 200] }}
              gl={{ antialias: true }} onPointerMissed={() => { localSelect.current = true; dispatch({ type: 'select', selection: null }); }}>
        <color attach="background" args={['#131519']} />
        <fog attach="fog" args={['#131519', span * 2.2, span * 6]} />
        <hemisphereLight args={['#ffffff', '#30343b', 0.75]} />
        <directionalLight position={[70, 170, 90]} intensity={1.6} castShadow
                          shadow-mapSize-width={2048} shadow-mapSize-height={2048}
                          shadow-camera-left={-span} shadow-camera-right={span} shadow-camera-top={span} shadow-camera-bottom={-span} />
        <directionalLight position={[-140, 80, -120]} intensity={0.45} color="#b8c7ff" />
        <OrbitControls makeDefault enabled={!drag} enableDamping dampingFactor={0.12} maxPolarAngle={Math.PI * 0.49} />
        <CameraRig bounds={b} view={view} viewSignal={viewSignal} focus={focus} />
        <mesh position={[(b[0] + b[2]) / 2, -boardH - 0.05, (b[1] + b[3]) / 2]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow
              onPointerMove={onMove} onPointerUp={onUp}>
          <planeGeometry args={[span * 8 + 400, span * 8 + 400]} />
          <meshStandardMaterial color="#1a1d22" roughness={1} />
        </mesh>
        <ContactShadows position={[(b[0] + b[2]) / 2, -boardH + 0.02, (b[1] + b[3]) / 2]} scale={span * 1.6} blur={2.2} far={30} opacity={0.55} />
        {phys.board && <BoardMesh board={phys.board} holes={holes} />}
        {phys.parts.map(p => (
          <PartNode key={p.instance_id} part={p} highlight={highlight}
                    selected={sel?.kind === 'component' && sel.id === p.instance_id}
                    hovered={hoverPart === p.instance_id}
                    showPins={(sel?.kind === 'component' && sel.id === p.instance_id) || (sel?.kind === 'pin' && sel.id.startsWith(`${p.instance_id}.`))}
                    showLabel={labels}
                    dragOffset={dragOffset(p.instance_id)} onDown={onDown} onHover={setHoverPart}
                    onSelectPin={ref => { localSelect.current = true; dispatch({ type: 'select', selection: { kind: 'pin', id: ref } }); }} />
        ))}
        {phys.wires.map(w => (
          <WireTube key={w.wire_id} wire={w} lit={highlight.wires.has(w.wire_id)} dim={netFocus && !highlight.wires.has(w.wire_id)}
                    onPick={x => { localSelect.current = true; dispatch({ type: 'select', selection: selectionForWire(x) }); }} />
        ))}
        {/* invisible drag/hover plane at the board surface */}
        <mesh position={[0, 0.05, 0]} rotation={[-Math.PI / 2, 0, 0]} onPointerMove={onMove} onPointerUp={onUp}>
          <planeGeometry args={[span * 8 + 400, span * 8 + 400]} />
          <meshBasicMaterial transparent opacity={0} depthWrite={false} />
        </mesh>
      </Canvas>
      <div className="phys-overlay top-right phys-stats" data-parts={phys.stats.parts_on_board + phys.stats.parts_offboard}
           data-wires={phys.wires.length} data-status={phys.verification?.status ?? ''}>
        {hover ? <>hole <b>{hover.id}</b> · {hover.node.replace('top:', 'strip top ').replace('bot:', 'strip bottom ').replace('rail:', 'rail ')} · {hoverOwner ? hoverOwner.replace(/^pin:/, '').replace(/^wire:/, 'wire ') : 'free'}</>
          : <>drag a part to another hole · R rotates · right-drag pans · wheel zooms</>}
        {fallbackCount > 0 && <> · <span className="warn-txt">{fallbackCount} generic stand-in{fallbackCount > 1 ? 's' : ''}</span></>}
      </div>
    </div>
  );
}
