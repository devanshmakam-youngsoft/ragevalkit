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
  }>;
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
