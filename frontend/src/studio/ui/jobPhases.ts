// The AI generation as a visible process: phases derived from the job's real events.
// Pure - unit tested. The phases only *describe* what happened; the verdicts shown for
// validation, schematic and physical build come from deterministic results, never from the AI.
import type { JobEvent, JobInfo } from '../types';

export type PhaseState = 'pending' | 'active' | 'done' | 'failed' | 'skipped';
export interface Phase { id: PhaseId; label: string; state: PhaseState; detail: string; who: 'ai' | 'engine' }
export type PhaseId = 'understand' | 'library' | 'calculate' | 'draft' | 'validate' | 'repair' | 'schematic' | 'physical';

const LABELS: Record<PhaseId, [string, 'ai' | 'engine']> = {
  understand: ['Understand the request', 'ai'],
  library: ['Search the component library', 'ai'],
  calculate: ['Calculate component values', 'engine'],
  draft: ['Draft the engineering design', 'ai'],
  validate: ['Validate electrically and functionally', 'engine'],
  repair: ['Repair what the checks rejected', 'ai'],
  schematic: ['Generate and verify the schematic', 'engine'],
  physical: ['Build and verify the breadboard', 'engine'],
};
const ORDER: PhaseId[] = ['understand', 'library', 'calculate', 'draft', 'validate', 'repair', 'schematic', 'physical'];

export function phaseOf(e: JobEvent): PhaseId | null {
  const m = e.message;
  switch (e.event) {
    case 'USER_PROMPT': case 'REQUIREMENTS_EXTRACTED': case 'FUNCTIONAL_INTENT': case 'REQUIREMENTS_EXTRACTION_FAILED':
      return 'understand';
    case 'PROPOSAL_REQUESTED':
      return m.startsWith('Repairing') ? 'repair' : 'draft';
    case 'PROPOSED_DESIGN':
      return 'draft';
    case 'VALIDATION_RESULT': case 'FUNCTIONAL_RESULT':
      return 'validate';
    case 'TOOL_CALL':
      if (m.startsWith('Calculating') || /calculate/i.test(m)) return 'calculate';
      if (m.startsWith('Checking a draft')) return 'validate';
      return 'library';
    default:
      return null;
  }
}

function isFail(e: JobEvent): boolean {
  return /→ FAIL|FAIL\b|functional FAIL|rejected/.test(e.message);
}

export function jobPhases(job: JobInfo | null): Phase[] {
  const phases: Record<PhaseId, Phase> = Object.fromEntries(ORDER.map(id => [id, {
    id, label: LABELS[id][0], who: LABELS[id][1], state: 'pending' as PhaseState, detail: '',
  }])) as Record<PhaseId, Phase>;
  if (!job) return ORDER.map(id => phases[id]);
  const counts: Partial<Record<PhaseId, number>> = {};
  let last: PhaseId | null = null;
  let failures = 0;
  for (const e of job.events) {
    const p = phaseOf(e);
    if (!p) continue;
    counts[p] = (counts[p] ?? 0) + 1;
    if (p === 'validate' && isFail(e)) failures++;
    if (p === 'understand' && e.message.startsWith('Understood intent:')) phases.understand.detail = e.message.replace('Understood intent: ', '');
    if (p === 'understand' && e.message.startsWith('Required behaviour:') && !phases.understand.detail) phases.understand.detail = e.message;
    if (p === 'draft' && e.message.startsWith('Draft design proposed')) phases.draft.detail = e.message.replace('Draft design proposed: ', '');
    last = p;
  }
  const lookups = (counts.library ?? 0);
  if (lookups) phases.library.detail = `${lookups} lookup${lookups > 1 ? 's' : ''}`;
  if (counts.calculate) phases.calculate.detail = `${counts.calculate} calculation${counts.calculate > 1 ? 's' : ''}`;
  if (counts.validate) phases.validate.detail = `${counts.validate} check${counts.validate > 1 ? 's' : ''}${failures ? ` · ${failures} rejected` : ''}`;
  if (counts.repair) phases.repair.detail = `${counts.repair} repair round${counts.repair > 1 ? 's' : ''}`;

  const running = job.status === 'running';
  const reachedIdx = last ? ORDER.indexOf(last) : -1;
  for (const id of ORDER.slice(0, 6)) {
    const i = ORDER.indexOf(id);
    if (counts[id]) phases[id].state = 'done';
    else if (i < reachedIdx && (id === 'calculate' || id === 'repair')) phases[id].state = 'skipped';
    else if (i < reachedIdx) phases[id].state = 'done';
  }
  if (running && last) phases[last].state = 'active';
  if (running && !last) phases.understand.state = 'active';
  if (!counts.repair && !failures && job.status !== 'running') phases.repair.state = 'skipped';

  if (job.status === 'done' && job.result) {
    const r = job.result;
    ORDER.slice(0, 6).forEach(id => { if (phases[id].state === 'pending') phases[id].state = id === 'calculate' || id === 'repair' ? 'skipped' : 'done'; });
    phases.validate.state = r.validation.status === 'PASS' && r.functional.status !== 'FAIL' ? 'done' : 'failed';
    phases.validate.detail = `electrical ${r.validation.status}` + (r.functional.intent_present ? ` · function ${r.functional.status}` : '');
    phases.schematic.state = r.verification.ok ? 'done' : 'failed';
    phases.schematic.detail = `${r.schematic.components.length} symbols · drawing ${r.verification.ok ? 'matches' : 'does NOT match'} the netlist`;
    const pv = r.physical?.verification;
    if (!r.physical || !pv) {
      phases.physical.state = 'skipped';
    } else if (pv.status === 'NOT_APPLICABLE') {
      phases.physical.state = 'skipped';
      phases.physical.detail = 'idealised parts only - no physical form';
    } else {
      phases.physical.state = pv.ok ? 'done' : 'failed';
      phases.physical.detail = `${r.physical.stats.parts_on_board} on the board · ${r.physical.stats.wires} wires · build ${pv.ok ? 'matches' : 'does NOT match'} the netlist`;
    }
  } else if (job.status === 'failed' || job.status === 'clarification') {
    const idx = last ? ORDER.indexOf(last) : 0;
    const stop = ORDER[Math.min(idx, 5)];
    phases[stop].state = job.status === 'failed' ? 'failed' : 'active';
    if (job.status === 'clarification') phases[stop].detail = 'waiting for your answer';
  }
  return ORDER.map(id => phases[id]);
}

export function jobHeadline(job: JobInfo | null): string {
  if (!job) return '';
  if (job.status === 'running') return `Working… ${Math.round(job.elapsed_s)}s`;
  if (job.status === 'done') return 'Design built and verified';
  if (job.status === 'clarification') return 'The AI needs a decision from you';
  return 'Could not reach a valid design';
}
