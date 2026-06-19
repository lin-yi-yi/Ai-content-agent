"""内容增长 Agent 执行 API"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.agent_run import AgentRun, AgentStep
from app.schemas.agent_run import AgentRunCreate, AgentRunOut, AgentRunResult
from app.services.content_growth_agent import create_agent_run, execute_agent_run, get_agent_run, prepare_retry_agent_run

router = APIRouter(prefix="/agent-runs", tags=["agent-runs"])


@router.post("", response_model=AgentRunResult, status_code=201)
async def create_agent_run_endpoint(
    body: AgentRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """启动一次内容增长 Agent 任务。"""
    result = create_agent_run(body, db)
    background_tasks.add_task(execute_agent_run, result.id)
    return result


@router.get("", response_model=list[AgentRunOut])
def list_agent_runs(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    runs = db.query(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit).all()
    return [_run_out(run, db) for run in runs]


@router.get("/{run_id}", response_model=AgentRunResult)
def get_agent_run_detail(run_id: int, db: Session = Depends(get_db)):
    result = get_agent_run(run_id, db)
    if not result:
        raise HTTPException(404, "Agent 任务不存在")
    return result


@router.post("/{run_id}/retry", response_model=AgentRunResult)
async def retry_agent_run(run_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    result = prepare_retry_agent_run(run_id, db)
    if not result:
        raise HTTPException(404, "Agent 任务不存在")
    if result.status in {"pending", "failed"}:
        background_tasks.add_task(execute_agent_run, run_id)
    return result


def _run_out(run: AgentRun, db: Session) -> AgentRunOut:
    steps = db.query(AgentStep).filter(AgentStep.run_id == run.id).order_by(AgentStep.step_index).all()
    return AgentRunOut(
        id=run.id,
        goal=run.goal,
        mode=run.mode,
        provider=run.provider,
        model_name=run.model_name,
        status=run.status,
        current_step=run.current_step,
        selected_topic_id=run.selected_topic_id,
        draft_id=run.draft_id,
        evaluation_score=run.evaluation_score,
        result_json=run.result_json,
        error_message=run.error_message,
        created_at=run.created_at,
        updated_at=run.updated_at,
        steps=steps,
    )
