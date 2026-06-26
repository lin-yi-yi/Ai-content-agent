import { useEffect, useMemo, useState } from 'react';
import { AgentRun, AgentRunCreate, AgentRunResult, KnowledgeBase, api } from '../api/client';

interface Props {
  onNavigate: (page: string) => void;
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待执行',
  running: '执行中',
  completed: '已完成',
  skipped: '已跳过',
  failed: '失败',
};

interface AgentDecisionAction {
  priority?: string;
  label?: string;
  reason?: string;
  target?: string;
}

interface AgentDecision {
  summary?: string;
  decision_status?: string;
  confidence?: string;
  selected_topic?: {
    verification_status?: string;
    reason?: string;
  };
  quality_gate?: {
    score?: number;
    threshold?: number;
    publish_readiness?: string;
    passed?: boolean;
    strengths?: string[];
  };
  revision?: {
    triggered?: boolean;
    changes?: string[];
    reason?: string;
  };
  why_this_topic?: string[];
  manual_review_focus?: string[];
  next_actions?: AgentDecisionAction[];
}

interface RagContextHit {
  chunk_id?: number;
  title?: string;
  source_uri?: string;
  content?: string;
  score?: number;
}

interface RagContext {
  enabled?: boolean;
  evidence_status?: string;
  knowledge_base_id?: number;
  knowledge_base_name?: string;
  coverage?: {
    top_score?: number;
    evidence_count?: number;
    distinct_documents?: number;
    status?: string;
  };
  hits?: RagContextHit[];
}

