export type Citation = {
  doc_id: string;
  version_date: string;
  chunk_id: string;
  quote: string;
};
export type Document = {
  doc_id: string;
  title: string;
  version_date: string;
  scope: string | null;
  content: string;
  chunks: { chunk_id: string; text: string }[];
};
export type Answer = {
  status: string;
  answer: string;
  mode: string;
  dataset_version: string;
  citations: Citation[];
  claims: { text: string; citation_indices: number[] }[];
  conflicts: {
    topic: string;
    explanation: string;
    citation_indices: number[];
  }[];
  knowledge_gaps: string[];
  clarification: string | null;
  stop_reason: string;
  steps: number;
  tool_calls: number;
};
export type Run = {
  id: string;
  question: string;
  status: string;
  mode: string;
  scenario: string;
  result: Answer | null;
};
export type Conversation = { id: string; title: string; runs?: Run[] };
export type Scenario = {
  id: string;
  title: string;
  question: string;
  description: string;
  expected: string;
  history_question?: string;
};
export type Trace = {
  sequence: number;
  kind: string;
  action?: string;
  reason?: string;
  summary?: string;
  status?: string;
  code?: string;
  supported?: boolean;
  arguments?: unknown;
  output?: unknown;
  issues?: string[];
  duration_ms?: number;
};
