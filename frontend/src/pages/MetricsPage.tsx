import { useEffect, useMemo, useState } from 'react';
import { api, Draft, Metric, MetricCreate, PublishLog, Topic } from '../api/client';

const PLATFORM_LABELS: Record<string, string> = {
  xiaohongshu: '小红书',
  douyin: '抖音',
};

function rate(value: number, base: number) {
  if (!base) return 0;
  return value / base;
}

function pct(value: number, base: number) {
  return `${(rate(value, base) * 100).toFixed(1)}%`;
}

const emptyMetric: MetricCreate = {
  views: 0,
  likes: 0,
  favorites: 0,
  comments: 0,
  shares: 0,
  new_followers: 0,
  impressions: null,
  click_rate: null,
  profile_visits: null,
  follow_conversion_rate: null,
  notes: '',
};

function nowForInput() {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export default function MetricsPage() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [logs, setLogs] = useState<PublishLog[]>([]);
  const [selectedLogId, setSelectedLogId] = useState<number | null>(null);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [loading, setLoading] = useState(false);
  const [logForm, setLogForm] = useState({
    draft_id: 0,
    platform: 'xiaohongshu',
    published_at: nowForInput(),
    post_url: '',
    used_title: '',
    used_cover_text: '',
    content_type: '图文',
    notes: '',
  });
  const [metricForm, setMetricForm] = useState<MetricCreate>(emptyMetric);

  const topicById = useMemo(() => new Map(topics.map(t => [t.id, t])), [topics]);
  const draftById = useMemo(() => new Map(drafts.map(d => [d.id, d])), [drafts]);

  const load = async () => {
    const [topicData, draftData, logData] = await Promise.all([
      api.listTopics({ limit: 100 }),
      api.listDrafts({ limit: 100 }),
      api.listPublishLogs(),
    ]);
    setTopics(topicData.items);
    setDrafts(draftData);
    setLogs(logData);
    if (!logForm.draft_id && draftData.length > 0) {
      const first = draftData[0];
      setLogForm(prev => ({
        ...prev,
        draft_id: first.id,
        used_title: first.title_options?.[0] || '',
        used_cover_text: first.cover_text_options?.[0] || '',
      }));
    }
    if (!selectedLogId && logData.length > 0) {
      setSelectedLogId(logData[0].id);
    }
  };

  useEffect(() => { load().catch(() => {}); }, []);

  useEffect(() => {
    if (!selectedLogId) {
      setMetrics([]);
      return;
    }
    api.listMetrics(selectedLogId).then(setMetrics).catch(() => setMetrics([]));
  }, [selectedLogId]);

  const selectedDraft = draftById.get(logForm.draft_id);
  const selectedLog = logs.find(log => log.id === selectedLogId) || null;

  const draftLabel = (draft: Draft) => {
    const topic = topicById.get(draft.topic_id);
    return `${topic?.title || `选题 #${draft.topic_id}`} / 发布包 #${draft.id}`;
  };

  const selectedLogSummary = useMemo(() => {
    if (metrics.length === 0) {
      return null;
    }
    const latestMetric = metrics[metrics.length - 1];
    const sum = metrics.reduce((acc, metric) => {
      acc.views += metric.views;
      acc.likes += metric.likes;
      acc.favorites += metric.favorites;
      acc.comments += metric.comments;
      acc.new_followers += metric.new_followers;
      return acc;
    }, {
      views: 0,
      likes: 0,
      favorites: 0,
      comments: 0,
      new_followers: 0,
    });
    return {
      views: sum.views,
      likes: sum.likes,
      favorites: sum.favorites,
      comments: sum.comments,
      new_followers: sum.new_followers,
      save_rate: rate(sum.favorites, sum.views),
      like_rate: rate(sum.likes, sum.views),
      comment_rate: rate(sum.comments, sum.views),
      follow_conversion_rate: latestMetric.follow_conversion_rate ??
        rate(sum.new_followers, sum.views),
    };
  }, [metrics]);

  const handleDraftChange = (draftId: number) => {
    const draft = draftById.get(draftId);
    setLogForm(prev => ({
      ...prev,
      draft_id: draftId,
      used_title: draft?.title_options?.[0] || '',
      used_cover_text: draft?.cover_text_options?.[0] || '',
    }));
  };

  const handleCreateLog = async () => {
    if (!logForm.draft_id) {
      alert('请先选择一个发布包');
      return;
    }
    setLoading(true);
    try {
      const created = await api.createPublishLog({
        ...logForm,
        published_at: logForm.published_at || null,
      });
      setSelectedLogId(created.id);
      await load();
    } catch (e: any) {
      alert('创建发布记录失败: ' + e.message);
    }
    setLoading(false);
  };

  const handleCreateMetric = async () => {
    if (!selectedLogId) {
      alert('请先选择一条发布记录');
      return;
    }
    setLoading(true);
    try {
      await api.createMetric(selectedLogId, metricForm);
      setMetricForm(emptyMetric);
      setMetrics(await api.listMetrics(selectedLogId));
    } catch (e: any) {
      alert('录入数据失败: ' + e.message);
    }
    setLoading(false);
  };

  return (
    <div>
      <div className="page-header">
        <h1>数据录入</h1>
        <p>手动记录发布链接和平台数据，供 7 天复盘使用</p>
      </div>

      <div className="grid-two">
        <section className="panel">
          <h3>创建发布记录</h3>
          <div className="form-group">
            <label>发布包</label>
            <select value={logForm.draft_id} onChange={e => handleDraftChange(Number(e.target.value))}>
              <option value={0}>请选择发布包</option>
              {drafts.map(draft => <option key={draft.id} value={draft.id}>{draftLabel(draft)}</option>)}
            </select>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>平台</label>
              <select value={logForm.platform} onChange={e => setLogForm({ ...logForm, platform: e.target.value })}>
                <option value="xiaohongshu">小红书</option>
                <option value="douyin">抖音</option>
              </select>
            </div>
            <div className="form-group">
              <label>发布时间</label>
              <input type="datetime-local" value={logForm.published_at} onChange={e => setLogForm({ ...logForm, published_at: e.target.value })} />
            </div>
          </div>
          <div className="form-group">
            <label>笔记链接</label>
            <input value={logForm.post_url} onChange={e => setLogForm({ ...logForm, post_url: e.target.value })} placeholder="https://..." />
          </div>
          <div className="form-group">
            <label>使用标题</label>
            <input value={logForm.used_title} onChange={e => setLogForm({ ...logForm, used_title: e.target.value })} />
          </div>
          <div className="form-group">
            <label>使用封面文案</label>
            <input value={logForm.used_cover_text} onChange={e => setLogForm({ ...logForm, used_cover_text: e.target.value })} />
          </div>
          <div className="form-group">
            <label>备注</label>
            <textarea value={logForm.notes} onChange={e => setLogForm({ ...logForm, notes: e.target.value })} />
          </div>
          <button className="btn btn-primary" onClick={handleCreateLog} disabled={loading || !selectedDraft}>
            创建发布记录
          </button>
        </section>

        <section className="panel">
          <h3>发布记录</h3>
          {logs.length === 0 ? (
            <div className="empty">暂无发布记录</div>
          ) : (
            <div className="stack-list">
              {logs.map(log => {
                const draft = draftById.get(log.draft_id);
                return (
                  <button
                    key={log.id}
                    className={`list-button ${selectedLogId === log.id ? 'active' : ''}`}
                    onClick={() => setSelectedLogId(log.id)}
                  >
                    <strong>{log.used_title || draft?.title_options?.[0] || `发布记录 #${log.id}`}</strong>
                    <span>{PLATFORM_LABELS[log.platform] || log.platform} · {log.published_at ? new Date(log.published_at).toLocaleString('zh-CN') : '未填发布时间'}</span>
                  </button>
                );
              })}
            </div>
          )}
        </section>
      </div>

      <section className="panel" style={{ marginTop: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center', marginBottom: 12 }}>
          <h3>录入平台数据</h3>
          {selectedLog && <span className="muted">当前记录 #{selectedLog.id}</span>}
        </div>
          <div className="metric-form-grid">
          {[
            ['views', '浏览/播放'],
            ['likes', '点赞'],
            ['favorites', '收藏'],
            ['comments', '评论'],
            ['shares', '分享'],
            ['new_followers', '新增粉丝'],
            ['impressions', '曝光'],
            ['profile_visits', '主页访问'],
          ].map(([key, label]) => (
            <div className="form-group" key={key}>
              <label>{label}</label>
              <input
                type="number"
                min={0}
                value={(metricForm as any)[key] ?? ''}
                onChange={e => setMetricForm({ ...metricForm, [key]: e.target.value === '' ? null : Number(e.target.value) })}
              />
            </div>
          ))}
          <div className="form-group">
            <label>点击率</label>
            <input type="number" step="0.0001" value={metricForm.click_rate ?? ''} onChange={e => setMetricForm({ ...metricForm, click_rate: e.target.value === '' ? null : Number(e.target.value) })} />
          </div>
          <div className="form-group">
            <label>关注转化率</label>
            <input type="number" step="0.0001" value={metricForm.follow_conversion_rate ?? ''} onChange={e => setMetricForm({ ...metricForm, follow_conversion_rate: e.target.value === '' ? null : Number(e.target.value) })} />
          </div>
        </div>
        <div className="form-group">
          <label>数据备注</label>
          <textarea value={metricForm.notes || ''} onChange={e => setMetricForm({ ...metricForm, notes: e.target.value })} />
        </div>
          <button className="btn btn-primary" onClick={handleCreateMetric} disabled={loading || !selectedLogId}>保存本次数据</button>

          {selectedLogSummary && (
            <div className="metric-summary" style={{ marginTop: 16 }}>
              <h4>汇总关键率</h4>
              <div className="metric-summary-grid">
                <span>收藏率：{pct(selectedLogSummary.favorites, selectedLogSummary.views)}</span>
                <span>点赞率：{pct(selectedLogSummary.likes, selectedLogSummary.views)}</span>
                <span>评论率：{pct(selectedLogSummary.comments, selectedLogSummary.views)}</span>
                <span>关注转化率：{selectedLogSummary.follow_conversion_rate != null ? `${(selectedLogSummary.follow_conversion_rate * 100).toFixed(1)}%` : pct(selectedLogSummary.new_followers, selectedLogSummary.views)}</span>
              </div>
            </div>
          )}

        <h3 style={{ marginTop: 24, marginBottom: 12 }}>历史数据</h3>
        {metrics.length === 0 ? (
          <div className="empty">暂无数据指标</div>
        ) : (
              <table>
                <thead>
                  <tr>
                    <th>时间</th><th>浏览</th><th>点赞</th><th>收藏</th><th>评论</th><th>分享</th><th>新增粉丝</th><th>关键率（收藏/点赞/评论/关注）</th>
                  </tr>
                </thead>
                <tbody>
                  {metrics.map(metric => (
                    <tr key={metric.id}>
                      <td>{new Date(metric.collected_at).toLocaleString('zh-CN')}</td>
                      <td>{metric.views}</td>
                      <td>{metric.likes}</td>
                      <td>{metric.favorites}</td>
                      <td>{metric.comments}</td>
                      <td>{metric.shares}</td>
                      <td>{metric.new_followers}</td>
                      <td>
                        {pct(metric.favorites, metric.views)} / {pct(metric.likes, metric.views)} / {pct(metric.comments, metric.views)} / {(metric.follow_conversion_rate != null ? `${(metric.follow_conversion_rate * 100).toFixed(1)}%` : pct(metric.new_followers, metric.views))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
      </section>
    </div>
  );
}
