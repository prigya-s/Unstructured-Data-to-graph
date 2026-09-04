import { useEffect, useMemo, useState } from "react";

import {
  ClassProposalDTO,
  approveClassProposal,
  getClassProposals,
  rejectClassProposal,
  saveClassProposal,
} from "../../api/client";
import EmptyState from "../../components/EmptyState";
import HistoryLog from "../../components/HistoryLog";
import MetricTile from "../../components/MetricTile";

const DEFAULT_TARGET_DOMAIN = "extensions";
const TERMINAL_STATUSES = new Set(["APPROVED", "REJECTED", "MERGED"]);

export default function ClassProposalReviewSection() {
  const [proposals, setProposals] = useState<ClassProposalDTO[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    getClassProposals()
      .then(setProposals)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  };

  useEffect(load, []);

  const pending = useMemo(
    () => (proposals ?? []).filter((p) => !TERMINAL_STATUSES.has(p.status)),
    [proposals],
  );
  const decided = useMemo(
    () => (proposals ?? []).filter((p) => TERMINAL_STATUSES.has(p.status)),
    [proposals],
  );

  const replaceOne = (updated: ClassProposalDTO) => {
    setProposals((prev) => (prev ? prev.map((p) => (p.id === updated.id ? updated : p)) : prev));
  };

  const withBusy = async (id: string, action: () => Promise<ClassProposalDTO>) => {
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
  if (!proposals) return <p className="muted">Loading...</p>;

  return (
    <details className="review-section">
      <summary>
        <h2>Class Proposals ({pending.length})</h2>
      </summary>

      <div className="review-section__body">
        <p className="muted">
          Concepts the extraction model flagged as not fitting any existing ontology class.
          Approving one writes a new class into the target domain's <code>.ttl</code> file.
        </p>

        {pending.length === 0 ? (
          <EmptyState>No class proposals awaiting review.</EmptyState>
        ) : (
          pending.map((proposal) => (
            <ClassProposalRow
              key={proposal.id}
              proposal={proposal}
              busy={busyId === proposal.id}
              onSave={(suggestedParent, targetDomain, comment) =>
                withBusy(proposal.id, () =>
                  saveClassProposal(proposal.id, {
                    suggested_parent: suggestedParent,
                    target_domain: targetDomain,
                    comment,
                  }),
                )
              }
              onApprove={(comment) => withBusy(proposal.id, () => approveClassProposal(proposal.id, comment))}
              onReject={(comment) => withBusy(proposal.id, () => rejectClassProposal(proposal.id, comment))}
            />
          ))
        )}

        {decided.length > 0 && (
          <details className="review-item">
            <summary>{decided.length} decided proposal(s)</summary>
            <div className="review-item__body">
              {decided.map((proposal) => (
                <div key={proposal.id} className="review-item">
                  <strong>{proposal.proposed_name}</strong> — {proposal.status}
                  {proposal.target_domain && <span className="muted"> ({proposal.target_domain}.ttl)</span>}
                  <HistoryLog history={proposal.history} />
                </div>
              ))}
            </div>
          </details>
        )}
      </div>
    </details>
  );
}

function ClassProposalRow({
  proposal,
  busy,
  onSave,
  onApprove,
  onReject,
}: {
  proposal: ClassProposalDTO;
  busy: boolean;
  onSave: (suggestedParent: string | null, targetDomain: string | null, comment?: string) => void;
  onApprove: (comment?: string) => void;
  onReject: (comment?: string) => void;
}) {
  const [suggestedParent, setSuggestedParent] = useState(proposal.suggested_parent ?? "");
  const [targetDomain, setTargetDomain] = useState(proposal.target_domain ?? DEFAULT_TARGET_DOMAIN);
  const [comment, setComment] = useState("");

  return (
    <details className="review-item" open>
      <summary>
        {proposal.proposed_name} <span className="muted">(NO_FIT)</span> — {proposal.status}
      </summary>

      <div className="review-item__body">
        <div className="metric-grid">
          <MetricTile label="Confidence" value={proposal.confidence.toFixed(2)} />
          <MetricTile label="Source chunks" value={proposal.source_chunks.length} />
        </div>

        {proposal.evidence && (
          <div>
            <strong>Evidence</strong>
            <blockquote>{proposal.evidence}</blockquote>
          </div>
        )}

        <label>
          Suggested parent class
          <input
            type="text"
            value={suggestedParent}
            onChange={(e) => setSuggestedParent(e.target.value)}
            placeholder="(none — will be written as an orphan class)"
          />
        </label>

        <label>
          Target domain file
          <input type="text" value={targetDomain} onChange={(e) => setTargetDomain(e.target.value)} />
        </label>
        <p className="muted">
          Defaults to <code>{DEFAULT_TARGET_DOMAIN}.ttl</code>, a machine-managed file. Only point this at a
          hand-authored domain file if you accept that its comments will be lost on rewrite.
        </p>

        <label>
          Comment
          <input type="text" value={comment} onChange={(e) => setComment(e.target.value)} />
        </label>

        <div className="review-item__actions">
          <button
            type="button"
            disabled={busy}
            onClick={() => onSave(suggestedParent.trim() || null, targetDomain.trim() || null, comment || undefined)}
          >
            Save
          </button>
          <button type="button" disabled={busy} onClick={() => onApprove(comment || undefined)}>
            Approve &amp; write to ontology
          </button>
          <button type="button" disabled={busy} onClick={() => onReject(comment || undefined)}>
            Reject
          </button>
        </div>

        <HistoryLog history={proposal.history} />
      </div>
    </details>
  );
}
