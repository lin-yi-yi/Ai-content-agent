import { useEffect, useState } from 'react';

interface Provider {
  provider: string;
  model: string;
  configured: boolean;
  base_url: string;
}

interface ModelRun {
  id: number;
  task_type: string;
  provider: string;
  model_name: string;
  success: boolean;
  latency_ms: number;
  input_preview: string;
  output_preview: string;
  created_at: string;
}

interface TaskDefault {
  task: string;
  label: string;
  provider: string;
  model: string;
}

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [taskDefaults, setTaskDefaults] = useState<TaskDefault[]>([]);
  const [runs, setRuns] = useState<ModelRun[]>([]);
  const [testResult, setTestResult] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('local');
  const [chatPrompt, setChatPrompt] = useState('用一句话介绍 AI Agent');
  const [chatResult, setChatResult] = useState('');
  const [loading, setLoading] = useState(false);

  const load = () => {
    fetch('/api/models/providers').then(r => r.json()).then(d => setProviders(d.providers)).catch(() => {});
    fetch('/api/models/task-defaults').then(r => r.json()).then(d => setTaskDefaults(d.defaults)).catch(() => {});
    fetch('/api/models/runs?limit=10').then(r => r.json()).then(d => setRuns(d.runs)).catch(() => {});
  };

  useEffect(() => { load(); }, []);

  const testProvider = async (provider: string) => {
    setTestResult('测试中...');
    try {
      const r = await fetch(`/api/models/test/${provider}`, { method: 'POST' });
      const d = await r.json();
      setTestResult(d.ok ? `✅ ${provider} 连接成功: ${d.response}` : `❌ ${d.error}`);
    } catch(e: any) {
      setTestResult(`❌ ${e.message}`);
    }
  };

  const testChat = async () => {
    setLoading(true);
    setChatResult('');
    try {
      const r = await fetch('/api/models/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: selectedProvider, user_prompt: chatPrompt, max_tokens: 100 }),
      });
      const d = await r.json();
      setChatResult(d.content);
      load();
    } catch(e: any) {
      setChatResult(`错误: ${e.message}`);
    }
    setLoading(false);
  };

  return (
    <div>
      <div className="page-header">
        <h1>⚙️ 模型设置</h1>
        <p>管理 LLM 供应商，查看调用记录</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* 供应商列表 */}
        <div style={{ background: 'var(--surface)', borderRadius: 8, padding: 20, border: '1px solid var(--border)' }}>
          <h3 style={{ marginBottom: 12 }}>模型供应商</h3>
          <table>
            <thead><tr><th>供应商</th><th>模型</th><th>状态</th><th>测试</th></tr></thead>
            <tbody>
              {providers.map(p => (
                <tr key={p.provider}>
                  <td><strong>{p.provider}</strong></td>
                  <td style={{ fontSize: 12 }}>{p.model}</td>
                  <td><span className={`badge ${p.configured ? 'badge-published' : 'badge-discarded'}`}>
                    {p.configured ? '已配置' : '未配置'}</span></td>
                  <td>
                    <button className="btn btn-sm" onClick={() => testProvider(p.provider)}
                            disabled={!p.configured}>测试</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {testResult && <div style={{ marginTop: 12, fontSize: 13, color: testResult.includes('✅') ? 'var(--green)' : 'var(--red)' }}>{testResult}</div>}
        </div>

        {/* 对话测试 */}
        <div style={{ background: 'var(--surface)', borderRadius: 8, padding: 20, border: '1px solid var(--border)' }}>
          <h3 style={{ marginBottom: 12 }}>对话测试</h3>
          <div className="form-group">
            <label>供应商</label>
            <select value={selectedProvider} onChange={e => setSelectedProvider(e.target.value)}>
              {providers.map(p => (
                <option key={p.provider} value={p.provider} disabled={!p.configured}>
                  {p.provider} / {p.model}{p.configured ? '' : '（未配置）'}
                </option>
              ))}
            </select>
          </div>
          <div className="form-group">
            <textarea value={chatPrompt} onChange={e => setChatPrompt(e.target.value)} rows={2}
                      style={{ width: '100%' }} />
          </div>
          <button className="btn btn-primary" onClick={testChat} disabled={loading}>
            {loading ? '调用中...' : '发送'}
          </button>
          {chatResult && (
            <div style={{ marginTop: 12, padding: 12, background: 'var(--bg)', borderRadius: 6, fontSize: 13, lineHeight: 1.6 }}>
              {chatResult}
            </div>
          )}
        </div>
      </div>

      <div style={{ marginTop: 24, background: 'var(--surface)', borderRadius: 8, padding: 20, border: '1px solid var(--border)' }}>
        <h3 style={{ marginBottom: 12 }}>Agent 任务默认模型</h3>
        <table>
          <thead><tr><th>任务</th><th>供应商</th><th>模型</th></tr></thead>
          <tbody>
            {taskDefaults.map(item => (
              <tr key={item.task}>
                <td>{item.label}</td>
                <td>{item.provider}</td>
                <td style={{ fontSize: 12 }}>{item.model}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 调用记录 */}
      <div style={{ marginTop: 24, background: 'var(--surface)', borderRadius: 8, padding: 20, border: '1px solid var(--border)' }}>
        <h3 style={{ marginBottom: 12 }}>最近调用记录</h3>
        <table>
          <thead><tr><th>任务</th><th>供应商</th><th>模型</th><th>耗时</th><th>状态</th><th>时间</th></tr></thead>
          <tbody>
            {runs.length === 0 ? (
              <tr><td colSpan={6} className="empty">暂无记录</td></tr>
            ) : runs.map(r => (
              <tr key={r.id}>
                <td>{r.task_type}</td>
                <td>{r.provider}</td>
                <td style={{ fontSize: 12 }}>{r.model_name}</td>
                <td>{r.latency_ms}ms</td>
                <td><span className={`badge ${r.success ? 'badge-published' : 'badge-discarded'}`}>
                  {r.success ? '成功' : '失败'}</span></td>
                <td style={{ fontSize: 12 }}>{new Date(r.created_at).toLocaleString('zh-CN')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
