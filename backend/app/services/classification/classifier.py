import logging
from pathlib import Path
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).parent / "rules.yaml"


@dataclass
class ClassificationResult:
    primary_domain: str
    secondary_domains: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""
    source: str = "rule"


@dataclass
class DomainRule:
    slug: str
    name_zh: str
    name_en: str
    keywords: list[str]
    arxiv_categories: list[str]


def load_rules() -> list[DomainRule]:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    rules = []
    for d in data.get("domains", []):
        rules.append(DomainRule(
            slug=d["slug"],
            name_zh=d["name_zh"],
            name_en=d["name_en"],
            keywords=[k.lower() for k in d.get("keywords", [])],
            arxiv_categories=d.get("arxiv_categories", []),
        ))
    return rules


class KeywordRuleClassifier:
    def __init__(self):
        self.rules = load_rules()

    def classify(self, title: str, abstract: str, arxiv_categories: list[str]) -> ClassificationResult:
        text = f"{title} {abstract}".lower()
        scores: list[tuple[str, float, str]] = []

        for rule in self.rules:
            score = 0.0
            reasons = []

            kw_hits = sum(1 for kw in rule.keywords if kw in text)
            if kw_hits > 0:
                score += kw_hits * 2.0
                reasons.append(f"{kw_hits} keyword hits")

            if rule.arxiv_categories:
                cat_overlap = set(rule.arxiv_categories) & set(arxiv_categories)
                if cat_overlap:
                    score += 5.0
                    reasons.append(f"category match: {cat_overlap}")

            if score > 0:
                scores.append((rule.slug, score, "; ".join(reasons)))

        scores.sort(key=lambda x: x[1], reverse=True)

        if not scores:
            return ClassificationResult(
                primary_domain="ai-society",
                confidence=0.1,
                reason="no keyword match, default fallback",
                source="rule",
            )

        primary = scores[0]
        max_score = primary[1]
        confidence = min(0.95, max_score / (max_score + 5.0))

        secondary = [s[0] for s in scores[1:3] if s[1] >= max_score * 0.4]

        return ClassificationResult(
            primary_domain=primary[0],
            secondary_domains=secondary,
            tags=[],
            confidence=round(confidence, 3),
            reason=primary[2],
            source="rule",
        )


class ManualOverride:
    def apply(self, paper, primary_category: str | None, secondary_categories: list[str] | None):
        if primary_category:
            paper.primary_category = primary_category
            paper.classification_source = "manual"
            paper.classification_confidence = 1.0
        if secondary_categories is not None:
            paper.secondary_categories = secondary_categories

    def is_manual(self, paper) -> bool:
        return paper.classification_source == "manual"
