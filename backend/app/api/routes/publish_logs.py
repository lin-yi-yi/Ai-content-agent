"""发布记录 + 数据指标 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.draft import Draft
from app.models.publish_log import PublishLog
from app.models.metric import Metric
from app.models.topic import Topic
from app.schemas.publish_log import PublishLogCreate, PublishLogOut
from app.schemas.metric import MetricCreate, MetricOut

router = APIRouter(prefix="/publish-logs", tags=["publish-logs"])


@router.get("", response_model=list[PublishLogOut])
def list_logs(db: Session = Depends(get_db)):
    logs = db.query(PublishLog).order_by(PublishLog.created_at.desc()).limit(50).all()
    return [PublishLogOut.model_validate(l) for l in logs]


@router.post("", response_model=PublishLogOut, status_code=201)
def create_log(body: PublishLogCreate, db: Session = Depends(get_db)):
    draft = db.query(Draft).filter(Draft.id == body.draft_id).first()
    if not draft:
        raise HTTPException(404, "发布包不存在")
    log = PublishLog(**body.model_dump())
    db.add(log)
    topic = db.query(Topic).filter(Topic.id == draft.topic_id).first()
    if topic:
        topic.status = "published"
    db.commit()
    db.refresh(log)
    return PublishLogOut.model_validate(log)


@router.post("/{log_id}/metrics", response_model=MetricOut, status_code=201)
def create_metric(log_id: int, body: MetricCreate, db: Session = Depends(get_db)):
    log = db.query(PublishLog).filter(PublishLog.id == log_id).first()
    if not log:
        raise HTTPException(404, "发布记录不存在")
    metric = Metric(publish_log_id=log_id, **body.model_dump(exclude={"publish_log_id"}))
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return MetricOut.model_validate(metric)


@router.get("/{log_id}/metrics", response_model=list[MetricOut])
def list_metrics(log_id: int, db: Session = Depends(get_db)):
    metrics = db.query(Metric).filter(Metric.publish_log_id == log_id).order_by(Metric.collected_at.desc()).all()
    return [MetricOut.model_validate(m) for m in metrics]
