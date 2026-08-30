import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_, func

from app.db.session import get_db, SessionLocal
from app.models.entities import Paper, Tag, PaperTag, SyncRun, MetricSnapshot, GithubRepository, SourceRecord
from app.schemas.paper import PaperResponse, PaperListResponse, PaperUpdate, SyncRunResponse, TagResponse, ArxivPaperRaw
from app.services.ingestion.pipeline import SyncPipeline
from app.services.classification.classifier import ManualOverride
from app.services.ranking.attention import compute_attention
from app.services.sources.arxiv_source import ArxivSource

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


@router.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Paper).count()
    hf_matched = (
        db.query(func.count(func.distinct(SourceRecord.paper_id)))
        .filter(SourceRecord.source_name == "huggingface", SourceRecord.status == "matched")
        .scalar()
        or 0
    )
    gh_matched = (
        db.query(func.count(func.distinct(GithubRepository.paper_id))).scalar() or 0
    )
    gdr = db.query(func.min(Paper.published_at), func.max(Paper.published_at)).first()
    last = (
        db.query(SyncRun)
        .filter(SyncRun.status == "completed")
        .order_by(SyncRun.completed_at.desc())
        .first()
    )
    return {
        "total": total,
        "hf_matched": hf_matched,
        "gh_matched": gh_matched,
        "new_in_last_sync": last.new_paper_count if last else 0,
        "last_sync_at": last.completed_at.isoformat() if last and last.completed_at else None,
        "last_status": last.status if last else None,
        "global_date_from": gdr[0].strftime("%Y-%m-%d") if gdr and gdr[0] else None,
        "global_date_to": gdr[1].strftime("%Y-%m-%d") if gdr and gdr[1] else None,
    }


@router.get("/sync-runs", response_model=list[SyncRunResponse])
def list_sync_runs(db: Session = Depends(get_db)):
    return db.query(SyncRun).order_by(SyncRun.started_at.desc()).limit(20).all()


