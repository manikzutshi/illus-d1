// TypeScript mirror of the backend models the studio consumes.
// Source of truth: src/core/models.py, src/schematic/models.py, src/studio/document.py.

export type Orient = 'left' | 'right' | 'up' | 'down';

export interface PinRef { instance_id: string; pin_id: string }
export interface EngineeringComponentInstance {
  instance_id: string;
  component_type: string;
  parameters: Record<string, string>;
  metadata: Record<string, string>;
}
export interface Net { net_id: string; connections: PinRef[]; net_type?: string | null }
export interface EngineeringDesign {
  schema_version: string;
  project_id: string;
  name: string;
  description: string;
  components: EngineeringComponentInstance[];
  nets: Net[];
  assumptions: string[];
  metadata: Record<string, string>;
  [key: string]: unknown;
}

export interface Placement { x: number; y: number; rotation: number; mirror: boolean; locked: boolean; show_all_pins: boolean }
export interface LayoutState { placements: Record<string, Placement>; net_styles: Record<string, 'auto' | 'wire' | 'label'> }
export interface Provenance { source: string; prompt?: string | null; provider?: string | null; model?: string | null; example?: string | null }
export interface StudioDocument { schema_version: string; design: EngineeringDesign; layout: LayoutState; intent?: FunctionalIntent | null; provenance: Provenance; revision: number }

export interface SymbolPrimitive {
  kind: 'line' | 'polyline' | 'polygon' | 'rect' | 'circle' | 'path' | 'text';
  points: number[][]; x: number; y: number; w: number; h: number; r: number; d: string;
  text: string; size: number; anchor: 'start' | 'middle' | 'end'; fill: 'none' | 'outline' | 'body'; width: number;
}
export interface SymbolPin { name: string; x: number; y: number; orientation: Orient; length: number; number?: string | null; hidden: boolean }
export interface SymbolDef { symbol_id: string; kind: 'part' | 'power_flag' | 'ground_flag'; graphics: SymbolPrimitive[]; pins: SymbolPin[]; body: number[]; description: string }

export interface TextItem { x: number; y: number; text: string; size: number; anchor: 'start' | 'middle' | 'end' }
export interface SchematicPin { pin_id: string; symbol_pin: string; name: string; x: number; y: number; orientation: Orient; net_id?: string | null; hidden: boolean }
export interface SchematicComponent {
  instance_id: string; component_type_id: string; reference: string; value: string; symbol_id: string;
  x: number; y: number; rotation: number; mirror: boolean; locked: boolean; pins: SchematicPin[]; bbox: number[];
  ref_label?: TextItem | null; value_label?: TextItem | null; port_text?: string | null; metadata: Record<string, string>;
}
export interface SchematicWire { wire_id: string; net_id: string; x1: number; y1: number; x2: number; y2: number }
export interface SchematicJunction { junction_id: string; net_id: string; x: number; y: number }
export interface SchematicPowerPort { port_id: string; net_id: string; kind: 'power' | 'ground'; text: string; x: number; y: number; direction: Orient; pin_ref?: string | null }
export interface SchematicNetLabel { label_id: string; net_id: string; text: string; x: number; y: number; direction: Orient; pin_ref?: string | null }
export interface NetTrace {
  net_id: string; display_name: string; net_class: 'power' | 'ground' | 'signal'; style: 'wire' | 'label' | 'port';
  pins: string[]; wires: string[]; junctions: string[]; ports: string[]; labels: string[]; voltage?: number | null;
}
export interface SchematicProject {
  schema_version: string; project_id: string; name: string;
  components: SchematicComponent[]; wires: SchematicWire[]; junctions: SchematicJunction[];
  power_ports: SchematicPowerPort[]; net_labels: SchematicNetLabel[];
  text_annotations: { annotation_id: string; x: number; y: number; text: string; size: number; anchor: 'start' | 'middle' | 'end' }[];
  symbols: Record<string, SymbolDef>; nets: Record<string, NetTrace>; bounds: number[];
  stats: { wire_length: number; bends: number; crossings: number; label_fallback_nets: string[]; elapsed_ms: number };
  diagnostics: string[];
}

export interface ValidationIssue {
  code: string; message: string; severity: 'ERROR' | 'WARNING' | 'INFO';
  affected_instances: string[]; affected_pins: string[]; affected_nets: string[]; validator: string;
}
export interface ValidationCheck { code: string; name: string; outcome: 'PASS' | 'FAIL' | 'WARN' | 'NOT_APPLICABLE' }
export interface ValidationResult {
  status: 'PASS' | 'FAIL' | 'UNVALIDATED' | 'NOT_CHECKABLE';
  errors: ValidationIssue[]; warnings: ValidationIssue[]; infos: ValidationIssue[];
  component_count: number; net_count: number; checks_run: ValidationCheck[];
}

export interface ExplanationPart {
  instance_id: string; reference: string; component_type: string; name: string; parameters: Record<string, string>;
  role: string; rationale: string; what_it_does: string; common_mistakes: string[]; physical: boolean;
}
export interface Explanation {
  summary: string; counts: { components: number; nets: number; physical_parts: number };
  parts: ExplanationPart[];
  power_rails: { net_id: string; name: string; kind: string; voltage?: number | null; members: string[] }[];
  signals: { net_id: string; members: string[]; drivers: string[]; receivers: string[] }[];
  checks: ValidationCheck[]; status: string; issues: ValidationIssue[]; suggestions: ValidationIssue[];
  assumptions: string[]; limitations: string[]; concepts: { concept_id: string; name: string }[];
}

