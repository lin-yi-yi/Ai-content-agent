import { useEffect, useState } from 'react';
import { api, KnowledgeBase, RagAnswerResponse, RagSearchHit } from '../api/client';

export default function RagLabPage() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [knowledgeBaseId, setKnowledgeBaseId] = useState<number | null>(null);
  const [query, setQuery] = useState('LangChain、RAG 和 LangGraph 应该怎么接进这个项目？');
  const [topK, setTopK] = useState(5);
  const [provider, setProvider] = useState('local');
  const [hits, setHits] = useState<RagSearchHit[]>([]);
  const [answer, setAnswer] = useState<RagAnswerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.listKnowledgeBases().then(items => {
      setKnowledgeBases(items);
      setKnowledgeBaseId(items[0]?.id ?? null);
    }).catch(() => setKnowledgeBases([]));
  }, []);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    setAnswer(null);
    try {
      const result = await api.searchRag({
        query: query.trim(),
        knowledge_base_id: knowledgeBaseId,
        top_k: topK,
      });
      setHits(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    setLoading(false);
  };

  const handleAnswer = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError('');
    try {
      const result = await api.answerWithRag({
        query: query.trim(),
        knowledge_base_id: knowledgeBaseId,
        provider,
        top_k: topK,
      });
      setAnswer(result);
      setHits(result.citations || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    setLoading(false);
  };

  return (
    <div>
      <div className="page-header">
        <h1>RAG 实验</h1>
        <p>手动测试知识库检索、证据覆盖和拒答边界</p>
      </div>

      <section className="rag-lab-layout">
        <div className="panel">
          <h3>查询</h3>
          <div className="form-group">
            <label>知识库</label>
            <select value={knowledgeBaseId || ''} onChange={e => setKnowledgeBaseId(e.target.value ? Number(e.target.value) : null)}>
              {knowledgeBases.map(item => (
                <option key={item.id} value={item.id}>#{item.id} {item.name}</option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <label>问题</label>
            <textarea rows={4} value={query} onChange={e => setQuery(e.target.value)} />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>证据数量</label>
              <select value={topK} onChange={e => setTopK(Number(e.target.value))}>
                <option value={3}>3 条</option>
                <option value={5}>5 条</option>
                <option value={8}>8 条</option>
              </select>
            </div>
            <div className="form-group">
              <label>回答模型</label>
              <select value={provider} onChange={e => setProvider(e.target.value)}>
                <option value="local">local 摘要</option>
                <option value="deepseek">DeepSeek</option>
                <option value="doubao">豆包 / 火山方舟</option>
              </select>
            </div>
          </div>
          <div className="form-actions">
            <button className="btn" onClick={handleSearch} disabled={loading || !query.trim()}>只检索</button>
            <button className="btn btn-primary" onClick={handleAnswer} disabled={loading || !query.trim()}>检索并回答</button>
          </div>
          {error && <div className="source-rag-status error">{error}</div>}
        </div>

        <div className="panel">
          <h3>回答</h3>
          {!answer ? (
            <div className="empty" style={{ padding: 24 }}>点击“检索并回答”后显示结果</div>
          ) : (
            <div className={`rag-answer-box ${answer.refused ? 'refused' : 'ok'}`}>
              <span>{answer.refused ? '已拒答' : '已回答'}</span>
              <strong>{answer.refused ? answer.refusal_reason || 'insufficient_evidence' : '基于证据生成'}</strong>
              <p>{answer.answer}</p>
              <small>
                覆盖状态：{String(answer.coverage?.status || '-')} ·
                证据 {String(answer.coverage?.evidence_count || 0)} 条 ·
                最高分 {String(answer.coverage?.top_score || 0)}
              </small>
            </div>
          )}
        </div>
      </section>

      <section className="panel">
        <h3>证据 Chunk</h3>
        {hits.length === 0 ? (
          <div className="empty" style={{ padding: 24 }}>暂无检索结果</div>
        ) : (
          <div className="rag-hit-grid">
            {hits.map((hit) => (
              <div key={hit.chunk_id} className="rag-hit-item">
                <div>
                  <span>chunk #{hit.chunk_id} · score {hit.score}</span>
                  <strong>{hit.title}</strong>
                </div>
                <p>{hit.content}</p>
                {hit.source_uri && <a href={hit.source_uri} target="_blank">查看来源</a>}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
