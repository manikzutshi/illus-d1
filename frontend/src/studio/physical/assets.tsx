// Procedural 3D visuals for physical parts, keyed by `visual.kind` (never by part name).
//
// Registry component -> physical definition (backend) -> visual kind + real body size -> this file.
// Each visual draws the part body in its own frame: origin at the body centre, x along the pin row,
// y across it, z up (converted to three.js Y-up by `L`). Leads, header pins and wires are drawn
// separately from the pin positions in the Physical IR, so the drawing always matches the build.
// A part whose kind is unknown (or `visual.fallback`) gets a labelled generic block; a detailed
// model can be supplied later through `visual.asset_url` without touching this file's callers.
import { Suspense, useMemo } from 'react';
import * as THREE from 'three';
import { useGLTF } from '@react-three/drei';
import type { PhysicalPart } from '../types';
import { localSize } from './coords';

type V3 = [number, number, number];
const L = (x: number, y: number, z: number): V3 => [x, z, y];

interface Mat { color: string; metal?: boolean; opacity?: number; emissive?: string }
function M({ color, metal, opacity, emissive }: Mat) {
  return <meshStandardMaterial color={color} metalness={metal ? 0.8 : 0.05} roughness={metal ? 0.3 : 0.6}
                               transparent={opacity !== undefined && opacity < 1} opacity={opacity ?? 1}
                               emissive={emissive ?? '#000000'} emissiveIntensity={emissive ? 0.6 : 0} />;
}
function Box({ at = [0, 0, 0], size, ...m }: { at?: V3; size: V3 } & Mat) {
  return <mesh position={L(...at)} castShadow><boxGeometry args={[size[0], size[2], size[1]]} /><M {...m} /></mesh>;
}
/** Cylinder along a local axis (z = upright). */
function Cyl({ at = [0, 0, 0], r, h, axis = 'z', seg = 24, ...m }: { at?: V3; r: number; h: number; axis?: 'x' | 'y' | 'z'; seg?: number } & Mat) {
  const rot: V3 = axis === 'x' ? [0, 0, Math.PI / 2] : axis === 'y' ? [Math.PI / 2, 0, 0] : [0, 0, 0];
  return <mesh position={L(...at)} rotation={rot} castShadow><cylinderGeometry args={[r, r, h, seg]} /><M {...m} /></mesh>;
}
function Sphere({ at = [0, 0, 0], r, ...m }: { at?: V3; r: number } & Mat) {
  return <mesh position={L(...at)}><sphereGeometry args={[r, 20, 14, 0, Math.PI * 2, 0, Math.PI / 2]} /><M {...m} /></mesh>;
}

const BAND: Record<string, string> = {
  black: '#1b1b1b', brown: '#6d3b1a', red: '#c62828', orange: '#ef6c00', yellow: '#fdd835', green: '#2e7d32',
  blue: '#1565c0', violet: '#6a1b9a', grey: '#9e9e9e', white: '#fafafa', gold: '#c9a227', silver: '#c0c0c0',
};

export interface VisualProps { part: PhysicalPart; size: V3 }

