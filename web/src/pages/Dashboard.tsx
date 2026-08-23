import { useEffect, useState } from "react";

import { DashboardResponse, getDashboard } from "../api/client";
import EmptyState from "../components/EmptyState";
import MetricTile from "../components/MetricTile";

const STATUS_COLUMNS = ["New", "Pending Review", "Approved", "Rejected", "Merged"];

export default function Dashboard() {
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDashboard()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">Loading...</p>;

  return (
    <div className="page">
      <h1>Dashboard</h1>

      <div className="metric-grid">
        <MetricTile label="Documents processed" value={data.documents_processed} />
        <MetricTile label="Candidate entities" value={data.candidate_entities} />
        <MetricTile label="Candidate relationships" value={data.candidate_relationships} />
        <MetricTile label="Approved entities" value={data.approved_entities} />
        <MetricTile label="Approved relationships" value={data.approved_relationships} />
        <MetricTile label="Rejected" value={data.rejected_total} />
        <MetricTile label="Pending ambiguity" value={data.pending_ambiguous_count} />
      </div>

      <h2>Entities by category and status</h2>
      {data.entities_by_category_status.length === 0 ? (
        <EmptyState>No candidate entities yet.</EmptyState>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Category</th>
              {STATUS_COLUMNS.map((col) => (
                <th key={col}>{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.entities_by_category_status.map((row, index) => (
              <tr key={index}>
                <td>{row.category}</td>
                {STATUS_COLUMNS.map((col) => (
                  <td key={col}>{row[col] ?? 0}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h2>Recent activity</h2>
      {data.recent_activity.length === 0 ? (
        <EmptyState>No review activity yet.</EmptyState>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Subject</th>
              <th>Action</th>
              <th>Reviewer</th>
              <th>Comment</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_activity.map((entry, index) => (
              <tr key={index}>
                <td>{entry.timestamp}</td>
                <td>{entry.subject}</td>
                <td>{entry.action}</td>
                <td>{entry.reviewer}</td>
                <td>{entry.comment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
