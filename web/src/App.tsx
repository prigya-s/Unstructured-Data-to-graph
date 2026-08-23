import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";

import { getReviewerName, setReviewerName } from "./api/client";
import CandidateGraph from "./pages/CandidateGraph";
import Chat from "./pages/Chat";
import Dashboard from "./pages/Dashboard";
import OntologyPreview from "./pages/OntologyPreview";
import ProductionGraph from "./pages/ProductionGraph";
import Publish from "./pages/Publish";
import Review from "./pages/Review";

// 7-page nav locked in 2026-08-20: Entity Review, Relationship Review, and
// Ambiguity Resolution merged into Review; Graph Impact Analysis and Graph
// Difference View merged into Candidate Graph. Stacked sections, not tabs.
const NAV_ITEMS = [
  { path: "/", label: "Dashboard" },
  { path: "/review", label: "Review" },
  { path: "/candidate-graph", label: "Candidate Graph" },
  { path: "/production-graph", label: "Production Graph" },
  { path: "/ontology-preview", label: "Ontology Preview" },
  { path: "/publish", label: "Publish" },
  { path: "/chat", label: "Ask the Knowledge Graph" },
];

export default function App() {
  const [reviewerName, setReviewerNameState] = useState(getReviewerName());

  function handleReviewerNameChange(name: string) {
    setReviewerNameState(name);
    setReviewerName(name);
  }

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="sidebar__title">Knowledge Graph Review</div>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `sidebar__link${isActive ? " sidebar__link--active" : ""}`}
          >
            {item.label}
          </NavLink>
        ))}
        <div className="sidebar__reviewer">
          <label htmlFor="reviewer-name">Your name</label>
          <input
            id="reviewer-name"
            type="text"
            value={reviewerName}
            onChange={(e) => handleReviewerNameChange(e.target.value)}
          />
        </div>
      </nav>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/review" element={<Review />} />
          <Route path="/candidate-graph" element={<CandidateGraph />} />
          <Route path="/production-graph" element={<ProductionGraph />} />
          <Route path="/ontology-preview" element={<OntologyPreview />} />
          <Route path="/publish" element={<Publish />} />
          <Route path="/chat" element={<Chat />} />
        </Routes>
      </main>
    </div>
  );
}
