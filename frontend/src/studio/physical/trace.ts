// Engineering <-> physical traceability. Pure functions - unit tested.
//
// The studio has one selection, expressed in engineering terms (component / net / pin). Both the
// schematic and the physical view derive what to highlight from it, so selecting in one view
// selects the same engineering object in the other.
import type { PhysicalProject, PhysicalWire, Selection } from '../types';

export interface PhysicalHighlight {
  parts: Set<string>;        // instance ids
  wires: Set<string>;        // wire ids
  pins: Set<string>;         // "instance.pin"
  nets: Set<string>;
}

export function emptyHighlight(): PhysicalHighlight {
  return { parts: new Set(), wires: new Set(), pins: new Set(), nets: new Set() };
}

export function highlightFor(sel: Selection, phys: PhysicalProject | null | undefined, extra?: { instances: string[]; nets: string[] } | null): PhysicalHighlight {
  const h = emptyHighlight();
  if (!phys) return h;
  const addNet = (net: string) => {
    h.nets.add(net);
    const trace = phys.nets[net];
    trace?.wires.forEach(w => h.wires.add(w));
    trace?.pins.forEach(p => h.pins.add(p));
  };
  if (sel?.kind === 'component') {
    h.parts.add(sel.id);
  } else if (sel?.kind === 'net') {
    addNet(sel.id);
  } else if (sel?.kind === 'pin') {
    h.pins.add(sel.id);
    const [iid, pin] = sel.id.split('.');
    const part = phys.parts.find(p => p.instance_id === iid);
    const net = part?.pins.find(p => p.pin_id === pin)?.net_id;
    if (net) addNet(net);
  }
  extra?.instances.forEach(i => h.parts.add(i));
  extra?.nets.forEach(addNet);
  return h;
}

/** Clicking a wire selects the engineering net it realises. */
export function selectionForWire(w: PhysicalWire): Selection {
  return { kind: 'net', id: w.net_id };
}

/** Engineering component -> what realises it physically (for the inspector). */
export function physicalSummary(phys: PhysicalProject | null | undefined, instanceId: string) {
  const part = phys?.parts.find(p => p.instance_id === instanceId);
  if (!part) return null;
  const pins = part.pins.map(p => ({
    pin: p.pin_id, net: p.net_id ?? null,
    where: p.hole ? p.hole : p.alias_of ? `same pin as ${p.alias_of}` : p.terminal ? `${p.terminal} terminal` : 'not connected physically',
  }));
  const wires = phys!.wires.filter(w => w.a.pin_ref?.startsWith(`${instanceId}.`) || w.b.pin_ref?.startsWith(`${instanceId}.`));
  return { part, pins, wires };
}

/** Which physical findings mention an instance (for badges in the inspector). */
export function findingsFor(phys: PhysicalProject | null | undefined, instanceId: string) {
  return (phys?.verification?.findings ?? []).filter(f => f.instances.includes(instanceId));
}