function AxialResistor({ part, size: [l, d] }: VisualProps) {
  const bands = (part.visual.params.bands ?? '').split(',').filter(Boolean);
  const r = d / 2;
  return (
    <group>
      <Cyl r={r * 0.85} h={l * 0.7} axis="x" color="#d9c29a" />
      <Cyl at={[-l * 0.36, 0, 0]} r={r} h={l * 0.22} axis="x" color="#d9c29a" />
      <Cyl at={[l * 0.36, 0, 0]} r={r} h={l * 0.22} axis="x" color="#d9c29a" />
      {bands.map((b, i) => (
        <Cyl key={i} at={[-l * 0.3 + i * l * 0.15 + (i === 3 ? l * 0.1 : 0), 0, 0]} r={r * 0.92} h={l * 0.07} axis="x" color={BAND[b] ?? '#888'} />
      ))}
    </group>
  );
}
function AxialDiode({ part, size: [l, d] }: VisualProps) {
  // cathode band at the end nearer the K pin
  const k = part.pins.find(p => p.pin_id === 'K');
  const a = part.pins.find(p => p.pin_id === 'A');
  let sign = 1;
  if (k && a && part.body) {
    const along = part.rotation % 180 ? 1 : 0;
    const dk = k.position[along] - part.body.center[along];
    sign = (part.rotation === 180 || part.rotation === 270 ? -1 : 1) * Math.sign(dk || 1);
  }
  const glass = part.component_type_id.includes('1n4148');
  return (
    <group>
      <Cyl r={d / 2} h={l} axis="x" color={glass ? '#e06a2c' : '#1f1f1f'} opacity={glass ? 0.85 : 1} />
      <Cyl at={[sign * l * 0.36, 0, 0]} r={d / 2 + 0.03} h={l * 0.12} axis="x" color={glass ? '#111' : '#d0d0d0'} />
    </group>
  );
}
function Led({ part, size: [, d, h] }: VisualProps) {
  const color = part.visual.params.color ?? '#eceff1';
  return (
    <group>
      <Cyl at={[0, 0, -h / 2 + 0.5]} r={d / 2 + 0.3} h={1} color={color} opacity={0.75} />
      <Cyl at={[0, 0, -h / 2 + 1 + (h - 3.5) / 2]} r={d / 2} h={h - 3.5} color={color} opacity={0.7} />
      <Sphere at={[0, 0, h / 2 - 2.5]} r={d / 2} color={color} opacity={0.7} />
    </group>
  );
}
function LedRgb(p: VisualProps) {
  return <Led {...p} part={{ ...p.part, visual: { ...p.part.visual, params: { ...p.part.visual.params, color: '#f5f5f5' } } }} />;
}
function CeramicCap({ size: [l, d, h] }: VisualProps) {
  return <mesh position={L(0, 0, 0)} rotation={[Math.PI / 2, 0, 0]}><cylinderGeometry args={[Math.min(l, h) / 2, Math.min(l, h) / 2, d * 0.6, 24]} /><M color="#e0a030" /></mesh>;
}
function Electrolytic({ size: [l, , h] }: VisualProps) {
  const r = l / 2;
  return (
    <group>
      <Cyl r={r} h={h} color="#243a8f" />
      <Cyl at={[0, 0, h / 2 + 0.05]} r={r * 0.85} h={0.1} color="#c8c8c8" metal />
      <Box at={[r * 0.92, 0, 0]} size={[0.3, r * 0.9, h * 0.98]} color="#d9dde8" />
    </group>
  );
}
function To92({ part, size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <mesh position={L(0, 0, 0)} rotation={[0, 0, 0]}>
        <cylinderGeometry args={[l / 2, l / 2, h, 24, 1, false, -Math.PI / 2, Math.PI]} />
        <M color="#1d1d1d" />
      </mesh>
      <Box at={[0, -0.05, 0]} size={[l, 0.1, h]} color="#2a2a2a" />
      <TextPlate at={[0, -d / 2 - 0.02, h / 4]} text={part.visual.params.text ?? ''} width={l} />
    </group>
  );
}
function To220({ size: [l, d, h] }: VisualProps) {
  const bodyH = h * 0.6;
  return (
    <group>
      <Box at={[0, 0, -h / 2 + bodyH / 2]} size={[l, d, bodyH]} color="#1d1d1d" />
      <Box at={[0, d / 2 - 0.65, h / 2 - (h - bodyH) / 2]} size={[l, 1.3, h - bodyH]} color="#b8b8b8" metal />
      <Cyl at={[0, d / 2 - 0.65, h / 2 - (h - bodyH) / 2]} r={1.8} h={1.5} axis="y" color="#333" />
    </group>
  );
}
function Dip({ part, size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l, d, h]} color="#1c1c1e" />
      <Cyl at={[-l / 2, 0, h / 2 - 0.4]} r={1.0} h={0.9} color="#0c0c0c" />
      <Cyl at={[-l / 2 + 1.6, -d / 2 + 1.4, h / 2]} r={0.45} h={0.1} color="#555" />
      <TextPlate at={[0.6, 0, h / 2 + 0.03]} flat text={part.visual.params.text ?? ''} width={Math.min(l * 0.72, 12)} />
    </group>
  );
}
function Header({ size: [l, d] }: VisualProps) {
  return <Box at={[0, 0, -3.25]} size={[l, d, 2.5]} color="#141414" />;
}
function Trimpot({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l, d, h * 0.7]} at={[0, 0, -h * 0.15]} color="#1e5bb8" />
      <Cyl at={[0, 0, h * 0.25]} r={Math.min(l, d) * 0.38} h={h * 0.3} color="#f0f0f0" />
      <Box at={[0, 0, h * 0.41]} size={[Math.min(l, d) * 0.6, 0.5, 0.2]} color="#555" />
    </group>
  );
}
function PushButton({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l, d, h * 0.6]} at={[0, 0, -h * 0.2]} color="#2b2b2b" />
      <Cyl at={[0, 0, h * 0.3]} r={Math.min(l, d) * 0.3} h={h * 0.4} color="#9e9e9e" />
    </group>
  );
}
function Buzzer({ size: [l, , h] }: VisualProps) {
  return (
    <group>
      <Cyl r={l / 2} h={h} color="#151515" />
      <Cyl at={[0, 0, h / 2 + 0.02]} r={1.0} h={0.1} color="#444" />
    </group>
  );
}
function Ldr({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <mesh rotation={[Math.PI / 2, 0, 0]} position={L(0, 0, 0)}><cylinderGeometry args={[l / 2, l / 2, d, 24]} /><M color="#c9c9c9" /></mesh>
      <Box at={[0, -d / 2 - 0.02, 0]} size={[l * 0.7, 0.04, h * 0.55]} color="#c0392b" />
    </group>
  );
}
function Thermistor({ size: [l, d] }: VisualProps) {
  return <mesh rotation={[Math.PI / 2, 0, 0]} position={L(0, 0, 0)}><cylinderGeometry args={[l / 2, l / 2, d, 20]} /><M color="#335c3a" /></mesh>;
}
function SlideSwitch({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l, d, h]} color="#9aa0a6" metal />
      <Box at={[l * 0.12, 0, h / 2 + 1]} size={[1.5, 1.5, 2]} color="#222" />
    </group>
  );
}
function Hcsr04({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box at={[0, d / 2 - 0.8, 0]} size={[l, 1.6, h]} color="#1f5fa8" />
      <Cyl at={[-l * 0.28, d / 2 - 1.6 - 6, 0]} r={8} h={12} axis="y" color="#c9ccd1" metal />
      <Cyl at={[l * 0.28, d / 2 - 1.6 - 6, 0]} r={8} h={12} axis="y" color="#c9ccd1" metal />
    </group>
  );
}
function Pcb({ color, size: [l, d, h], children }: { color: string; size: V3; children?: React.ReactNode }) {
  return <group><Box size={[l, d, Math.min(h, 1.6)]} at={[0, 0, -h / 2 + 0.8]} color={color} />{children}</group>;
}
function ModulePcb({ part, size }: VisualProps) {
  return <Pcb color="#1c6e3d" size={size}><TextPlate at={[0, 0, -size[2] / 2 + 1.7]} flat text={part.visual.params.text ?? ''} width={size[0] * 0.8} /></Pcb>;
}
function Oled({ size }: VisualProps) {
  const [l, d, h] = size;
  return <Pcb color="#15407a" size={size}><Box at={[0, 1.5, -h / 2 + 2.0]} size={[l * 0.92, d * 0.62, 0.8]} color="#050505" /></Pcb>;
}
function Pico({ size }: VisualProps) {
  const [l, , h] = size;
  return (
    <Pcb color="#1e7a3c" size={size}>
      <Box at={[-l / 2 + 3, 0, -h / 2 + 2.3]} size={[5.5, 8, 2.6]} color="#bdbdbd" metal />
      <Box at={[2, 0, -h / 2 + 2.0]} size={[7, 7, 1]} color="#111" />
    </Pcb>
  );
}
function SmdAdapter({ part, size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l, d, h]} color="#1c5fa8" />
      <Box at={[0, -d / 2 - 0.4, 1]} size={[Math.min(l * 0.5, 5), 0.8, 3]} color="#111" />
      <TextPlate at={[0, -d / 2 - 0.02, -h / 4]} text={part.visual.params.text ?? ''} width={l * 0.9} />
    </group>
  );
}
function Dht11({ size }: VisualProps) {
  return <Box size={size} color="#2f7fd1" />;
}
function SevenSegment({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l, d, h]} color="#161616" />
      <Box at={[0, 0, h / 2 + 0.02]} size={[l * 0.55, d * 0.72, 0.05]} color="#3a0d0d" />
    </group>
  );
}
// ── off-board ────────────────────────────────────────────────────────────
function Battery9v({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l * 0.86, d, h]} at={[-l * 0.07, 0, 0]} color="#1a1a1a" />
      <Box size={[l * 0.14, d, h]} at={[l * 0.43, 0, 0]} color="#c9a227" metal />
      <Cyl at={[l / 2 + 0.8, -4, 0]} r={2.5} h={1.6} axis="x" color="#bbb" metal />
      <Cyl at={[l / 2 + 0.8, 4, 0]} r={3.2} h={1.6} axis="x" color="#bbb" metal />
    </group>
  );
}
function BatteryHolder({ size: [l, d, h] }: VisualProps) {
  const cells = Math.max(2, Math.round(d / 14.5));
  return (
    <group>
      <Box size={[l, d, h * 0.5]} at={[0, 0, -h * 0.25]} color="#111" />
      {Array.from({ length: cells }, (_, i) => (
        <Cyl key={i} at={[0, -d / 2 + d / cells * (i + 0.5), h * 0.05]} r={7} h={l * 0.8} axis="x" color={i % 2 ? '#2e7d32' : '#37474f'} />
      ))}
    </group>
  );
}
function UsbSupply({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l, d, h * 0.25]} at={[0, 0, -h * 0.375]} color="#1f2d3d" />
      <Box size={[9, 12, 4.5]} at={[-l / 2 + 4.5, 0, -h * 0.02]} color="#c8ccd2" metal />
      <Box size={[3, 3, 1]} at={[l / 2 - 5, -d / 4, -h * 0.2]} color="#111" />
    </group>
  );
}
function ArduinoUno({ size }: VisualProps) {
  const [l, d, h] = size;
  return (
    <Pcb color="#0f7f8c" size={size}>
      <Box at={[-l / 2 + 6, d / 2 - 14, -h / 2 + 7]} size={[16, 12, 11]} color="#bdbdbd" metal />
      <Box at={[-l / 2 + 7, -d / 2 + 10, -h / 2 + 6]} size={[14, 9, 11]} color="#111" />
      <Box at={[8, 0, -h / 2 + 3]} size={[35, 8, 4]} color="#111" />
      <Box at={[6, -d / 2 + 2.5, -h / 2 + 5.6]} size={[46, 2.5, 8.5]} color="#141414" />
      <Box at={[12, d / 2 - 2.5, -h / 2 + 5.6]} size={[38, 2.5, 8.5]} color="#141414" />
    </Pcb>
  );
}
function Esp32({ size }: VisualProps) {
  const [l, d, h] = size;
  return (
    <Pcb color="#1a1a1a" size={size}>
      <Box at={[-l / 2 + 12, 0, -h / 2 + 2.5]} size={[18, 16, 3]} color="#c0c0c0" metal />
      <Box at={[l / 2 - 3, 0, -h / 2 + 3]} size={[6, 8, 3]} color="#bdbdbd" metal />
      <Box at={[0, -d / 2 + 1.5, -h / 2 + 5.6]} size={[38, 2.5, 8.5]} color="#141414" />
      <Box at={[0, d / 2 - 1.5, -h / 2 + 5.6]} size={[38, 2.5, 8.5]} color="#141414" />
    </Pcb>
  );
}
function PirModule({ size }: VisualProps) {
  const [, d, h] = size;
  return <Pcb color="#2e7d32" size={size}><Sphere at={[0, 0, -h / 2 + 1.6]} r={Math.min(d / 2, 11)} color="#f5f5f5" opacity={0.9} /></Pcb>;
}
function GasModule({ size }: VisualProps) {
  const [, d, h] = size;
  return <Pcb color="#1c5fa8" size={size}><Cyl at={[0, 0, 0]} r={d * 0.4} h={h - 2} color="#b0b0b0" metal /></Pcb>;
}
function EncoderModule({ size }: VisualProps) {
  const [, , h] = size;
  return <Pcb color="#1c5fa8" size={size}><Cyl at={[0, 0, 0]} r={3} h={h - 2} color="#9e9e9e" metal /></Pcb>;
}
function LcdModule({ size }: VisualProps) {
  const [l, d, h] = size;
  return <Pcb color="#2e7d32" size={size}><Box at={[0, 0, -h / 2 + 5]} size={[l * 0.9, d * 0.7, 8]} color="#6b8e23" /></Pcb>;
}
function RelayModule({ size }: VisualProps) {
  const [l, , h] = size;
  return (
    <Pcb color="#1c5fa8" size={size}>
      <Box at={[-2, 0, -h / 2 + 9]} size={[19, 15.5, 15.3]} color="#1e4fb0" />
      <Box at={[l / 2 - 4, 0, -h / 2 + 6]} size={[7, 15, 10]} color="#2e7d32" />
    </Pcb>
  );
}
function Relay({ size }: VisualProps) { return <Box size={size} color="#1e4fb0" />; }
function Servo({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Box size={[l, d, h * 0.75]} at={[0, 0, -h * 0.125]} color="#1565c0" />
      <Cyl at={[l * 0.25, 0, h * 0.35]} r={2.4} h={h * 0.2} color="#eeeeee" />
    </group>
  );
}
function DcMotor({ size: [l, d, h] }: VisualProps) {
  return (
    <group>
      <Cyl r={Math.min(d, h) / 2} h={l} axis="x" color="#b0b7bd" metal />
      <Cyl at={[l / 2 + 4, 0, 0]} r={1} h={8} axis="x" color="#ddd" metal />
    </group>
  );
}
function ScrewTerminal({ size }: VisualProps) { return <Box size={size} color="#2e7d32" />; }

