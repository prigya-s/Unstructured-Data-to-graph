import { GraphPayload } from "../api/client";

// entity_relationships store raw entity ids for source/target (see
// src/review/candidate_graph.py); resolve to names client-side the same way
// app/pages/candidate_graph.py and app/pages/production_graph.py do.
export default function RelationshipTable({ graph }: { graph: GraphPayload }) {
  const nameById = new Map(graph.nodes.entities.map((entity) => [entity.id, entity.name]));

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Source</th>
          <th>Relationship</th>
          <th>Target</th>
        </tr>
      </thead>
      <tbody>
        {graph.relationships.entity_relationships.map((rel, index) => (
          <tr key={index}>
            <td>{nameById.get(rel.source) ?? rel.source}</td>
            <td>{rel.relationship}</td>
            <td>{nameById.get(rel.target) ?? rel.target}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
