import { useEffect, useState } from "react";

import { OntologyPreviewResponse, getOntologyPreview, regenerateOntologyPreview } from "../api/client";
import EmptyState from "../components/EmptyState";
import MetricTile from "../components/MetricTile";

function pct(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export default function OntologyPreview() {
  const [data, setData] = useState<OntologyPreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  useEffect(() => {
    getOntologyPreview()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  async function handleRegenerate() {
    setRegenerating(true);
    setError(null);
    try {
      setData(await regenerateOntologyPreview());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRegenerating(false);
    }
  }

  return (
    <div className="page">
      <div className="page__header">
        <h1>Ontology Preview</h1>
        <button type="button" onClick={handleRegenerate} disabled={regenerating}>
          Regenerate Preview
        </button>
      </div>
      <p className="muted">
        This is what will be published as the shared business ontology - only approved entities
        and relationships appear here.
      </p>

      {error && <p className="error">{error}</p>}
      {!data && !error && <p className="muted">Loading...</p>}

      {data && (
        <>
          {data.pending_count > 0 && (
            <p className="warning">
              {data.pending_count} entity(ies)/relationship(s) are still pending review and will
              not be included below.
            </p>
          )}

          <p className="muted">Last generated: {data.generated_at}</p>

          <div className="metric-grid">
            <MetricTile label="Approved entities" value={data.stats.total_entities} />
            <MetricTile label="Approved relationships" value={data.stats.total_relationships} />
          </div>

          <h2>Entities</h2>
          {data.entities.length === 0 ? (
            <EmptyState>No approved entities yet.</EmptyState>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Entity name</th>
                  <th>Category</th>
                  <th>Definition</th>
                  <th>Confidence</th>
                  <th>Source documents</th>
                </tr>
              </thead>
              <tbody>
                {data.entities.map((entity, index) => (
                  <tr key={index}>
                    <td>{entity.name}</td>
                    <td>{entity.category}</td>
                    <td>{entity.definition}</td>
                    <td>{pct(entity.confidence_score)}</td>
                    <td>{entity.source_documents.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <h2>Relationships</h2>
          {data.relationships.length === 0 ? (
            <EmptyState>No approved relationships yet.</EmptyState>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source term</th>
                  <th>Relationship</th>
                  <th>Target term</th>
                  <th>Confidence</th>
                </tr>
              </thead>
              <tbody>
                {data.relationships.map((rel, index) => (
                  <tr key={index}>
                    <td>{rel.source_name}</td>
                    <td>{rel.relationship_type}</td>
                    <td>{rel.target_name}</td>
                    <td>{pct(rel.confidence_score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
