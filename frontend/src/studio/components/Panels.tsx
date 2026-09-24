import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import type { Studio } from '../store';
import type { ExampleInfo, JobInfo, LibraryItem, ProviderInfo, ValidationIssue } from '../types';
import { SymbolThumbnail } from './SymbolGraphics';
import { viewCenter } from '../geometry';

// ── Validation ────────────────────────────────────────────────────────────

export function ValidationPanel({ studio }: { studio: Studio }) {
  const { state, dispatch } = studio;
  const v = state.studio?.validation;
  const [showChecks, setShowChecks] = useState(false);
  if (!v) return null;
  const focus = (e: ValidationIssue) => {
    if (e.affected_instances[0]) dispatch({ type: 'select', selection: { kind: 'component', id: e.affected_instances[0] } });
    else if (e.affected_pins[0]) dispatch({ type: 'select', selection: { kind: 'pin', id: e.affected_pins[0] } });
    else if (e.affected_nets[0]) dispatch({ type: 'select', selection: { kind: 'net', id: e.affected_nets[0] } });
  };
  const applied = v.checks_run.filter(c => c.outcome !== 'NOT_APPLICABLE');
  const notCheckable = v.warnings.filter(w => w.code === 'W002');
  const Item = ({ e, cls }: { e: ValidationIssue; cls: string }) => (
    <li className={`issue ${cls}`} onClick={() => focus(e)}><span className="code">{e.code}</span>{e.message}</li>
  );
  return (
    <div className="validation">
      <div className={`vstatus ${v.status === 'PASS' ? 'pass' : 'fail'}`}>
        <b>{v.status === 'PASS' ? '✓ Valid design' : '✕ Design has errors'}</b>
        <span>{v.errors.length} errors · {v.warnings.length - notCheckable.length} warnings · {applied.length} checks applied</span>
      </div>
      <ul className="issues">
        {v.errors.map((e, i) => <Item key={`e${i}`} e={e} cls="error" />)}
        {v.warnings.filter(w => w.code !== 'W002').map((e, i) => <Item key={`w${i}`} e={e} cls="warning" />)}
        {v.infos.map((e, i) => <Item key={`i${i}`} e={e} cls="info" />)}
      </ul>
      {notCheckable.length > 0 && (
        <details className="nc"><summary>{notCheckable.length} pin(s) not checkable - missing voltage data</summary>
          <ul>{notCheckable.map((w, i) => <li key={i} onClick={() => focus(w)}>{w.affected_pins.join(', ')}</li>)}</ul>
        </details>
      )}
      <button className="link" onClick={() => setShowChecks(s => !s)}>{showChecks ? 'Hide' : 'Show'} checks performed</button>
      {showChecks && (
        <table className="checks"><tbody>
          {v.checks_run.map(c => <tr key={c.code} className={c.outcome.toLowerCase()}><td className="mono">{c.code}</td><td>{c.name}</td><td>{c.outcome.replace('_', ' ').toLowerCase()}</td></tr>)}
        </tbody></table>
      )}
    </div>
  );
}

// ── Explanation ───────────────────────────────────────────────────────────

