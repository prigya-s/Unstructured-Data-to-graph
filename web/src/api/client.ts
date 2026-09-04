// Typed fetch client for api/main.py's routes. Every function name mirrors
// the FastAPI route it calls - see api/routers/*.py.

const REVIEWER_NAME_KEY = "reviewerName";

// Mirrors LocalAuthProvider's free-text "Your name" sidebar box
// (src/providers/auth_provider.py) - same default, same lack of verification.
export function getReviewerName(): string {
  return localStorage.getItem(REVIEWER_NAME_KEY) || "Reviewer";
}

export function setReviewerName(name: string): void {
  localStorage.setItem(REVIEWER_NAME_KEY, name || "Reviewer");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      "X-Reviewer-Name": getReviewerName(),
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export interface NewThreadResponse {
  thread_id: string;
}

export interface ChatStreamDone {
  turn_index: number;
  citations: { chunk_id: string; document_id: string; document_name: string }[];
  entities: { entity_id: string; name: string; entity_type: string }[];
  graph_paths: string[];
  next_steps: string[];
}

export function createChatThread(): Promise<NewThreadResponse> {
  return request<NewThreadResponse>("/api/chat/threads", { method: "POST" });
}

// Consumes api/routers/chat.py's send_message NDJSON stream directly (not
// through request<T>(), which assumes one JSON body) - one
// {"type": "delta"|"done"|"error", ...} object per line. onDelta is called
// with each incremental answer chunk as it arrives; the returned promise
// resolves with the trailing citations/entities/graph_paths/next_steps once
// the stream ends.
export async function sendChatMessageStream(
  threadId: string,
  message: string,
  onDelta: (text: string) => void,
): Promise<ChatStreamDone> {
  const response = await fetch(`/api/chat/threads/${threadId}/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Reviewer-Name": getReviewerName(),
    },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `${response.status} ${response.statusText}`);
  }
  if (!response.body) {
    throw new Error("Streaming is not supported in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done: ChatStreamDone | null = null;

  const handleLine = (line: string) => {
    if (!line) return;
    const event = JSON.parse(line);
    if (event.type === "delta") {
      onDelta(event.text as string);
    } else if (event.type === "done") {
      done = event as ChatStreamDone;
    } else if (event.type === "error") {
      throw new Error(event.detail as string);
    }
  };

  while (true) {
    const { value, done: readerDone } = await reader.read();
    if (readerDone) break;
    buffer += decoder.decode(value, { stream: true });
    let newlineIndex: number;
    while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
      const line = buffer.slice(0, newlineIndex);
      buffer = buffer.slice(newlineIndex + 1);
      handleLine(line);
    }
  }
  handleLine(buffer);

  if (!done) {
    throw new Error("The knowledge graph assistant's response ended unexpectedly.");
  }
  return done;
}

export interface DashboardResponse {
  documents_processed: number;
  candidate_entities: number;
  candidate_relationships: number;
  approved_entities: number;
  approved_relationships: number;
  rejected_total: number;
  pending_ambiguous_count: number;
  entities_by_category_status: Record<string, string | number>[];
  recent_activity: { timestamp: string; subject: string; action: string; reviewer: string; comment: string }[];
}

export function getDashboard(): Promise<DashboardResponse> {
  return request<DashboardResponse>("/api/dashboard");
}

export interface GraphNode {
  id: string;
  name: string;
  type: string;
}

export interface GraphRelationship {
  source: string;
  relationship: string;
  target: string;
}

export interface GraphPayload {
  nodes: { entities: GraphNode[] };
  relationships: { entity_relationships: GraphRelationship[] };
  stats: { entities: number; entity_relationships: number };
}

export function getCandidateGraph(): Promise<GraphPayload> {
  return request<GraphPayload>("/api/candidate-graph");
}

export function getProductionGraph(): Promise<GraphPayload | null> {
  return request<GraphPayload | null>("/api/production-graph");
}

export interface GraphDiffResponse {
  counts: {
    new_entities: number;
    new_relationships: number;
    entities_merged: number;
    removed_total: number;
    entity_count_delta: number;
    relationship_count_delta: number;
  };
  entities_added: { name: string; type: string }[];
  entities_removed: { name: string; type: string }[];
  entities_modified: { name: string; previous_name: string; type: string; previous_type: string }[];
  entities_merged: { name: string; merged_into_name: string }[];
  relationships_added: { source: string; relationship: string; target: string }[];
  relationships_removed: { source: string; relationship: string; target: string }[];
}

export function getGraphDiff(): Promise<GraphDiffResponse> {
  return request<GraphDiffResponse>("/api/graph-diff");
}

export interface OntologyPreviewResponse {
  generated_at: string;
  pending_count: number;
  stats: { total_entities: number; total_relationships: number };
  entities: {
    name: string;
    category: string;
    definition: string;
    confidence_score: number;
    source_documents: string[];
  }[];
  relationships: {
    source_name: string;
    relationship_type: string;
    target_name: string;
    confidence_score: number;
  }[];
}

export function getOntologyPreview(): Promise<OntologyPreviewResponse> {
  return request<OntologyPreviewResponse>("/api/ontology/preview");
}

export function regenerateOntologyPreview(): Promise<OntologyPreviewResponse> {
  return request<OntologyPreviewResponse>("/api/ontology/preview/regenerate", { method: "POST" });
}

export interface HistoryEntryDTO {
  timestamp: string;
  reviewer: string;
  action: string;
  comment: string | null;
}

export interface CandidateEntityDTO {
  id: string;
  name: string;
  entity_type: string;
  definition: string;
  business_meaning: string;
  confidence_score: number;
  status: "NEW" | "PENDING_REVIEW" | "APPROVED" | "REJECTED" | "MERGED";
  evidence: string[];
  source_documents: string[];
  source_chunks: string[];
  possible_meanings: string[];
  history: HistoryEntryDTO[];
  reviewer: string | null;
  review_timestamp: string | null;
  merged_into: string | null;
}

export interface CandidateRelationshipDTO {
  id: string;
  source_entity: string;
  relationship_type: string;
  target_entity: string;
  confidence_score: number;
  status: "NEW" | "PENDING_REVIEW" | "APPROVED" | "REJECTED" | "MERGED";
  evidence: string[];
  history: HistoryEntryDTO[];
  reviewer: string | null;
  review_timestamp: string | null;
  source_name: string;
  target_name: string;
  publish_ready: boolean;
}

export function getEntities(): Promise<CandidateEntityDTO[]> {
  return request<CandidateEntityDTO[]>("/api/entities");
}

export function saveEntity(
  id: string,
  body: { name: string; definition: string; business_meaning: string; comment?: string },
): Promise<CandidateEntityDTO> {
  return request<CandidateEntityDTO>(`/api/entities/${id}/save`, { method: "PATCH", body: JSON.stringify(body) });
}

export function approveEntity(id: string, comment?: string): Promise<CandidateEntityDTO> {
  return request<CandidateEntityDTO>(`/api/entities/${id}/approve`, {
    method: "PATCH",
    body: JSON.stringify({ comment }),
  });
}

export function rejectEntity(id: string, comment?: string): Promise<CandidateEntityDTO> {
  return request<CandidateEntityDTO>(`/api/entities/${id}/reject`, {
    method: "PATCH",
    body: JSON.stringify({ comment }),
  });
}

export function mergeEntity(id: string, targetId: string, comment?: string): Promise<CandidateEntityDTO> {
  return request<CandidateEntityDTO>(`/api/entities/${id}/merge`, {
    method: "PATCH",
    body: JSON.stringify({ target_id: targetId, comment }),
  });
}

export function bulkApproveEntities(ids: string[]): Promise<CandidateEntityDTO[]> {
  return request<CandidateEntityDTO[]>("/api/entities/bulk-approve", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
}

export function getRelationships(): Promise<CandidateRelationshipDTO[]> {
  return request<CandidateRelationshipDTO[]>("/api/relationships");
}

export function saveRelationship(
  id: string,
  relationshipType: string,
  comment?: string,
): Promise<CandidateRelationshipDTO> {
  return request<CandidateRelationshipDTO>(`/api/relationships/${id}/save`, {
    method: "PATCH",
    body: JSON.stringify({ relationship_type: relationshipType, comment }),
  });
}

export function approveRelationship(id: string, comment?: string): Promise<CandidateRelationshipDTO> {
  return request<CandidateRelationshipDTO>(`/api/relationships/${id}/approve`, {
    method: "PATCH",
    body: JSON.stringify({ comment }),
  });
}

export function rejectRelationship(id: string, comment?: string): Promise<CandidateRelationshipDTO> {
  return request<CandidateRelationshipDTO>(`/api/relationships/${id}/reject`, {
    method: "PATCH",
    body: JSON.stringify({ comment }),
  });
}

export function getAmbiguousEntities(): Promise<CandidateEntityDTO[]> {
  return request<CandidateEntityDTO[]>("/api/ambiguity");
}

export function confirmAmbiguity(id: string, chosen: string): Promise<CandidateEntityDTO> {
  return request<CandidateEntityDTO>(`/api/ambiguity/${id}/confirm`, {
    method: "PATCH",
    body: JSON.stringify({ chosen }),
  });
}

export function dismissAmbiguity(id: string): Promise<CandidateEntityDTO> {
  return request<CandidateEntityDTO>(`/api/ambiguity/${id}/dismiss`, { method: "PATCH" });
}

export interface ClassProposalDTO {
  id: string;
  proposed_name: string;
  suggested_parent: string | null;
  evidence: string;
  source_chunks: string[];
  confidence: number;
  status: "NEW" | "PENDING_REVIEW" | "APPROVED" | "REJECTED" | "MERGED";
  target_domain: string | null;
  reviewer: string | null;
  review_timestamp: string | null;
  history: HistoryEntryDTO[];
}

export function getClassProposals(): Promise<ClassProposalDTO[]> {
  return request<ClassProposalDTO[]>("/api/class-proposals");
}

export function saveClassProposal(
  id: string,
  body: { suggested_parent: string | null; target_domain: string | null; comment?: string },
): Promise<ClassProposalDTO> {
  return request<ClassProposalDTO>(`/api/class-proposals/${id}/save`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function approveClassProposal(id: string, comment?: string): Promise<ClassProposalDTO> {
  return request<ClassProposalDTO>(`/api/class-proposals/${id}/approve`, {
    method: "PATCH",
    body: JSON.stringify({ comment }),
  });
}

export function rejectClassProposal(id: string, comment?: string): Promise<ClassProposalDTO> {
  return request<ClassProposalDTO>(`/api/class-proposals/${id}/reject`, {
    method: "PATCH",
    body: JSON.stringify({ comment }),
  });
}

export interface PublishSummaryResponse {
  approved_entities: number;
  approved_relationships: number;
  pending_entities: number;
  pending_relationships: number;
}

export function getPublishSummary(): Promise<PublishSummaryResponse> {
  return request<PublishSummaryResponse>("/api/publish/summary");
}

export interface PublishJobResponse {
  job_id: string;
}

export interface PublishJobStatus {
  status: "running" | "succeeded" | "failed";
  result: Record<string, unknown> | null;
  error: string | null;
}

export function publishOntology(): Promise<PublishJobResponse> {
  return request<PublishJobResponse>("/api/publish/ontology", { method: "POST" });
}

export function publishGraph(): Promise<PublishJobResponse> {
  return request<PublishJobResponse>("/api/publish/graph", { method: "POST" });
}

export function getPublishJob(jobId: string): Promise<PublishJobStatus> {
  return request<PublishJobStatus>(`/api/publish/jobs/${jobId}`);
}

export interface RetrievalTraceCluster {
  chunk_count: number;
  document_names: string[];
}

export interface RetrievalTraceTurnResponse {
  question: string;
  turn_index: number;
  chunk_count: number;
  entity_count: number;
  document_count: number;
  graph_expansion_hops: number;
  page_link_hops: number;
  cypher_full: string;
  cypher_largest_cluster: string;
  connectivity: {
    cluster_count: number;
    clusters: RetrievalTraceCluster[];
  };
}

export function getRetrievalTraceTurn(threadId: string, turnIndex: number): Promise<RetrievalTraceTurnResponse> {
  return request<RetrievalTraceTurnResponse>(`/api/retrieval-trace/threads/${threadId}/turns/${turnIndex}`);
}

export interface RetrievalTraceGraphNode {
  id: string;
  label: "Chunk" | "Document" | "Entity";
  name: string;
}

export interface RetrievalTraceGraphEdge {
  source: string;
  target: string;
  type: "HAS_CHUNK" | "MENTIONS" | "RELATED" | "LEADS_TO";
}

export interface RetrievalTraceGraphResponse {
  nodes: RetrievalTraceGraphNode[];
  edges: RetrievalTraceGraphEdge[];
}

export function getRetrievalTraceGraph(threadId: string, turnIndex: number): Promise<RetrievalTraceGraphResponse> {
  return request<RetrievalTraceGraphResponse>(`/api/retrieval-trace/threads/${threadId}/turns/${turnIndex}/graph`);
}