export interface OpResult { op: string; kind: 'engineering' | 'presentation'; message: string }
export interface StudioState {
  document: StudioDocument; validation: ValidationResult; functional: FunctionalReport; schematic: SchematicProject;
  verification: { ok: boolean; opens: string[]; shorts: string[]; hygiene: string[] };
  explanation: Explanation; op_results: OpResult[];
}

export interface LibraryItem {
  id: string; name: string; short_name?: string | null; category: string; object_type: string; family?: string | null;
  tags: string[]; aliases: string[]; description: string; pin_count: number; symbol: SymbolDef;
}
export interface ComponentDetails {
  component_type_id: string; name: string; short_name?: string | null; category: string; object_type: string; family?: string | null;
  description: string; tags: string[]; interfaces: string[]; roles: string[];
  pins: { pin_id: string; name: string; direction: string; electrical_type?: string | null; max_voltage?: number | null;
          supply?: string | null; nominal_voltage?: number | null; number?: string | null; description: string }[];
  electrical_properties: Record<string, string>; configurable_parameters: Record<string, string>;
  education?: { summary: string; how_it_works: string; typical_uses: string[]; common_mistakes: string[] } | null;
  physical?: { package?: string | null; mounting?: string | null; breadboard_compatible?: boolean | null; pin_pitch_mm?: number | null } | null;
  design_constraints: { kind: string; pins: string[]; value?: string | null; severity: string; note: string }[];
  concepts: { concept_id: string; name: string; kind: string }[];
}
export interface ExampleInfo { id: string; name: string; description: string; components: number; concept?: string | null }
export interface ProviderInfo { name: string; configured: boolean; default_model: string }
export interface JobEvent { t: number; event: string; message: string }
export interface JobInfo {
  job_id: string; status: 'running' | 'done' | 'failed' | 'clarification'; prompt: string; provider?: string | null; model?: string | null;
  events: JobEvent[]; error?: string | null; clarification?: { reason?: string; missing_choices?: string[] } | null;
  trace_summary: Record<string, unknown>; elapsed_s: number; result?: StudioState;
}

export type EditOp =
  | { op: 'add_component'; component_type: string; instance_id?: string; parameters?: Record<string, string>; x?: number; y?: number }
  | { op: 'remove_component'; instance_id: string }
  | { op: 'set_parameter'; instance_id: string; key: string; value: string | null }
  | { op: 'connect'; a: string; b: string; net_id?: string }
  | { op: 'disconnect'; pin: string }
  | { op: 'delete_net'; net_id: string }
  | { op: 'rename_net'; net_id: string; new_net_id: string }
  | { op: 'set_net_type'; net_id: string; net_type: 'power' | 'ground' | 'signal' | null }
  | { op: 'insert_pattern'; pattern_id: string; prefix?: string; bindings?: Record<string, string> }
  | { op: 'set_design_info'; name?: string; description?: string }
  | { op: 'move_component'; instance_id: string; x: number; y: number }
  | { op: 'rotate_component'; instance_id: string; rotation?: number }
  | { op: 'mirror_component'; instance_id: string }
  | { op: 'set_net_style'; net_id: string; style: 'auto' | 'wire' | 'label' }
  | { op: 'set_show_all_pins'; instance_id: string; value: boolean }
  | { op: 'auto_arrange'; keep_locked: boolean }
  | { op: 'set_intent'; intent: FunctionalIntent | null };

export type Selection =
  | { kind: 'component'; id: string }
  | { kind: 'net'; id: string }
  | { kind: 'pin'; id: string }
  | null;

// ── functional intent & report (src/functional) ──
export interface FunctionalIntent {
  signals: { id: string; role: 'input' | 'output'; quantity: string; description?: string; component_hint?: string | null }[];
  behaviors: { id: string; description?: string;
               when: { input?: string | null; relation: string; threshold?: { kind: string; value?: string | null } | null };
               then: { output: string; effect: string } }[];
  processing: string; required_components: string[]; notes: string[];
}
export type FunctionalStatus = 'PASS' | 'FAIL' | 'WARN' | 'NOT_CHECKABLE';
export interface FunctionalFinding {
  code: string; status: FunctionalStatus; message: string; behavior_id?: string | null; signal_id?: string | null;
  affected_instances: string[]; affected_nets: string[]; affected_pins: string[]; patterns: string[]; repair_hint: string;
}
export interface FunctionalPathStep { instance: string; kind: string; from_node: string; to_node: string; sign: number; pins: string[] }
export interface BehaviorResult {
  behavior_id: string; description: string; status: FunctionalStatus; input_instances: string[]; output_instances: string[];
  path: FunctionalPathStep[]; path_sign?: number | null; required_sign?: number | null; polarity_basis: string;
  decision_instance?: string | null; decision_kind?: string | null; driver_instance?: string | null;
  threshold_set_by?: string | null; explanation: string[];
}
export interface FunctionalReport {
  status: FunctionalStatus; intent_present: boolean; summary: string; behaviors: BehaviorResult[];
  findings: FunctionalFinding[]; bindings: Record<string, string[]>;
  inferred: { input_instance: string; output_instance: string; sign?: number | null; via: string[]; statement: string }[];
  involved_instances: string[]; explanation: string[];
  intent_notes?: string[];
}
export interface Highlight { instances: string[]; nets: string[] }
