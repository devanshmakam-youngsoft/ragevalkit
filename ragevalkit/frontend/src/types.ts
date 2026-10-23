/** Pipeline nodes are data, not code: whatever the RAG app reports shows up here. */
export interface NodeAvg {
  name: string;
  avg: number;
}

export interface VersionSummary {
  version: string | number;
  run_id: string;
  date: string;
  duration_seconds: number;
  dataset: string;
  total_rows: number;
  failed_rows: number;
  avg_answer_marks: number | null;
  avg_material_marks: number | null;
  avg_total_time: number | null;
  avg_keyword_recall: number | null;
  avg_bm25_score: number | null;
  avg_semantic_similarity: number | null;
  comment: string;
  /** Average seconds per node, in pipeline order (only nodes that ran in that version). */
  nodes: NodeAvg[];
  archived?: boolean;
  /** The run was stopped early; it is never recommended or compared as a finished run. */
  stopped?: boolean;
  /** What needs attention and what to try next, written for a non-technical reader. */
  insights?: { pitfalls: string[]; suggestions: string[] };
  /** Short "what changed?" note entered when the run was started. */
  notes?: string;
  /** Names of the test case groups used in this run. */
  group_names?: string[];
  /** Per-group score breakdown (present when the run covered named test-case groups). */
  group_stats?: Record<string, {
    avg_answer_marks: number | null;
    avg_material_marks: number | null;
    avg_total_time: number | null;
    avg_keyword_recall: number | null;
    avg_bm25_score: number | null;
    avg_semantic_similarity: number | null;
    total_rows: number;
    failed_rows?: number;
  }>;
}

/** The server's answer to "which version should ship?" (version ids are strings). */
export interface RecoResult {
  best: string | null;
  reason: string;
  fastest: string | null;
  runner_up: string | null;
  latest_gap: { version: string; gap: number } | null;
  not_comparable: string[];
  /** Why each version in `not_comparable` was left out. */
  not_comparable_detail: Record<string, string>;
  excluded: string[];
  excluded_detail: Record<string, string>;
  budget_miss: boolean;
  /** "weighted" = answer + material; "answer_only" = material was not graded for every version. */
  basis: "weighted" | "answer_only";
  basis_note: string;
  weights: { answer: number; material: number };
  tolerance: number;
  max_time: number | null;
  qualities: Record<string, number | null>;
  considered: number;
  /** How many test cases the comparison was made on: the ones every compared version ran. */
  compared_cases: number | null;
  /** Versions that ran more test cases than were compared (judged on the shared ones only). */
  partial: { version: string; ran: number; compared: number }[];
  /** Each compared version's scores on the shared test cases. */
  scores: Record<string, { answer: number | null; material: number | null; time: number | null; cases: number; quality: number | null }>;
}

/** One group's scores in one run. */
export interface GroupRunStat {
  version: string;
  date: string;
  total_rows: number;
  failed_rows: number;
  avg_answer_marks: number | null;
  avg_material_marks: number | null;
  avg_total_time: number | null;
  quality: number | null;
  stopped: boolean;
}

export interface GroupHistory {
  group: Group;
  run_count: number;
  last: GroupRunStat | null;
  best: GroupRunStat | null;
  reason: string;
  basis_note: string;
  compared_cases?: number | null;
  runs: GroupRunStat[];
}

export interface ResultRow {
  chat_id: string;
  session_id: string | null;
  turn_no: number;
  type: string;
  question: string;
  expected_answer: string;
  intent: string | null;
  generated_answer: string | null;
  material: string | null;
  sources: string[];
  status: string;
  total_time_taken: number | null;
  /** Seconds per node for this question, in execution order. */
  node_timings: Record<string, number>;
  answer_marks: number | null;
  answer_remarks: string | null;
  material_marks: number | null;
  material_remarks: string | null;
  keyword_recall: number | null;
  bm25_score: number | null;
  semantic_similarity: number | null;
  /** Groups this test case belonged to when it ran. */
  groups?: string[];
  /** Free-form notes attached via ragevalkit.note() during the pipeline run. */
  flags?: Record<string, string>;
  /** Whether recorded sources matched expected_sources from the dataset. */
  source_match?: boolean | null;
  matched_sources?: string[];
  missing_sources?: string[];
}

export interface VersionDetail {
  summary: VersionSummary;
  rows: ResultRow[];
}