export default function AgentWorkbenchPage({ onNavigate }: Props) {
  const [form, setForm] = useState<AgentRunCreate>({
    goal: '普通人怎么用 AI 自动化副业内容',
    mode: 'inspiration',
    research_depth: 'quick',
    target_audience: 'AI 新手 / 自媒体人',
    viewpoint: '先跑通半自动流程，再谈全自动',
    personal_case: '',
    content_type: 'auto',
    source_urls: [],
    provider: 'local',
	    model: '',
	    auto_score: true,
	    use_rag: false,
	    knowledge_base_id: null,
	    rag_top_k: 5,
	    rag_min_score: 0.08,
	  });
	  const [sourceUrlsText, setSourceUrlsText] = useState('');
	  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
	  const [run, setRun] = useState<AgentRunResult | null>(null);
  const [history, setHistory] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(false);

  const loadHistory = () => {
    api.listAgentRuns(12).then(setHistory).catch(() => setHistory([]));
  };

	  useEffect(() => {
	    loadHistory();
	    api.listKnowledgeBases().then(items => {
	      setKnowledgeBases(items);
	      if (items[0]) {
	        setForm(prev => prev.knowledge_base_id ? prev : { ...prev, knowledge_base_id: items[0].id });
	      }
	    }).catch(() => setKnowledgeBases([]));
	  }, []);

  useEffect(() => {
    if (!run || !['pending', 'running'].includes(run.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getAgentRun(run.id);
        setRun(next);
        if (!['pending', 'running'].includes(next.status)) loadHistory();
      } catch {
        // 页面轮询失败不打断用户，下一轮继续尝试。
      }
    }, 1200);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.status]);

  const stepProgress = useMemo(() => {
    const total = run?.steps.length || 0;
    const completed = run?.steps.filter(step => ['completed', 'skipped'].includes(step.status)).length || 0;
    return { total, completed };
  }, [run]);

  const handleStart = async () => {
    if (!form.goal.trim()) return;
    setLoading(true);
    try {
      const result = await api.createAgentRun({
        ...form,
        source_urls: sourceUrlsText.split(/\n+/).map(item => item.trim()).filter(Boolean),
      });
      setRun(result);
      loadHistory();
    } catch (e) {
      alert('Agent 执行失败: ' + e);
    }
    setLoading(false);
  };

  const handleRetry = async () => {
    if (!run) return;
    setLoading(true);
    try {
      const result = await api.retryAgentRun(run.id);
      setRun(result);
      loadHistory();
    } catch (e) {
      alert('重试失败: ' + e);
    }
    setLoading(false);
  };

  const handleLoadRun = async (id: number) => {
    setLoading(true);
    try {
      setRun(await api.getAgentRun(id));
    } catch (e) {
      alert('读取 Agent 任务失败: ' + e);
    }
    setLoading(false);
  };

  const evaluation = run?.evaluation || {};
  const issues = Array.isArray(evaluation.issues) ? evaluation.issues as Array<{ message?: string; level?: string; card_page?: number }> : [];
  const ideas = ((run?.result_json?.topic_ideas as Record<string, unknown> | undefined)?.ideas || []) as Array<Record<string, unknown>>;
  const decision = (run?.result_json?.agent_decision || null) as AgentDecision | null;
	  const decisionActions = Array.isArray(decision?.next_actions) ? decision.next_actions : [];
	  const reviewFocus = Array.isArray(decision?.manual_review_focus) ? decision.manual_review_focus : [];
	  const whyThisTopic = Array.isArray(decision?.why_this_topic) ? decision.why_this_topic : [];
	  const revisionChanges = Array.isArray(decision?.revision?.changes) ? decision.revision.changes : [];
	  const ragContext = (run?.result_json?.rag_context || null) as RagContext | null;
	  const ragHits = Array.isArray(ragContext?.hits) ? ragContext.hits : [];

  return (
    <div>
      <div className="page-header">
        <h1>Agent 工作台</h1>
        <p>输入一个内容目标，让 Agent 串起选题、发布包、卡片和质量评分</p>
      </div>

      <div className="agent-layout">
        <section className="agent-panel">
          <div className="agent-panel__header">
            <h2>内容目标</h2>
            <span className="badge" style={{ background: '#eef2ff', color: '#4338ca' }}>v0.3-C</span>
          </div>
          <div className="form-group">
            <label>我想做什么内容 *</label>
            <textarea
              value={form.goal}
              onChange={e => setForm({ ...form, goal: e.target.value })}
              rows={3}
              placeholder="例如：普通人怎么用 AI 自动化副业内容"
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>模式</label>
              <select value={form.mode} onChange={e => setForm({ ...form, mode: e.target.value as 'research' | 'inspiration' })}>
                <option value="inspiration">主题灵感创作</option>
                <option value="research">AI 自动调研</option>
              </select>
            </div>
            <div className="form-group">
              <label>调研深度</label>
              <select value={form.research_depth} onChange={e => setForm({ ...form, research_depth: e.target.value as 'quick' | 'deep' })}>
                <option value="quick">快速模式</option>
                <option value="deep">深度模式</option>
              </select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>目标人群</label>
              <input
                value={form.target_audience || ''}
                onChange={e => setForm({ ...form, target_audience: e.target.value })}
                placeholder="AI 新手 / 自媒体人"
              />
            </div>
            <div className="form-group">
              <label>模型</label>
              <select value={form.provider} onChange={e => setForm({ ...form, provider: e.target.value })}>
                <option value="local">local 规则模型</option>
                <option value="doubao">豆包 / 火山方舟</option>
                <option value="deepseek">DeepSeek</option>
              </select>
            </div>
          </div>
          <div className="form-group">
            <label>想表达的观点</label>
            <textarea
              value={form.viewpoint || ''}
              onChange={e => setForm({ ...form, viewpoint: e.target.value })}
              rows={2}
              placeholder="例如：先跑通半自动流程，再谈全自动"
            />
          </div>
          <div className="form-group">
            <label>个人经验 / 案例</label>
            <textarea
              value={form.personal_case || ''}
              onChange={e => setForm({ ...form, personal_case: e.target.value })}
              rows={2}
              placeholder="可选。没有真实案例也可以留空"
            />
          </div>
          {form.mode === 'research' && (
            <div className="form-group">
              <label>补充来源链接</label>
              <textarea
                value={sourceUrlsText}
                onChange={e => setSourceUrlsText(e.target.value)}
                rows={3}
                placeholder="可选，每行一个公开网页 / GitHub / 工具官网链接"
              />
            </div>
          )}
	          <label className="checkbox-row">
	            <input
	              type="checkbox"
	              checked={Boolean(form.auto_score)}
	              onChange={e => setForm({ ...form, auto_score: e.target.checked })}
	            />
	            <span>自动评分推荐选题</span>
	          </label>
	          <div className="agent-rag-config">
	            <label className="checkbox-row">
	              <input
	                type="checkbox"
	                checked={Boolean(form.use_rag)}
	                onChange={e => setForm({ ...form, use_rag: e.target.checked })}
	              />
	              <span>启用知识库检索</span>
	            </label>
	            {form.use_rag && (
	              <div className="form-row">
	                <div className="form-group">
	                  <label>知识库</label>
	                  <select
	                    value={form.knowledge_base_id || ''}
	                    onChange={e => setForm({ ...form, knowledge_base_id: e.target.value ? Number(e.target.value) : null })}
	                  >
	                    {knowledgeBases.map(item => (
	                      <option key={item.id} value={item.id}>#{item.id} {item.name}</option>
	                    ))}
	                  </select>
	                </div>
	                <div className="form-group">
	                  <label>证据数量</label>
	                  <select value={form.rag_top_k || 5} onChange={e => setForm({ ...form, rag_top_k: Number(e.target.value) })}>
	                    <option value={3}>3 条</option>
	                    <option value={5}>5 条</option>
	                    <option value={8}>8 条</option>
	                  </select>
	                </div>
	              </div>
	            )}
	          </div>
	          <button className="btn btn-primary agent-start-button" onClick={handleStart} disabled={loading || !form.goal.trim()}>
            {loading ? '任务创建中...' : '开始生成完整发布包'}
          </button>
        </section>

        <aside className="agent-history">
          <h3>最近任务</h3>
          {history.length === 0 ? (
            <div className="empty" style={{ padding: 16 }}>暂无执行记录</div>
          ) : history.map(item => (
            <button key={item.id} className={`agent-history-item ${run?.id === item.id ? 'active' : ''}`} onClick={() => handleLoadRun(item.id)}>
              <strong>#{item.id} {item.goal}</strong>
              <span>{STATUS_LABELS[item.status] || item.status} · {item.evaluation_score ?? '-'}分</span>
            </button>
          ))}
        </aside>
      </div>

      {run && (
        <section className="agent-result">
          <div className="agent-result__header">
            <div>
              <h2>Agent Run #{run.id}</h2>
              <p>{STATUS_LABELS[run.status] || run.status} · {stepProgress.completed}/{stepProgress.total} 步完成</p>
            </div>
            <div className="agent-result__actions">
              {run.status === 'failed' && (
                <button className="btn btn-primary" onClick={handleRetry} disabled={loading}>重试失败步骤</button>
              )}
              <div className={`agent-run-status ${run.status}`}>{STATUS_LABELS[run.status] || run.status}</div>
            </div>
          </div>

          <div className="agent-step-grid">
            {run.steps.map(step => (
              <div key={step.id} className={`agent-step-card ${step.status}`}>
                <span>{String(step.step_index).padStart(2, '0')}</span>
                <strong>{step.label}</strong>
                <small>{STATUS_LABELS[step.status] || step.status}</small>
                {step.error_message && <em>{step.error_message}</em>}
              </div>
            ))}
	          </div>

	          {ragContext?.enabled && (
	            <div className={`agent-rag-evidence ${ragContext.evidence_status === 'sufficient' ? 'ok' : 'weak'}`}>
	              <div className="agent-rag-evidence__header">
	                <div>
	                  <span>知识库证据</span>
	                  <strong>
	                    {ragContext.evidence_status === 'sufficient' ? '证据可用' : '证据不足'}
	                  </strong>
	                  <p>
	                    知识库 #{ragContext.knowledge_base_id} ·
	                    命中 {ragContext.coverage?.evidence_count || 0} 条 ·
	                    最高分 {ragContext.coverage?.top_score ?? 0}
	                  </p>
	                </div>
	              </div>
	              {ragHits.length > 0 ? (
	                <div className="agent-rag-hit-list">
	                  {ragHits.slice(0, 5).map((hit, index) => (
	                    <div key={`${hit.chunk_id}-${index}`}>
	                      <span>chunk #{hit.chunk_id} · {hit.score ?? '-'}</span>
	                      <strong>{hit.title || '未命名来源'}</strong>
	                      <p>{String(hit.content || '').slice(0, 180)}</p>
	                    </div>
	                  ))}
	                </div>
	              ) : (
	                <p className="agent-rag-empty">当前知识库没有足够相关证据，后续内容需要人工补来源或降级为观点草稿。</p>
	              )}
	            </div>
	          )}

	          {decision && (
            <div className="agent-decision">
              <div className="agent-decision__main">
                <span>Agent 决策</span>
                <strong>{decision.summary}</strong>
                <p>
                  {decision.quality_gate?.passed ? '已过基础质量线' : '需要人工重点复查'} ·
                  信心 {decision.confidence || 'medium'} ·
                  {decision.selected_topic?.verification_status || '未核验'}
                </p>
              </div>
              <div className="agent-decision__stats">
                <div>
                  <span>质量门槛</span>
                  <strong>{decision.quality_gate?.score ?? run.evaluation_score ?? '-'}/{decision.quality_gate?.threshold ?? 75}</strong>
                  <p>{decision.quality_gate?.publish_readiness || 'needs_review'}</p>
                </div>
                <div>
                  <span>自动改稿</span>
                  <strong>{decision.revision?.triggered ? '已执行' : '未触发'}</strong>
                  <p>{decision.revision?.reason || '-'}</p>
                </div>
              </div>

              {whyThisTopic.length > 0 && (
                <div className="agent-decision-list">
                  <h3>为什么选它</h3>
                  {whyThisTopic.slice(0, 3).map((item, index) => (
                    <p key={`${item}-${index}`}>{item}</p>
                  ))}
                </div>
              )}

              {decisionActions.length > 0 && (
                <div className="agent-action-list">
                  <h3>下一步</h3>
                  {decisionActions.slice(0, 5).map((action, index) => (
                    <div key={`${action.label}-${index}`}>
                      <span>{action.priority || 'medium'}</span>
                      <strong>{action.label}</strong>
                      <p>{action.reason}</p>
                    </div>
                  ))}
                </div>
              )}

              {(reviewFocus.length > 0 || revisionChanges.length > 0) && (
                <div className="agent-review-focus">
                  {reviewFocus.length > 0 && (
                    <div>
                      <h3>人工复查重点</h3>
                      {reviewFocus.slice(0, 5).map((item, index) => (
                        <p key={`${item}-${index}`}>{item}</p>
                      ))}
                    </div>
                  )}
                  {revisionChanges.length > 0 && (
                    <div>
                      <h3>自动改稿记录</h3>
                      {revisionChanges.slice(0, 5).map((item, index) => (
                        <p key={`${item}-${index}`}>{item}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {ideas.length > 0 && (
            <div className="agent-section">
              <h3>选题建议</h3>
              <div className="agent-idea-grid">
                {ideas.slice(0, 5).map((idea, index) => (
                  <div key={`${idea.title}-${index}`} className={`agent-idea-card ${run.topic?.title === idea.title ? 'selected' : ''}`}>
                    <strong>{String(idea.title || '')}</strong>
                    <span>{String(idea.content_angle || '-')} · {String(idea.score || '-')}分</span>
                    <p>{String(idea.reason || '')}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="agent-summary-grid">
            <div className="agent-summary-card">
              <span>推荐选题</span>
              <strong>{run.topic?.title || '-'}</strong>
              <p>{run.topic?.content_angle || '-'} · {run.topic?.score ?? '-'}分</p>
            </div>
            <div className="agent-summary-card">
              <span>发布包</span>
              <strong>{run.draft ? `#${run.draft.id}` : '-'}</strong>
              <p>{run.cards.length} 张卡片</p>
            </div>
            <div className="agent-summary-card">
              <span>质量评分</span>
              <strong>{run.evaluation_score ?? '-'}/100</strong>
              <p>{String(evaluation.publish_readiness || 'needs_review')}</p>
            </div>
          </div>

          {run.draft && (
            <div className="agent-section">
              <div className="agent-section__header">
                <h3>发布包结果</h3>
                <button className="btn btn-primary" onClick={() => onNavigate('drafts')}>去发布包编辑</button>
              </div>
              <div className="agent-draft-preview">
                {(run.draft.title_options || []).slice(0, 3).map((title, index) => (
                  <span key={`${title}-${index}`}>{title}</span>
                ))}
              </div>
              <div className="agent-card-list">
                {run.cards.slice(0, 7).map(card => (
                  <div key={card.id}>
                    <span>{String(card.page_index).padStart(2, '0')}</span>
                    <strong>{card.title}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}

          {issues.length > 0 && (
            <div className="agent-section">
              <h3>质量问题</h3>
              <div className="agent-issue-list">
                {issues.slice(0, 5).map((issue, index) => (
                  <div key={`${issue.message}-${index}`}>
                    <span>{issue.level || 'medium'}</span>
                    <p>{issue.card_page ? `第 ${issue.card_page} 页：` : ''}{issue.message}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