export function GenericModule({ part, size }: VisualProps) {
  return (
    <group>
      <Box size={size} color={part.visual.fallback ? '#8d99a6' : '#607d8b'} opacity={part.visual.fallback ? 0.9 : 1} />
      <TextPlate at={[0, 0, size[2] / 2 + 0.02]} flat text={part.visual.params.text ?? part.reference} width={size[0] * 0.9} />
    </group>
  );
}

/** Flat text rendered to a canvas texture (no external font download - works offline). */
function TextPlate({ at, text, width, flat }: { at: V3; text: string; width: number; flat?: boolean }) {
  const tex = useMemo(() => {
    if (!text || typeof document === 'undefined') return null;
    const c = document.createElement('canvas');
    c.width = 256; c.height = 64;
    const g = c.getContext('2d');
    if (!g) return null;
    g.fillStyle = 'rgba(0,0,0,0)'; g.fillRect(0, 0, 256, 64);
    g.fillStyle = '#e8e8e8'; g.font = 'bold 34px sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(text.slice(0, 12), 128, 34);
    const t = new THREE.CanvasTexture(c);
    t.anisotropy = 4;
    return t;
  }, [text]);
  if (!tex) return null;
  const w = Math.max(width, 2);
  return (
    <mesh position={L(...at)} rotation={flat ? [-Math.PI / 2, 0, 0] : [0, Math.PI, 0]}>
      <planeGeometry args={[w, w / 4]} />
      <meshBasicMaterial map={tex} transparent depthWrite={false} />
    </mesh>
  );
}

