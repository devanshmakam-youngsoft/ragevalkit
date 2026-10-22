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
  excluded: string[];
  budget_miss: boolean;
  /** "weighted" = answer + material; "answer_only" = material was not graded for every version. */
  basis: "weighted" | "answer_only";
  basis_note: string;
  weights: { answer: number; material: number };
  tolerance: number;
  max_time: number | null;
  qualities: Record<string, number | null>;
  considered: number;
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