@router.post("/sync/arxiv", response_model=SyncRunResponse)
def trigger_arxiv_sync(
    background_tasks: BackgroundTasks,
    days: int = Query(default=7, ge=1, le=30),
    max_results: int | None = Query(default=None, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    run = SyncRun(
        started_at=datetime.utcnow(),
        status="running",
        categories=["cs.AI", "cs.CL", "cs.LG", "cs.CV"],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    background_tasks.add_task(_bg_sync, run.id, days, max_results)
    return run


def _bg_sync(run_id: int, days: int, max_results: int | None = None) -> None:
    db = SessionLocal()
    try:
        run = db.get(SyncRun, run_id)
        pipeline = SyncPipeline(db)
        pipeline.run_arxiv_sync(days=days, max_results=max_results, sync_run=run)
    except Exception as e:
        logger.exception("background sync failed: %s", e)
        try:
            run = db.get(SyncRun, run_id)
            if run and run.status == "running":
                run.status = "failed"
                run.error_summary = str(e)[:500]
                run.completed_at = datetime.utcnow()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


@router.post("/sync/enrich")
def trigger_enrich(db: Session = Depends(get_db)):
    pipeline = SyncPipeline(db)
    results = pipeline.run_enrich()
    return {"status": "completed", "results": results}


@router.post("/translate/backfill")
def trigger_backfill_translate(
    background_tasks: BackgroundTasks,
    limit: int = Query(default=20, ge=1, le=100),
):
    background_tasks.add_task(_bg_backfill, limit)
    return {"status": "started", "limit": limit}


def _bg_backfill(limit: int) -> None:
    db = SessionLocal()
    try:
        pipeline = SyncPipeline(db)
        n = pipeline.backfill_translate(limit=limit)
        logger.info("backfill translate done: %d papers", n)
    except Exception as e:
        logger.exception("backfill translate failed: %s", e)
    finally:
        db.close()


@router.get("/papers", response_model=PaperListResponse)
def list_papers(
    query: str | None = None,
    domain: str | None = None,
    tag: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    paper_status: str | None = None,
    editorial_status: str | None = None,
    has_code: bool | None = None,
    has_demo: bool | None = None,
    hf_matched: bool | None = None,
    sort: str = "latest",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Paper)

    if query:
        q = q.filter(
            or_(
                Paper.title.ilike(f"%{query}%"),
                Paper.title_zh.ilike(f"%{query}%"),
                Paper.abstract.ilike(f"%{query}%"),
            )
        )
    if domain:
        q = q.filter(Paper.primary_category == domain)
    if paper_status:
        q = q.filter(Paper.paper_status == paper_status)
    if editorial_status:
        q = q.filter(Paper.editorial_status == editorial_status)
    if has_code is not None:
        q = q.filter(Paper.has_code == has_code)
    if has_demo is not None:
        q = q.filter(Paper.has_demo == has_demo)
    if date_from:
        q = q.filter(Paper.published_at >= date_from)
    if date_to:
        q = q.filter(Paper.published_at <= date_to)
    if hf_matched is not None:
        sub = db.query(SourceRecord.paper_id).filter(
            SourceRecord.source_name == "huggingface",
            SourceRecord.status == "matched",
        )
        if hf_matched:
            q = q.filter(Paper.id.in_(sub))
        else:
            q = q.filter(~Paper.id.in_(sub))
    if tag:
        tag_sub = (
            db.query(PaperTag.paper_id)
            .join(Tag)
            .filter(Tag.slug == tag)
        )
        q = q.filter(Paper.id.in_(tag_sub))

    total = q.count()

    dr = (
        q.order_by(None)
        .with_entities(func.min(Paper.published_at), func.max(Paper.published_at))
        .first()
    )
    range_from = dr[0].strftime("%Y-%m-%d") if dr and dr[0] else None
    range_to = dr[1].strftime("%Y-%m-%d") if dr and dr[1] else None

    if sort == "attention":
        q = q.order_by(Paper.modified_at.desc())
    else:
        q = q.order_by(Paper.published_at.desc())

    items = (
        q.options(selectinload(Paper.source_records))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    last_sync = db.query(SyncRun.completed_at).filter(
        SyncRun.status == "completed"
    ).order_by(SyncRun.completed_at.desc()).first()

    return PaperListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=items,
        filters={
            "query": query, "domain": domain, "tag": tag,
            "paper_status": paper_status, "editorial_status": editorial_status,
            "sort": sort,
        },
        last_sync_at=last_sync[0] if last_sync else None,
        date_from=range_from,
        date_to=range_to,
    )


@router.get("/search/arxiv", response_model=list[ArxivPaperRaw])
def search_arxiv_papers(
    query: str = Query(..., min_length=1, max_length=200),
    max_results: int = Query(default=20, ge=1, le=50),
):
    normalized_query = query.strip()
    if not normalized_query:
        raise HTTPException(status_code=422, detail="query must not be blank")

    try:
        return ArxivSource().search(normalized_query, max_results)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("arXiv search failed: %s", exc)
        raise HTTPException(status_code=502, detail="arXiv search failed") from exc


@router.get("/papers/{paper_id}", response_model=PaperResponse)
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.patch("/papers/{paper_id}")
def update_paper(paper_id: int, data: PaperUpdate, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    override = ManualOverride()
    if data.primary_category or data.secondary_categories is not None:
        override.apply(paper, data.primary_category, data.secondary_categories)

    if data.editorial_status:
        paper.editorial_status = data.editorial_status
    if data.title_zh is not None:
        paper.title_zh = data.title_zh
    if data.summary_zh is not None:
        paper.summary_zh = data.summary_zh
    if data.one_line_zh is not None:
        paper.one_line_zh = data.one_line_zh

    db.commit()
    return {"status": "updated", "id": paper_id}


@router.get("/papers/{paper_id}/metrics")
def get_paper_metrics(paper_id: int, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    score = compute_attention(db, paper)
    metrics = db.query(MetricSnapshot).filter(
        MetricSnapshot.paper_id == paper_id
    ).order_by(MetricSnapshot.captured_at.desc()).limit(20).all()

    gh_repos = db.query(GithubRepository).filter(
        GithubRepository.paper_id == paper_id
    ).all()

    source_records = db.query(SourceRecord).filter(
        SourceRecord.paper_id == paper_id
    ).all()

    return {
        "attention": {"total": score.total, "components": score.components},
        "metrics": [
            {"source": m.source_name, "name": m.metric_name, "value": m.metric_value, "at": m.captured_at.isoformat()}
            for m in metrics
        ],
        "github_repos": [
            {"owner": g.owner, "repo": g.repo, "stars": g.stars, "forks": g.forks, "url": g.repository_url}
            for g in gh_repos
        ],
        "source_records": [
            {"source": s.source_name, "status": s.status, "external_id": s.external_id}
            for s in source_records
        ],
    }


@router.post("/papers/{paper_id}/refresh")
def refresh_paper(paper_id: int, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    pipeline = SyncPipeline(db)
    results = pipeline.run_enrich([paper.arxiv_id_base])
    return {"status": "refreshed", "results": results}


@router.get("/domains")
def list_domains(db: Session = Depends(get_db)):
    import yaml
    from pathlib import Path
    rules_path = Path(__file__).parent.parent / "services" / "classification" / "rules.yaml"
    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    domains = []
    for d in data.get("domains", []):
        count = db.query(Paper).filter(Paper.primary_category == d["slug"]).count()
        domains.append({
            "slug": d["slug"],
            "name_zh": d["name_zh"],
            "name_en": d["name_en"],
            "paper_count": count,
        })
    return domains


@router.get("/tags", response_model=list[TagResponse])
def list_tags(status: str = "active", db: Session = Depends(get_db)):
    return db.query(Tag).filter(Tag.status == status).all()


@router.post("/tags", response_model=TagResponse)
def create_tag(
    name_zh: str, name_en: str, slug: str,
    tag_type: str = "topic", primary_domain: str | None = None,
    db: Session = Depends(get_db),
):
    tag = Tag(name_zh=name_zh, name_en=name_en, slug=slug, tag_type=tag_type, primary_domain=primary_domain)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.patch("/tags/{tag_id}")
def update_tag(tag_id: int, status: str | None = None, name_zh: str | None = None, db: Session = Depends(get_db)):
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    if status:
        tag.status = status
    if name_zh:
        tag.name_zh = name_zh
    db.commit()
    return {"status": "updated", "id": tag_id}


@router.get("/editorial/queue")
def editorial_queue(
    status: str = "new",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Paper).filter(Paper.editorial_status == status)
    total = q.count()
    items = (
        q.options(selectinload(Paper.source_records))
        .order_by(Paper.published_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "page": page, "page_size": page_size, "items": [PaperResponse.model_validate(p) for p in items]}


@router.patch("/papers/{paper_id}/editorial-status")
def set_editorial_status(paper_id: int, status: str, db: Session = Depends(get_db)):
    valid = {"new", "reviewing", "candidate", "rejected"}
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    paper.editorial_status = status
    db.commit()
    return {"status": "updated", "id": paper_id, "editorial_status": status}
