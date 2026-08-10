"""
Known ambiguous business terms and their candidate meanings.

Used by candidate_builder to seed CandidateEntity.possible_meanings, and by
the Ambiguity Resolution page to render the choice of meanings. Matching is
whole-token, case-insensitive against the entity name's words - so "Core
Banking System" does not match "bank", but a lone entity named "Bank" does.
"""

from __future__ import annotations

KNOWN_AMBIGUOUS_TERMS: dict[str, list[str]] = {
    "bank": ["Financial Institution", "River Bank"],
    "platform": ["Technology Platform", "Business Division", "Physical Platform"],
    "service": ["Microservice", "Business Service", "Customer Service"],
    "gateway": ["API Gateway", "Network Gateway", "Payment Gateway"],
    "pipeline": ["Data Pipeline", "CI/CD Pipeline", "Business Process Pipeline"],
    "store": ["Database Store", "Retail Store", "Object Store"],
    "policy": ["Business Policy", "Security Policy", "Insurance Policy"],
    "process": ["Business Process", "Operating System Process", "Manufacturing Process"],
    "domain": ["Business Domain", "Network Domain", "Email Domain"],
    "cluster": ["Kubernetes Cluster", "Database Cluster", "Business Cluster"],
}


def possible_meanings_for(name: str) -> list[str]:
    """Return candidate meanings for a term if any whole word in `name`
    (case-insensitive) is a known ambiguous term, else []."""
    tokens = {t.lower() for t in name.split()}
    for term in tokens:
        if term in KNOWN_AMBIGUOUS_TERMS:
            return list(KNOWN_AMBIGUOUS_TERMS[term])
    return []
