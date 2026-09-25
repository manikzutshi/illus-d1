// Library organisation: search, filter and grouping. Pure - unit tested.
// Data-driven: categories and families come from the registry, so nothing here depends on
// today's parts; a larger library only means more groups and more items.
import type { LibraryItem } from '../types';

export type KindFilter = 'all' | 'physical' | 'ideal';

export const CATEGORY_LABEL: Record<string, string> = {
  MICROCONTROLLER: 'Microcontroller boards', SENSOR: 'Sensors', PASSIVE_COMPONENT: 'Passives',
  ACTIVE_COMPONENT: 'Modules & actuators', SEMICONDUCTOR: 'Semiconductors', INTEGRATED_CIRCUIT: 'Integrated circuits',
  POWER_MANAGEMENT: 'Power management', POWER_SOURCE: 'Power sources', GROUND_NODE: 'Ground & rails',
  CONNECTOR: 'Connectors', SWITCH: 'Switches', ACTUATOR: 'Actuators', DISPLAY: 'Displays', MEMORY: 'Memory',
  INTERFACE: 'Interface', LOGIC: 'Logic', ROUTING: 'Routing',
};

/** Preferred order of well-known categories; unknown ones follow alphabetically. */
const CATEGORY_ORDER = ['MICROCONTROLLER', 'SENSOR', 'ACTIVE_COMPONENT', 'ACTUATOR', 'DISPLAY', 'INTEGRATED_CIRCUIT',
  'SEMICONDUCTOR', 'PASSIVE_COMPONENT', 'SWITCH', 'POWER_SOURCE', 'POWER_MANAGEMENT', 'MEMORY', 'INTERFACE',
  'CONNECTOR', 'LOGIC', 'GROUND_NODE', 'ROUTING'];

export function categoryLabel(cat: string): string {
  return CATEGORY_LABEL[cat] ?? cat.toLowerCase().replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());
}

export function haystack(it: LibraryItem): string {
  return [it.id, it.name, it.short_name, it.family, it.description, ...it.tags, ...it.aliases, it.category, categoryLabel(it.category)]
    .filter(Boolean).join(' ').toLowerCase();
}

/** Every query token must appear; results ranked by where the match is (name > alias/tag > description). */
export function searchLibrary(items: LibraryItem[], query: string, kind: KindFilter = 'all'): LibraryItem[] {
  const pool = items.filter(it => kind === 'all' || (kind === 'physical') === (it.object_type === 'PHYSICAL'));
  const toks = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!toks.length) return pool;
  const scored: [number, LibraryItem][] = [];
  for (const it of pool) {
    const hay = haystack(it);
    if (!toks.every(t => hay.includes(t))) continue;
    const name = `${it.short_name ?? ''} ${it.name}`.toLowerCase();
    const tags = [...it.aliases, ...it.tags, it.family ?? ''].join(' ').toLowerCase();
    let score = 0;
    for (const t of toks) score += name.includes(t) ? 0 : tags.includes(t) ? 1 : 2;
    scored.push([score, it]);
  }
  return scored.sort((a, b) => a[0] - b[0] || a[1].name.localeCompare(b[1].name)).map(s => s[1]);
}

export interface LibraryGroup { category: string; label: string; items: LibraryItem[] }

export function groupLibrary(items: LibraryItem[]): LibraryGroup[] {
  const m = new Map<string, LibraryItem[]>();
  for (const it of items) m.set(it.category, [...(m.get(it.category) ?? []), it]);
  const rank = (c: string) => { const i = CATEGORY_ORDER.indexOf(c); return i < 0 ? 1000 : i; };
  return [...m.entries()]
    .sort((a, b) => rank(a[0]) - rank(b[0]) || categoryLabel(a[0]).localeCompare(categoryLabel(b[0])))
    .map(([category, list]) => ({ category, label: categoryLabel(category), items: [...list].sort((a, b) => (a.short_name || a.name).localeCompare(b.short_name || b.name)) }));
}