export const VISUALS: Record<string, (p: VisualProps) => React.ReactElement> = {
  axial_resistor: AxialResistor, axial_inductor: AxialResistor, axial_diode: AxialDiode, led_5mm: Led, led_rgb: LedRgb,
  ceramic_cap: CeramicCap, electrolytic_cap: Electrolytic, to92: To92, to220: To220, dip: Dip, header: Header,
  trimpot: Trimpot, pushbutton: PushButton, buzzer: Buzzer, ldr: Ldr, thermistor_disc: Thermistor,
  slide_switch: SlideSwitch, hcsr04: Hcsr04, module_pcb: ModulePcb, oled: Oled, pico: Pico, smd_adapter: SmdAdapter,
  dht11: Dht11, seven_segment: SevenSegment, battery_9v: Battery9v, battery_holder: BatteryHolder, usb_supply: UsbSupply,
  arduino_uno: ArduinoUno, esp32_devkit: Esp32, pir_module: PirModule, gas_module: GasModule, encoder_module: EncoderModule,
  lcd_module: LcdModule, relay_module: RelayModule, relay: Relay, servo: Servo, dc_motor: DcMotor,
  screw_terminal: ScrewTerminal, generic_module: GenericModule,
};

/** Kinds that lie flat (their leads bend into the body ends at mid-height). */
export const LYING_KINDS = new Set(['axial_resistor', 'axial_inductor', 'axial_diode']);

export function isProcedural(kind: string): boolean {
  return kind in VISUALS;
}

function GlbAsset({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const cloned = useMemo(() => scene.clone(), [scene]);
  return <primitive object={cloned} />;
}

/** The body of a part in its own frame. Detailed model if one exists, else procedural, else generic. */
export function PartBody({ part }: { part: PhysicalPart }) {
  const size = localSize(part) as V3;
  const Visual = VISUALS[part.visual.kind] ?? GenericModule;
  const procedural = <Visual part={part} size={size} />;
  if (part.visual.asset_url) {
    return <Suspense fallback={procedural}><GlbAsset url={part.visual.asset_url} /></Suspense>;
  }
  return procedural;
}