export function ExplainPanel({ studio }: { studio: Studio }) {
  const { state, dispatch } = studio;
  const ex = state.studio?.explanation;
  if (!ex) return null;
  return (
    <div className="explain">
      <p className="prose">{ex.summary}</p>
      <h4>Parts and their roles</h4>
      <table className="parts"><tbody>
        {ex.parts.map(p => (
          <tr key={p.instance_id} onClick={() => dispatch({ type: 'select', selection: { kind: 'component', id: p.instance_id } })}>
            <td className="mono">{p.reference}</td>
            <td><b>{p.name}</b>{!p.physical && <span className="chip ideal">idealised</span>}
              <div className="muted">{p.role || p.what_it_does}</div>
              {p.rationale && <div className="muted small">↳ {p.rationale}</div>}</td>
          </tr>
        ))}
      </tbody></table>
      <h4>Power</h4>
      <ul className="bul">{ex.power_rails.map(r => <li key={r.net_id}><b>{r.name}</b> → {r.members.join(', ')}</li>)}</ul>
      <h4>Signals</h4>
      <ul className="bul">{ex.signals.map(sg => (
        <li key={sg.net_id}><span className="mono">{sg.net_id}</span>: {sg.drivers.length ? `${sg.drivers.join(', ')} → ` : ''}{sg.members.filter(m => !sg.drivers.includes(m)).join(', ')}</li>
      ))}</ul>
      {ex.assumptions.length > 0 && <><h4>Assumptions</h4><ul className="bul">{ex.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul></>}
      <h4>What was checked</h4>
      <p className="muted">{ex.checks.filter(c => c.outcome !== 'NOT_APPLICABLE').map(c => c.name).join(' · ')}</p>
      <h4>Limitations</h4>
      <ul className="bul">{ex.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
      {ex.concepts.length > 0 && <><h4>Concepts</h4><div className="chips">{ex.concepts.map(c => <span className="chip concept" key={c.concept_id}>{c.name}</span>)}</div></>}
    </div>
  );
}

// ── Library ───────────────────────────────────────────────────────────────

const CATEGORY_LABEL: Record<string, string> = {
  MICROCONTROLLER: 'Microcontrollers', SENSOR: 'Sensors', PASSIVE_COMPONENT: 'Passives', ACTIVE_COMPONENT: 'Modules & actuators',
  SEMICONDUCTOR: 'Semiconductors', INTEGRATED_CIRCUIT: 'Integrated circuits', POWER_MANAGEMENT: 'Power management',
  POWER_SOURCE: 'Power sources', GROUND_NODE: 'Ground', CONNECTOR: 'Connectors', SWITCH: 'Switches', ACTUATOR: 'Actuators',
  DISPLAY: 'Displays', MEMORY: 'Memory', INTERFACE: 'Interface', LOGIC: 'Logic (idealised)', ROUTING: 'Routing',
};

export function LibraryPanel({ studio }: { studio: Studio }) {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api.library().then(setItems).catch(e => setError(String(e.message ?? e))); }, []);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    const toks = q.split(/\s+/);
    return items.filter(it => {
      const hay = [it.id, it.name, it.short_name, it.family, it.description, ...it.tags, ...it.aliases, it.category].join(' ').toLowerCase();
      return toks.every(t => hay.includes(t));
    });
  }, [items, query]);
  const groups = useMemo(() => {
    const m = new Map<string, LibraryItem[]>();
    filtered.forEach(it => m.set(it.category, [...(m.get(it.category) ?? []), it]));
    return [...m.entries()];
  }, [filtered]);
  const disabled = !studio.state.studio;
  return (
    <div className="library">
      <input className="search" placeholder={`Search ${items.length} parts (e.g. "mosfet", "i2c adc")`} value={query} onChange={e => setQuery(e.target.value)} />
      {error && <div className="err-msg">{error}</div>}
      {disabled && <div className="muted">Open a design (Assistant or Examples) to add parts.</div>}
      {groups.map(([cat, list]) => (
        <div key={cat} className="libgroup">
          <div className="libcat">{CATEGORY_LABEL[cat] ?? cat} <span>{list.length}</span></div>
          {list.map(it => (
            <div key={it.id} className="libitem" title={it.description}>
              <SymbolThumbnail symbol={it.symbol} size={44} />
              <div className="libtext">
                <div className="libname">{it.short_name || it.name}{it.object_type !== 'PHYSICAL' && <span className="chip ideal">ideal</span>}</div>
                <div className="muted small">{it.name}</div>
              </div>
              <button className="add" disabled={disabled} title="Add to design"
                      onClick={() => studio.applyOps([{ op: 'add_component', component_type: it.id, x: viewCenter.x, y: viewCenter.y }])}>＋</button>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// ── Examples ──────────────────────────────────────────────────────────────

export function ExamplesPanel({ studio, onOpened }: { studio: Studio; onOpened: () => void }) {
  const [examples, setExamples] = useState<ExampleInfo[]>([]);
  useEffect(() => { api.examples().then(setExamples).catch(() => setExamples([])); }, []);
  return (
    <div className="examples">
      <p className="muted">Hand-checked reference designs. They load instantly and work offline.</p>
      {examples.map(ex => (
        <button key={ex.id} className="example" onClick={async () => { await studio.load(() => api.openExample(ex.id), `Opened example: ${ex.name}`); onOpened(); }}>
          <b>{ex.name}</b>
          <span className="muted small">{ex.description}</span>
          <span className="chips">{ex.concept && <span className="chip concept">{ex.concept}</span>}<span className="chip">{ex.components} parts</span></span>
        </button>
      ))}
    </div>
  );
}

// ── AI assistant ──────────────────────────────────────────────────────────

const SUGGESTIONS = [
  'An automatic night light that turns on an LED in the dark, powered by a 9 V battery, no microcontroller',
  'Arduino temperature monitor using an LM35 that lights a red LED above a threshold',
  'Control the speed of a small DC motor with PWM from a Raspberry Pi Pico',
  'A 3.3 V supply for an ESP32 from a 9 V battery with a power indicator',
];

export function AssistantPanel({ studio, onGenerated }: { studio: Studio; onGenerated: () => void }) {
  const [prompt, setPrompt] = useState('');
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [model, setModel] = useState('');
  const [job, setJob] = useState<JobInfo | null>(null);
  const timer = useRef<number | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  useEffect(() => { api.providers().then(p => { setProviders(p); const g = p.find(x => x.name === 'gemini'); if (g) setModel(g.default_model); }).catch(() => {}); }, []);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);
  useEffect(() => { logRef.current?.scrollTo(0, logRef.current.scrollHeight); }, [job?.events.length]);

  const configured = providers.some(p => p.configured);
  const running = job?.status === 'running';

  const poll = (id: string) => {
    api.job(id).then(info => {
      setJob(info);
      if (info.status === 'running') timer.current = window.setTimeout(() => poll(id), 1000);
      else if (info.status === 'done' && info.result) {
        const result = info.result;
        void studio.load(async () => result, `Generated by ${info.model ?? 'AI'} and validated`).then(onGenerated);
      }
    }).catch(e => setJob(j => j ? { ...j, status: 'failed', error: String(e.message ?? e) } : j));
  };

  const start = async () => {
    const text = prompt.trim();
    if (!text || running) return;
    try {
      const provider = providers.find(p => p.configured)?.name ?? 'gemini';
      const { job_id } = await api.generate(text, provider, model || undefined);
      setJob({ job_id, status: 'running', prompt: text, events: [], trace_summary: {}, elapsed_s: 0 });
      poll(job_id);
    } catch (e) {
      setJob({ job_id: '', status: 'failed', prompt: text, events: [], trace_summary: {}, elapsed_s: 0, error: String((e as Error).message) });
    }
  };

  return (
    <div className="assistant">
      <p className="muted">Describe a circuit. The AI plans it from the component library; deterministic validation decides whether it is accepted.</p>
      <textarea value={prompt} rows={4} placeholder="e.g. Sound a buzzer when motion is detected, using an ESP32…"
                onChange={e => setPrompt(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) void start(); }} />
      <div className="row">
        <select value={model} onChange={e => setModel(e.target.value)} title="Model">
          {['gemini-3.6-flash', 'gemini-3-flash-preview', 'gemini-3.5-flash', 'gemini-3.1-pro-preview'].map(m => <option key={m} value={m}>{m}</option>)}
        </select>
        <button className="primary" disabled={!prompt.trim() || running || !configured} onClick={() => void start()}>
          {running ? 'Designing…' : 'Generate design'}
        </button>
      </div>
      {!configured && providers.length > 0 && <div className="err-msg">No AI provider key found on the server (set GEMINI_API_KEY and restart). Examples still work offline.</div>}
      {!job && (
        <div className="suggest">
          {SUGGESTIONS.map(s => <button key={s} className="sugg" onClick={() => setPrompt(s)}>{s}</button>)}
        </div>
      )}
      {job && (
        <div className="job">
          <div className={`jobstatus ${job.status}`}>{job.status === 'running' ? `Working… ${job.elapsed_s}s` : job.status}{job.model ? ` · ${job.model}` : ''}</div>
          <div className="log" ref={logRef}>
            {job.events.map((e, i) => <div key={i} className={e.message.includes('FAIL') ? 'fail' : e.message.includes('PASS') || e.event === 'COMPLETED' ? 'pass' : ''}>
              <span className="t">{e.t.toFixed(0)}s</span>{e.message}</div>)}
            {running && <div className="pulse">…</div>}
          </div>
          {job.error && <div className="err-msg">{job.error}</div>}
          {job.clarification && (
            <div className="note"><b>The AI needs clarification:</b> {job.clarification.reason}
              {job.clarification.missing_choices?.length ? <ul className="bul">{job.clarification.missing_choices.map((c, i) => <li key={i}>{c}</li>)}</ul> : null}
              <div className="muted">Refine the prompt and generate again.</div></div>
          )}
          {job.status === 'done' && job.trace_summary && (
            <div className="muted small">{String(job.trace_summary.model_call_count ?? '?')} model calls · {String(job.trace_summary.tool_call_count ?? '?')} tool calls · {String(job.trace_summary.repair_count ?? 0)} repairs</div>
          )}
        </div>
      )}
    </div>
  );
}
