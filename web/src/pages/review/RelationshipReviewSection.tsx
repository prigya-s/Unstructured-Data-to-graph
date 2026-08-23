import { useEffect, useMemo, useState } from "react";

import {
  CandidateRelationshipDTO,
  approveRelationship,
  getRelationships,
  rejectRelationship,
  saveRelationship,
} from "../../api/client";
import EmptyState from "../../components/EmptyState";
import HistoryLog from "../../components/HistoryLog";
import MetricTile from "../../components/MetricTile";

const ALL_STATUSES = ["NEW", "PENDING_REVIEW", "APPROVED", "REJECTED", "MERGED"] as const;

export default function RelationshipReviewSection() {
  const [relationships, setRelationships] = useState<CandidateRelationshipDTO[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set(["NEW", "PENDING_REVIEW"]));
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    getRelationships()
      .then(setRelationships)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  };

  useEffect(load, []);

  const types = useMemo(
    () => Array.from(new Set((relationships ?? []).map((r) => r.relationship_type))).sort(),
    [relationships],
  );

  const filtered = useMemo(() => {
    if (!relationships) return [];
    return relationships.filter(
      (r) => statusFilter.has(r.status) && (typeFilter.size === 0 || typeFilter.has(r.relationship_type)),
    );
  }, [relationships, statusFilter, typeFilter]);

  const toggle = (set: Set<string>, setSet: (s: Set<string>) => void, value: string) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setSet(next);
  };

  const replaceOne = (updated: CandidateRelationshipDTO) => {
    setRelationships((prev) => (prev ? prev.map((r) => (r.id === updated.id ? updated : r)) : prev));
  };

  const withBusy = async (id: string, action: () => Promise<CandidateRelationshipDTO>) => {
    setBusyId(id);
    setError(null);
    try {
      replaceOne(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  if (error) return <p className="error">{error}</p>;
  if (!relationships) return <p className="muted">Loading...</p>;

  return (
    <section className="review-section">
      <h2>Relationship Review</h2>

      <div className="filter-group">
        <span className="filter-group__label">Status</span>
        {ALL_STATUSES.map((status) => (
          <label key={status} className="filter-checkbox">
            <input
              type="checkbox"
              checked={statusFilter.has(status)}
              onChange={() => toggle(statusFilter, setStatusFilter, status)}
            />
            {status}
          </label>
        ))}
      </div>

      <div className="filter-group">
        <label className="filter-group__label" htmlFor="relationship-type-filter">
          Relationship type
        </label>
        <select
          id="relationship-type-filter"
          multiple
          value={Array.from(typeFilter)}
          onChange={(e) => setTypeFilter(new Set(Array.from(e.target.selectedOptions).map((o) => o.value)))}
        >
          {types.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
      </div>

      {filtered.length === 0 ? (
        <EmptyState>No relationships match the current filters.</EmptyState>
      ) : (
        filtered.map((relationship) => (
          <RelationshipRow
            key={relationship.id}
            relationship={relationship}
            busy={busyId === relationship.id}
            onSave={(relationshipType, comment) =>
              withBusy(relationship.id, () => saveRelationship(relationship.id, relationshipType, comment))
            }
            onApprove={(comment) => withBusy(relationship.id, () => approveRelationship(relationship.id, comment))}
            onReject={(comment) => withBusy(relationship.id, () => rejectRelationship(relationship.id, comment))}
          />
        ))
      )}
    </section>
  );
}

function RelationshipRow({
  relationship,
  busy,
  onSave,
  onApprove,
  onReject,
}: {
  relationship: CandidateRelationshipDTO;
  busy: boolean;
  onSave: (relationshipType: string, comment?: string) => void;
  onApprove: (comment?: string) => void;
  onReject: (comment?: string) => void;
}) {
  const [relationshipType, setRelationshipType] = useState(relationship.relationship_type);
  const [comment, setComment] = useState("");

  return (
    <details className="review-item">
      <summary>
        {relationship.source_name} → {relationship.relationship_type} → {relationship.target_name} —{" "}
        {relationship.status}
      </summary>

      <div className="review-item__body">
        {relationship.status === "APPROVED" && !relationship.publish_ready && (
          <p className="warning">
            This relationship is approved but won't be published yet — its source or target entity isn't
            approved (or merged into an approved entity).
          </p>
        )}

        {relationship.evidence.length > 0 && (
          <div>
            <strong>Evidence from Source Documents</strong>
            {relationship.evidence.map((snippet, i) => (
              <blockquote key={i}>{snippet}</blockquote>
            ))}
          </div>
        )}

        <div className="metric-grid">
          <MetricTile label="Confidence" value={relationship.confidence_score.toFixed(2)} />
        </div>

        <label>
          Relationship type
          <input type="text" value={relationshipType} onChange={(e) => setRelationshipType(e.target.value)} />
        </label>

        <label>
          Comment
          <input type="text" value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>

        <div className="review-item__actions">
          <button type="button" disabled={busy} onClick={() => onSave(relationshipType, comment || undefined)}>
            Save
          </button>
          <button type="button" disabled={busy} onClick={() => onApprove(comment || undefined)}>
            Approve
          </button>
          <button type="button" disabled={busy} onClick={() => onReject(comment || undefined)}>
            Reject
          </button>
        </div>

        <HistoryLog history={relationship.history} />
      </div>
    </details>
  );
}
