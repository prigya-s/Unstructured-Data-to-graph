import AmbiguitySection from "./review/AmbiguitySection";
import ClassProposalReviewSection from "./review/ClassProposalReviewSection";
import EntityReviewSection from "./review/EntityReviewSection";
import RelationshipReviewSection from "./review/RelationshipReviewSection";

// Merges the former Entity Review, Relationship Review, and Ambiguity
// Resolution pages into one page as stacked sections (not tabs), per the
// 2026-08-20 nav consolidation. ClassProposalReviewSection (Phase 3) was
// stacked in after AmbiguitySection.
export default function Review() {
  return (
    <div className="page">
      <div className="page__header">
        <h1>Review</h1>
      </div>

      <EntityReviewSection />
      <hr className="section-divider" />
      <RelationshipReviewSection />
      <hr className="section-divider" />
      <AmbiguitySection />
      <hr className="section-divider" />
      <ClassProposalReviewSection />
    </div>
  );
}
