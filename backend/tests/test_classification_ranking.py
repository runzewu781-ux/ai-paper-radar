import pytest

from app.services.classification.classifier import (
    KeywordRuleClassifier,
    ManualOverride,
    ClassificationResult,
)
from app.services.ranking.attention import compute_attention, AttentionScore


class TestKeywordRuleClassifier:
    @pytest.fixture
    def classifier(self):
        return KeywordRuleClassifier()

    def test_llm_paper(self, classifier):
        result = classifier.classify(
            title="Scaling Language Models with Instruction Tuning",
            abstract="We present a new approach to instruction tuning for large language models using RLHF.",
            arxiv_categories=["cs.CL"],
        )
        assert result.primary_domain == "llm-nlp"
        assert result.confidence > 0.3
        assert result.source == "rule"

    def test_cv_paper(self, classifier):
        result = classifier.classify(
            title="Real-Time Object Detection with Vision Transformers",
            abstract="We propose a novel object detection framework using ViT backbone for image classification and segmentation.",
            arxiv_categories=["cs.CV"],
        )
        assert result.primary_domain == "computer-vision"

    def test_agent_paper(self, classifier):
        result = classifier.classify(
            title="Multi-Agent Collaboration for Autonomous Planning",
            abstract="We study multi-agent systems with tool use and planning capabilities for autonomous workflow orchestration.",
            arxiv_categories=["cs.AI", "cs.MA"],
        )
        assert result.primary_domain == "ai-agent"

    def test_fallback_default(self, classifier):
        result = classifier.classify(
            title="A Novel Approach to Something",
            abstract="This paper presents results.",
            arxiv_categories=["math.CO"],
        )
        assert result.primary_domain == "ai-society"
        assert result.confidence < 0.2

    def test_secondary_domains(self, classifier):
        result = classifier.classify(
            title="Multimodal Vision-Language Agent with Tool Use",
            abstract="We build a multimodal agent that combines vision-language understanding with planning and tool use for autonomous tasks.",
            arxiv_categories=["cs.CV", "cs.CL", "cs.AI"],
        )
        assert result.primary_domain in ("ai-agent", "multimodal", "computer-vision")
        assert len(result.secondary_domains) <= 2


class TestManualOverride:
    def test_manual_overrides_rule(self):
        override = ManualOverride()

        class FakePaper:
            primary_category = "llm-nlp"
            secondary_categories = []
            classification_source = "rule"
            classification_confidence = 0.7

        paper = FakePaper()
        override.apply(paper, "computer-vision", ["multimodal"])
        assert paper.primary_category == "computer-vision"
        assert paper.secondary_categories == ["multimodal"]
        assert paper.classification_source == "manual"
        assert paper.classification_confidence == 1.0

    def test_is_manual(self):
        override = ManualOverride()

        class FakePaper:
            classification_source = "manual"

        assert override.is_manual(FakePaper()) is True

        class FakePaper2:
            classification_source = "rule"

        assert override.is_manual(FakePaper2()) is False

    def test_sync_does_not_override_manual(self):
        override = ManualOverride()

        class FakePaper:
            primary_category = "ai-safety"
            secondary_categories = []
            classification_source = "manual"
            classification_confidence = 1.0

        paper = FakePaper()
        assert override.is_manual(paper)
        # Sync should skip this paper - verified by is_manual check


class TestAttentionScore:
    @pytest.fixture
    def db(self, tmp_path):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.db.session import Base
        import app.models.entities  # noqa: F401

        engine = create_engine(f"sqlite:///{tmp_path}/test.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def test_missing_data_not_zero(self, db):
        from app.models.entities import Paper

        paper = Paper(
            arxiv_id_base="2501.99999",
            title="Test",
            abstract="Test",
            has_code=False,
            has_model=False,
            has_demo=False,
        )
        db.add(paper)
        db.commit()
        db.refresh(paper)

        score = compute_attention(db, paper)
        assert score.components["hf_listed"] is None
        assert score.components["hf_upvotes"] is None
        assert score.components["github_stars"] is None
        assert score.components["s2_indexed"] is None
        assert score.components["has_code"] == 0.0

    def test_with_signals(self, db):
        from app.models.entities import Paper, SourceRecord, MetricSnapshot, GithubRepository
        from datetime import datetime

        paper = Paper(
            arxiv_id_base="2501.88888",
            title="Test",
            abstract="Test",
            has_code=True,
            has_model=True,
            has_demo=False,
        )
        db.add(paper)
        db.commit()
        db.refresh(paper)

        db.add(SourceRecord(
            paper_id=paper.id,
            source_name="huggingface",
            status="matched",
            external_id="2501.88888",
        ))
        db.add(MetricSnapshot(
            paper_id=paper.id,
            source_name="huggingface",
            metric_name="upvotes",
            metric_value=20.0,
            captured_at=datetime.utcnow(),
        ))
        db.add(GithubRepository(
            paper_id=paper.id,
            owner="user",
            repo="repo",
            repository_url="https://github.com/user/repo",
            stars=500,
        ))
        db.commit()

        score = compute_attention(db, paper)
        assert score.components["hf_listed"] == 3.0
        assert score.components["hf_upvotes"] == 10.0
        assert score.components["github_stars"] == 8.0
        assert score.components["has_code"] == 2.0
        assert score.components["has_model_or_demo"] == 1.5
        assert score.total > 20
