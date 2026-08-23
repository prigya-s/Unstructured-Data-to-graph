import { useEffect, useState } from "react";

import {
  PublishJobStatus,
  PublishSummaryResponse,
  getPublishJob,
  getPublishSummary,
  publishGraph,
  publishOntology,
} from "../api/client";
import MetricTile from "../components/MetricTile";

const POLL_INTERVAL_MS = 1500;

interface StepState {
  running: boolean;
  success: string | null;
  error: string | null;
}

const IDLE: StepState = { running: false, success: null, error: null };

async function pollJob(jobId: string): Promise<PublishJobStatus> {
  while (true) {
    const status = await getPublishJob(jobId);
    if (status.status !== "running") return status;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
  }
}

export default function Publish() {
  const [summary, setSummary] = useState<PublishSummaryResponse | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [ontologyState, setOntologyState] = useState<StepState>(IDLE);
  const [graphState, setGraphState] = useState<StepState>(IDLE);

  useEffect(() => {
    loadSummary();
  }, []);

  function loadSummary() {
    getPublishSummary()
      .then(setSummary)
      .catch((err) => setSummaryError(err instanceof Error ? err.message : String(err)));
  }

  async function handlePublishOntology() {
    setOntologyState({ running: true, success: null, error: null });
    try {
      const { job_id } = await publishOntology();
      const status = await pollJob(job_id);
      if (status.status === "succeeded") {
        const stats = (status.result?.stats ?? {}) as {
          total_entities?: number;
          total_relationships?: number;
        };
        setOntologyState({
          running: false,
          success: `Ontology generated with ${stats.total_entities ?? 0} entities and ${
            stats.total_relationships ?? 0
          } relationships.`,
          error: null,
        });
        loadSummary();
      } else {
        setOntologyState({ running: false, success: null, error: status.error ?? "Ontology generation failed." });
      }
    } catch (err) {
      setOntologyState({ running: false, success: null, error: err instanceof Error ? err.message : String(err) });
    }
  }

  async function handlePublishGraph() {
    setGraphState({ running: true, success: null, error: null });
    try {
      const { job_id } = await publishGraph();
      const status = await pollJob(job_id);
      if (status.status === "succeeded") {
        const stats = (status.result ?? {}) as { entities_loaded?: number; relationships_loaded?: number };
        setGraphState({
          running: false,
          success: `Published ${stats.entities_loaded ?? 0} entities and ${
            stats.relationships_loaded ?? 0
          } relationships to the graph database.`,
          error: null,
        });
        loadSummary();
      } else {
        setGraphState({ running: false, success: null, error: status.error ?? "Graph publish failed." });
      }
    } catch (err) {
      setGraphState({ running: false, success: null, error: err instanceof Error ? err.message : String(err) });
    }
  }

  return (
    <div className="page">
      <h1>Publish</h1>
      <p className="muted">
        Only approved entities and relationships are ever published. Rejected, pending, or
        ambiguous entities are never included.
      </p>

      {summaryError && <p className="error">{summaryError}</p>}
      {!summary && !summaryError && <p className="muted">Loading...</p>}

      {summary && (
        <>
          <div className="metric-grid">
            <MetricTile label="Approved Entities" value={summary.approved_entities} />
            <MetricTile label="Approved Relationships" value={summary.approved_relationships} />
            <MetricTile label="Still Pending" value={summary.pending_entities + summary.pending_relationships} />
          </div>

          {(summary.pending_entities > 0 || summary.pending_relationships > 0) && (
            <p className="warning">
              {summary.pending_entities} entity(ies) and {summary.pending_relationships} relationship(s)
              are still pending review. Publishing will only include approved items.
            </p>
          )}
        </>
      )}

      <hr className="section-divider" />
      <h2>Step 1: Generate Approved Ontology</h2>
      <p className="muted">Writes the approved business glossary to the configured lakehouse storage.</p>
      <button type="button" onClick={handlePublishOntology} disabled={ontologyState.running}>
        {ontologyState.running ? "Generating..." : "Generate Approved Ontology"}
      </button>
      {ontologyState.success && <p className="success">{ontologyState.success}</p>}
      {ontologyState.error && <p className="error">{ontologyState.error}</p>}

      <hr className="section-divider" />
      <h2>Step 2: Publish to the Graph Database</h2>
      <p className="muted">
        Loads only approved entities and relationships into the graph database. Previously
        published items are updated in place - safe to run more than once.
      </p>
      <button type="button" onClick={handlePublishGraph} disabled={graphState.running}>
        {graphState.running ? "Publishing..." : "Generate Graph"}
      </button>
      {graphState.success && <p className="success">{graphState.success}</p>}
      {graphState.error && <p className="error">{graphState.error}</p>}
    </div>
  );
}
