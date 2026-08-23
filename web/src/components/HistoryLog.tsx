import { HistoryEntryDTO } from "../api/client";

// Same reversed (newest-first) ordering the Streamlit pages rendered via
// st.caption() over reversed(entity.history).
export default function HistoryLog({ history }: { history: HistoryEntryDTO[] }) {
  if (history.length === 0) {
    return <p className="muted history-log__empty">No history yet.</p>;
  }

  return (
    <ul className="history-log">
      {[...history].reverse().map((entry, index) => (
        <li key={index} className="history-log__entry">
          <span className="history-log__timestamp">{entry.timestamp}</span>
          {" · "}
          <span className="history-log__reviewer">{entry.reviewer}</span>
          {" · "}
          <span className="history-log__action">{entry.action}</span>
          {entry.comment && <span className="history-log__comment"> - {entry.comment}</span>}
        </li>
      ))}
    </ul>
  );
}
