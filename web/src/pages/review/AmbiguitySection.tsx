import { useEffect, useState } from "react";

import { CandidateEntityDTO, confirmAmbiguity, dismissAmbiguity, getAmbiguousEntities } from "../../api/client";
import EmptyState from "../../components/EmptyState";

export default function AmbiguitySection() {
  const [entities, setEntities] = useState<CandidateEntityDTO[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = () => {
    getAmbiguousEntities()
      .then(setEntities)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  };

  useEffect(load, []);

  const remove = (id: string) => {
    setEntities((prev) => (prev ? prev.filter((e) => e.id !== id) : prev));
  };

  const withBusy = async (id: string, action: () => Promise<CandidateEntityDTO>) => {
    setBusyId(id);
    setError(null);
    try {
      await action();
      remove(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyId(null);
    }
  };

  if (error) return <p className="error">{error}</p>;
  if (!entities) return <p className="muted">Loading...</p>;

  return (
    <details className="review-section">
      <summary>
        <h2>Ambiguity Resolution ({entities.length})</h2>
      </summary>

      <div className="review-section__body">
        {entities.length === 0 ? (
          <EmptyState>No ambiguous entities to resolve.</EmptyState>
        ) : (
          entities.map((entity) => (
            <AmbiguityRow
              key={entity.id}
              entity={entity}
              busy={busyId === entity.id}
              onConfirm={(chosen) => withBusy(entity.id, () => confirmAmbiguity(entity.id, chosen))}
              onDismiss={() => withBusy(entity.id, () => dismissAmbiguity(entity.id))}
            />
          ))
        )}
      </div>
    </details>
  );
}

const OTHER = "__other__";

function AmbiguityRow({
  entity,
  busy,
  onConfirm,
  onDismiss,
}: {
  entity: CandidateEntityDTO;
  busy: boolean;
  onConfirm: (chosen: string) => void;
  onDismiss: () => void;
}) {
  const [selected, setSelected] = useState<string>(entity.possible_meanings[0] ?? OTHER);
  const [freeText, setFreeText] = useState("");

  const chosen = selected === OTHER ? freeText.trim() : selected;

  return (
    <div className="review-item review-item--ambiguity">
      <h3>{entity.name}</h3>
      <p className="muted">{entity.entity_type}</p>

      {entity.evidence.length > 0 && (
        <div>
          <strong>Evidence from Source Documents</strong>
          {entity.evidence.map((snippet, i) => (
            <blockquote key={i}>{snippet}</blockquote>
          ))}
        </div>
      )}

      <fieldset>
        <legend>Possible meanings</legend>
        {entity.possible_meanings.map((meaning) => (
          <label key={meaning} className="filter-checkbox">
            <input
              type="radio"
              name={`meaning-${entity.id}`}
              value={meaning}
              checked={selected === meaning}
              onChange={() => setSelected(meaning)}
            />
            {meaning}
          </label>
        ))}
        <label className="filter-checkbox">
          <input
            type="radio"
            name={`meaning-${entity.id}`}
            value={OTHER}
            checked={selected === OTHER}
            onChange={() => setSelected(OTHER)}
          />
          None of the above
        </label>
        {selected === OTHER && (
          <input
            type="text"
            placeholder="Describe the correct meaning"
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
          />
        )}
      </fieldset>

      <div className="review-item__actions">
        <button type="button" disabled={busy || !chosen} onClick={() => onConfirm(chosen)}>
          Confirm Meaning
        </button>
        <button type="button" disabled={busy} onClick={onDismiss}>
          Dismiss Ambiguity
        </button>
      </div>

      <p className="muted">
        Confirming a meaning does not approve this entity — go to Entity Review to approve or reject it.
      </p>
    </div>
  );
}