export interface RunState {
  run_id: string;
  version: string;
  status: "running" | "completed" | "failed" | "stopped";
  total: number;
  done: number;
  current_question: string;
  date: string;
  dataset: string;
  error: string | null;
}

export interface DatasetInfo {
  name: string;
  rows: number;
  chats: number;
  required_columns?: string[];
}

export interface Group {
  group_id: string;
  name: string;
  created_at: string;
  member_count: number;
  /** Set when the group has been deleted (hidden but kept; can be restored). */
  deleted_at?: string | null;
  /** Present on the groups list: how the group has done across non-archived runs. */
  run_count?: number;
  last_run?: GroupRunStat | null;
  best_run?: GroupRunStat | null;
}

/** Backward-compat alias — prefer Group in new code. */
export type Dataset = Group;

/** A group label on a test case. */
export interface GroupRef {
  group_id: string;
  name: string;
}

export interface TestCase {
  tc_id: string;
  chat_id: string;
  turn_no: number;
  question: string;
  expected_answer: string;
  expected_sources?: string;
  type: string;
  status: "active" | "inactive" | "deleted";
  version: number;
  created_at: string;
  updated_at?: string;
  /** Group labels this case carries (a case can have any number). */
  groups: GroupRef[];
  /** Set on cases written from a document: where each answer comes from. */
  origin?: { kind: string; file: string; evidence: GenEvidence[]; model?: string };
}

/** Writing test cases from documents. */
export interface GenCategory { key: string; label: string }

export interface GenLimits {
  max_files: number;
  max_file_mb: number;
  per_category_max: number;
  per_category_default: number;
  turns_default: number;
  categories: GenCategory[];
  model: string;
  ttl_hours: number;
  formats: string[];
}

export interface GenEvidence { quote: string; file: string; page: string; passage?: string }
export interface GenTurn { question: string; expected_answer: string; evidence: GenEvidence[] }
export interface GenItem { item_id: string; category: string; file: string; number: number; chat_id: string; turns: GenTurn[] }

export interface GenBatch {
  batch_id: string;
  status: "running" | "ready" | "failed" | "cancelled" | "interrupted";
  created_at: string;
  expires_at: string;
  options: { per_category: number; categories: string[]; turns: number };
  model: string;
  files: { name: string; pages?: number | null; passages?: number; error?: string }[];
  total_tasks: number;
  done_tasks: number;
  items: GenItem[];
  errors: { category: string; file: string; reason: string }[];
  error: string;
}

/** A batch without its items: what the "waiting for review" banner needs. */
export type GenSummary = Omit<GenBatch, "items"> & { item_count: number; case_count: number; by_category: Record<string, number> };

/** The fields a test case import understands, and which file column feeds each. */
export type ImportMapping = Record<string, string | null>;

export interface ImportProblem {
  /** Row number as shown in the spreadsheet (the header is row 1). */
  row: number;
  reason: string;
  cells: Record<string, string>;
}

export interface ImportPreview {
  filename: string;
  sheets: string[];
  sheet: string | null;
  columns: string[];
  mapping: ImportMapping;
  fields: string[];
  field_labels: Record<string, string>;
  ignored_columns: string[];
  question_missing: boolean;
  auto_chat: boolean;
  auto_turn: boolean;
  total_rows: number;
  counts: { new: number; update: number; unchanged: number; skipped_deleted: number; problem: number };
  slot_conflicts: number;
  sample: { row: number; chat_id: string; turn_no: number; question: string; expected_answer: string; groups: string[]; outcome: string }[];
  problems: ImportProblem[];
  group_names_in_file: string[];
  new_group_names: string[];
}

export interface ImportResult {
  new: number;
  updated: number;
  unchanged: number;
  skipped_deleted: number;
  slot_conflicts: number;
  labelled: number;
  groups_created: string[];
  problems: number;
  problem_rows: ImportProblem[];
  columns: string[];
}

/** What a run should execute: groups and/or individually picked test cases. */
export interface RunSelection {
  groupIds?: string[];
  tcIds?: string[];
  statusFilter?: string;
  includeContext?: boolean;
}

export interface RunPreview {
  selected: number;
  context: number;
  total: number;
  missing: number;
  group_names: string[];
  collisions: { chat_id: string; turn_no: number; tc_ids: string[] }[];
}
