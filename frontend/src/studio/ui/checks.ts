// One summary of "is this design right?" across the three deterministic checks. Pure - unit tested.
import type { StudioState } from '../types';

export type Tone = 'ok' | 'warn' | 'bad' | 'neutral';
export interface CheckCard { id: 'electrical' | 'function' | 'physical'; title: string; tone: Tone; verdict: string; detail: string }
export interface PartIssue { source: 'Electrical' | 'Function' | 'Physical'; code: string; message: string; severity: 'error' | 'warning' | 'info' }

export function checkCards(st: StudioState): CheckCard[] {
  const v = st.validation;
  const warn = v.warnings.filter(w => w.code !== 'W002').length;
  const nc = v.warnings.filter(w => w.code === 'W002').length;
  const electrical: CheckCard = {
    id: 'electrical', title: 'Electrical',
    tone: v.status === 'PASS' ? (warn ? 'warn' : 'ok') : 'bad',
    verdict: v.status === 'PASS' ? 'Valid' : `${v.errors.length} error${v.errors.length === 1 ? '' : 's'}`,
    detail: `${v.checks_run.filter(c => c.outcome !== 'NOT_APPLICABLE').length} rules applied · ${warn} warning${warn === 1 ? '' : 's'}${nc ? ` · ${nc} pin(s) not checkable` : ''}`,
  };
  const f = st.functional;
  const fn: CheckCard = !f.intent_present
    ? { id: 'function', title: 'Function', tone: 'neutral', verdict: 'No requirement', detail: 'No functional intent recorded; behaviour inferred only' }
    : {
      id: 'function', title: 'Function',
      tone: f.status === 'PASS' ? 'ok' : f.status === 'FAIL' ? 'bad' : f.status === 'WARN' ? 'warn' : 'neutral',
      verdict: f.status === 'PASS' ? 'Does what was asked' : f.status === 'FAIL' ? 'Does not do what was asked' : f.status === 'WARN' ? 'Works, with caveats' : 'Not checkable',
      detail: `${f.behaviors.length} behaviour${f.behaviors.length === 1 ? '' : 's'} · ${f.findings.filter(x => x.status === 'FAIL').length} defect(s)`,
    };
  const pv = st.physical?.verification;
  const physical: CheckCard = !st.physical || !pv
    ? { id: 'physical', title: 'Physical build', tone: 'neutral', verdict: 'Not built yet', detail: 'Open the Physical 3D view to build it on a breadboard' }
    : pv.status === 'NOT_APPLICABLE'
      ? { id: 'physical', title: 'Physical build', tone: 'neutral', verdict: 'No physical form', detail: 'Idealised parts only' }
      : {
        id: 'physical', title: 'Physical build', tone: pv.ok ? (pv.status === 'WARN' ? 'warn' : 'ok') : 'bad',
        verdict: pv.ok ? 'Build matches netlist' : 'Build does NOT match',
        detail: `${pv.findings.filter(x => x.severity === 'ERROR').length} errors · ${pv.findings.filter(x => x.severity === 'WARNING').length} data caveats`,
      };
  return [electrical, fn, physical];
}

/** Everything the three checks say about one engineering component. */
export function issuesForPart(st: StudioState, iid: string): PartIssue[] {
  const out: PartIssue[] = [];
  const v = st.validation;
  const hit = (e: { affected_instances: string[]; affected_pins: string[] }) =>
    e.affected_instances.includes(iid) || e.affected_pins.some(p => p.split('.')[0] === iid);
  v.errors.filter(hit).forEach(e => out.push({ source: 'Electrical', code: e.code, message: e.message, severity: 'error' }));
  v.warnings.filter(w => w.code !== 'W002').filter(hit).forEach(e => out.push({ source: 'Electrical', code: e.code, message: e.message, severity: 'warning' }));
  st.functional.findings.filter(f => f.affected_instances.includes(iid) && f.status !== 'PASS')
    .forEach(f => out.push({ source: 'Function', code: f.code, message: f.message, severity: f.status === 'FAIL' ? 'error' : 'warning' }));
  (st.physical?.verification?.findings ?? []).filter(f => f.instances.includes(iid) && f.severity !== 'INFO')
    .forEach(f => out.push({ source: 'Physical', code: f.code, message: f.message, severity: f.severity === 'ERROR' ? 'error' : 'warning' }));
  return out;
}

/** Overall tone for the title bar. */
export function overallTone(cards: CheckCard[]): Tone {
  if (cards.some(c => c.tone === 'bad')) return 'bad';
  if (cards.some(c => c.tone === 'warn')) return 'warn';
  return 'ok';
}
