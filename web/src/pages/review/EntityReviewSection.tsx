import { useEffect, useMemo, useState } from "react";

import {
  CandidateEntityDTO,
  approveEntity,
  bulkApproveEntities,
  getEntities,
  mergeEntity,
  rejectEntity,
  saveEntity,
} from "../../api/client";
import EmptyState from "../../components/EmptyState";
import HistoryLog from "../../components/HistoryLog";
import MetricTile from "../../components/MetricTile";

const ALL_STATUSES = ["NEW", "PENDING_REVIEW", "APPROVED", "REJECTED", "MERGED"] as const;
const TERMINAL_STATUSES = new Set(["APPROVED", "REJECTED", "MERGED"]);

export default function EntityReviewSection() {
  const [entities, setEntities] = useState<CandidateEntityDTO[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set(["NEW", "PENDING_REVIEW"]));
  const [categoryFilter, setCategoryFilter] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    getEntities()
      .then(setEntities)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  };

  useEffect(load, []);

  const categories = useMemo(
    () => Array.from(new Set((entities ?? []).map((e) => e.entity_type))).sort(),
    [entities],
  );

  const approvedEntities = useMemo(
    () => (entities ?? []).filter((e) => e.status === "APPROVED"),
    [entities],
  );

  const filtered = useMemo(() => {
    if (!entities) return [];
    return entities.filter(
      (e) => statusFilter.has(e.status) && (categoryFilter.size === 0 || categoryFilter.has(e.entity_type)),
    );
  }, [entities, statusFilter, categoryFilter]);

  const bulkApprovableIds = useMemo(
    () => filtered.filter((e) => !TERMINAL_STATUSES.has(e.status)).map((e) => e.id),
    [filtered],
  );

  const toggle = (set: Set<string>, setSet: (s: Set<string>) => void, value: string) => {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setSet(next);
  };

  const replaceOne = (updated: CandidateEntityDTO) => {
    setEntities((prev) => (prev ? prev.map((e) => (e.id === updated.id ? updated : e)) : prev));
  };

  const withBusy = async (id: string, action: () => Promise<CandidateEntityDTO>) => {
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

  const handleBulkApprove = async () => {
    if (bulkApprovableIds.length === 0) return;
    setBusyId("__bulk__");
    setError(null);
    try {
      const updated = await bulkApproveEntities(bulkApprovableIds);
      const byId = new Map(updated.map((e) => [e.id, e]));
      setEntities((prev) => (prev ? prev.map((e) => byId.get(e.id) ?? e) : prev));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  if (error) return <p className="error">{error}</p>;
  if (!entities) return <p className="muted">Loading...</p>;

  return (
    <section className="review-section">
      <h2>Entity Review</h2>

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
        <label className="filter-group__label" htmlFor="entity-category-filter">
          Category
        </label>
        <select
          id="entity-category-filter"
          multiple
          value={Array.from(categoryFilter)}
          onChange={(e) =>
            setCategoryFilter(new Set(Array.from(e.target.selectedOptions).map((o) => o.value)))
          }
        >
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </div>

      <div className="bulk-approve-panel">
        <button type="button" onClick={handleBulkApprove} disabled={bulkApprovableIds.length === 0 || busyId === "__bulk__"}>
          Approve all {bulkApprovableIds.length} filtered pending entities
        </button>
      </div>

      {filtered.length === 0 ? (
        <EmptyState>No entities match the current filters.</EmptyState>
      ) : (
        filtered.map((entity) => (
          <EntityRow
            key={entity.id}
            entity={entity}
            approvedEntities={approvedEntities}
            busy={busyId === entity.id}
            onSave={(name, definition, businessMeaning, comment) =>
              withBusy(entity.id, () => saveEntity(entity.id, { name, definition, business_meaning: businessMeaning, comment }))
            }
            onApprove={(comment) => withBusy(entity.id, () => approveEntity(entity.id, comment))}
            onReject={(comment) => withBusy(entity.id, () => rejectEntity(entity.id, comment))}
            onMerge={(targetId, comment) => withBusy(entity.id, () => mergeEntity(entity.id, targetId, comment))}
          />
        ))
      )}
    </section>
  );
}

function EntityRow({
  entity,
  approvedEntities,
  busy,
  onSave,
  onApprove,
  onReject,
  onMerge,
}: {
  entity: CandidateEntityDTO;
  approvedEntities: CandidateEntityDTO[];
  busy: boolean;
  onSave: (name: string, definition: string, businessMeaning: string, comment?: string) => void;
  onApprove: (comment?: string) => void;
  onReject: (comment?: string) => void;
  onMerge: (targetId: string, comment?: string) => void;
}) {
  const [name, setName] = useState(entity.name);
  const [definition, setDefinition] = useState(entity.definition);
  const [businessMeaning, setBusinessMeaning] = useState(entity.business_meaning);
  const [comment, setComment] = useState("");
  const [mergeTarget, setMergeTarget] = useState("");

  const mergeCandidates = approvedEntities.filter((e) => e.id !== entity.id);

  return (
    <details className="review-item">
      <summary>
        {entity.name} <span className="muted">({entity.entity_type})</span> — {entity.status}
      </summary>

      <div className="review-item__body">
        <div className="metric-grid">
          <MetricTile label="Confidence" value={entity.confidence_score.toFixed(2)} />
        </div>

        <label>
          Name
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
        </label>

        <label>
          Definition
          <textarea value={definition} onChange={(e) => setDefinition(e.target.value)} rows={3} />
        </label>

        <label>
          Business meaning
          <textarea value={businessMeaning} onChange={(e) => setBusinessMeaning(e.target.value)} rows={3} />
        </label>

        {entity.possible_meanings.length > 0 && (
          <p>
            <strong>Related Terms / Possible Meanings:</strong> {entity.possible_meanings.join(", ")}
          </p>
        )}

        {entity.evidence.length > 0 && (
          <div>
            <strong>Evidence from Source Documents</strong>
            {entity.evidence.map((snippet, i) => (
              <blockquote key={i}>{snippet}</blockquote>
            ))}
          </div>
        )}

        {entity.source_documents.length > 0 && (
          <p>
            <strong>Source Documents:</strong> {entity.source_documents.join(", ")}
          </p>
        )}

        {entity.reviewer && (
          <p>
            <strong>Last reviewed by:</strong> {entity.reviewer}
          </p>
        )}

        <label>
          Comment
          <input type="text" value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>

        <div className="review-item__actions">
          <button type="button" disabled={busy} onClick={() => onSave(name, definition, businessMeaning, comment || undefined)}>
            Save
          </button>
          <button type="button" disabled={busy} onClick={() => onApprove(comment || undefined)}>
            Approve
          </button>
          <button type="button" disabled={busy} onClick={() => onReject(comment || undefined)}>
            Reject
          </button>
        </div>

        <div className="merge-panel">
          <select value={mergeTarget} onChange={(e) => setMergeTarget(e.target.value)}>
            <option value="">Select an approved entity to merge into...</option>
            {mergeCandidates.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.name}
              </option>
            ))}
          </select>
          <button type="button" disabled={busy || !mergeTarget} onClick={() => onMerge(mergeTarget, comment || undefined)}>
            Confirm Merge
          </button>
        </div>

        <HistoryLog history={entity.history} />
      </div>
    </details>
  );
}
