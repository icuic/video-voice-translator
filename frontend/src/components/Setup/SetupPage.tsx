import { useEffect, useState, FormEvent } from 'react';
import { setupService, SetupApplyResult, SetupStatus } from '../../services/setup';

interface SetupPageProps {
  onConfigured: () => void;
  allowSkip?: boolean;
}

export function SetupPage({ onConfigured, allowSkip = false }: SetupPageProps) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SetupApplyResult | null>(null);
  const [isConfigured, setIsConfigured] = useState(false);

  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState('');
  const [timeout, setTimeout] = useState('');
  const [restart, setRestart] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const s: SetupStatus = await setupService.getStatus();
        setIsConfigured(s.configured);
        if (s.configured) {
          setBaseUrl(s.current.llm_base_url || '');
          setModel(s.current.llm_model || '');
          if (s.current.llm_temperature) setTemperature(s.current.llm_temperature);
          if (s.current.llm_timeout) setTimeout(s.current.llm_timeout);
        }
      } catch (e: any) {
        setError(e?.response?.data?.detail || e?.message || '无法获取配置状态，请刷新重试');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setResult(null);
    if (!baseUrl.trim()) {
      setError('请填写 API Base URL');
      return;
    }
    if (!/^https?:\/\//i.test(baseUrl.trim())) {
      setError('API Base URL 必须以 http:// 或 https:// 开头');
      return;
    }
    if (!apiKey.trim()) {
      setError('请填写 API Key（本地无鉴权请填 EMPTY）');
      return;
    }
    if (!model.trim()) {
      setError('请填写模型名');
      return;
    }
    if (temperature.trim()) {
      const f = parseFloat(temperature);
      if (Number.isNaN(f) || f < 0 || f > 2) {
        setError('采样温度必须是 0.0~2.0 之间的数字');
        return;
      }
    }
    if (timeout.trim()) {
      const n = parseInt(timeout, 10);
      if (!/^[1-9][0-9]*$/.test(timeout.trim()) || !Number.isFinite(n)) {
        setError('超时时间必须是正整数');
        return;
      }
    }
    setSubmitting(true);
    try {
      const r = await setupService.apply({
        llm_base_url: baseUrl.trim(),
        llm_api_key: apiKey.trim(),
        llm_model: model.trim(),
        llm_temperature: temperature.trim() || undefined,
        llm_timeout: timeout.trim() || undefined,
        restart,
      });
      setResult(r);
      if (r.saved) {
        const waitForBackend = async () => {
          const hardDeadline = Date.now() + (restart ? 90_000 : 5_000);
          const initialDelay = restart ? 3500 : 200;
          let backoff = 1200;
          await new Promise((res) => setTimeout(res, initialDelay));
          while (Date.now() < hardDeadline) {
            try {
              const s: SetupStatus = await setupService.getStatus();
              if (s.configured) {
                try {
                  onConfigured?.();
                  return;
                } catch (e) {
                  console.error('[SetupPage] onConfigured throw, 强制 reload 跳 /', e);
                  try { window.location.href = '/'; } catch (_) { /* noop */ }
                  return;
                }
              }
            } catch (_) {
              // 后端重启窗口期：502 / ECONNREFUSED / socket hang up 全部吞掉，继续轮询
            }
            const waitMs = Math.min(backoff, 4000);
            backoff = Math.round(backoff * 1.25);
            await new Promise((res) => setTimeout(res, waitMs));
          }
          // 兜底：90s 后即便后端没成功回来（比如进程真的起不来），也不要卡死在 SetupPage，
          // 强制整页跳 / ，让 ErrorBoundary / 全局 reload 兜底再给一次机会。
          try { window.location.href = '/'; } catch (_) { /* noop */ }
        };
        void waitForBackend();
      } else {
        setError('后端返回保存失败，请查看错误详情');
      }
    } catch (e: any) {
      const detail = e?.response?.data;
      let msg = e?.message || '保存失败';
      if (detail && typeof detail === 'object') {
        if (detail.detail) {
          if (typeof detail.detail === 'string') msg = detail.detail;
          else if (Array.isArray(detail.detail)) {
            msg = detail.detail.map((x: any) => `${x.loc?.join('.') || ''}: ${x.msg}`).join('; ');
          }
        } else if (typeof detail === 'object' && Object.keys(detail).length > 0) {
          try { msg = JSON.stringify(detail, null, 2); } catch { /* ignore */ }
        }
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-900 to-slate-900 flex items-center justify-center p-4">
        <div className="text-white text-lg flex items-center gap-3">
          <svg className="animate-spin w-6 h-6" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
            <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
          </svg>
          正在检查配置状态...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center shadow-lg">
            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
          </div>
          <div>
            <h1 className="text-3xl font-bold text-white">AI 音视频翻译系统</h1>
            <p className="text-slate-300 mt-1">
              {isConfigured ? '重新配置 LLM 翻译服务' : '首次使用：配置 LLM 翻译服务'}
            </p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="bg-slate-800/60 backdrop-blur border border-slate-700 rounded-2xl p-6 shadow-2xl space-y-5">
          <div className="space-y-1">
            <label className="block text-sm font-semibold text-slate-200">
              API Base URL <span className="text-red-400">*</span>
              <span className="ml-2 text-xs text-slate-400 font-normal">OpenAI 兼容接口，以 http(s):// 开头</span>
            </label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="例如：https://dashscope.aliyuncs.com/compatible-mode/v1"
              className="w-full px-4 py-3 rounded-lg bg-slate-900/80 text-white placeholder-slate-500 border border-slate-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/40 outline-none transition"
              autoComplete="off"
              spellCheck={false}
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-semibold text-slate-200">
              API Key <span className="text-red-400">*</span>
              <span className="ml-2 text-xs text-slate-400 font-normal">本地无鉴权部署填 <code className="text-yellow-300">EMPTY</code></span>
            </label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className="w-full px-4 py-3 rounded-lg bg-slate-900/80 text-white placeholder-slate-500 border border-slate-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/40 outline-none transition"
              autoComplete="off"
              spellCheck={false}
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-semibold text-slate-200">
              模型名 <span className="text-red-400">*</span>
              <span className="ml-2 text-xs text-slate-400 font-normal">按供应商文档填写，大小写敏感</span>
            </label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="例如：qwen-flash 或 Qwen/Qwen2.5-72B-Instruct 或 gpt-4o-mini"
              className="w-full px-4 py-3 rounded-lg bg-slate-900/80 text-white placeholder-slate-500 border border-slate-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/40 outline-none transition"
              autoComplete="off"
              spellCheck={false}
            />
          </div>

          <button
            type="button"
            onClick={() => setShowAdvanced((s) => !s)}
            className="text-sm text-indigo-300 hover:text-indigo-200 flex items-center gap-2 transition"
          >
            <svg className={`w-4 h-4 transition-transform ${showAdvanced ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            高级选项 {showAdvanced ? '(收起)' : '(展开：采样温度 / 超时 / 是否立即重启)'}
          </button>

          {showAdvanced && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 pt-2">
              <div className="space-y-1">
                <label className="block text-sm font-semibold text-slate-200">
                  采样温度
                  <span className="ml-2 text-xs text-slate-400 font-normal">翻译推荐 0.05~0.2，留空=默认 0.1</span>
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={temperature}
                  onChange={(e) => setTemperature(e.target.value)}
                  placeholder="0.1"
                  className="w-full px-4 py-2.5 rounded-lg bg-slate-900/80 text-white placeholder-slate-500 border border-slate-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/40 outline-none transition"
                />
              </div>
              <div className="space-y-1">
                <label className="block text-sm font-semibold text-slate-200">
                  请求超时（秒）
                  <span className="ml-2 text-xs text-slate-400 font-normal">长文本翻译建议 300~600</span>
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  value={timeout}
                  onChange={(e) => setTimeout(e.target.value)}
                  placeholder="300"
                  className="w-full px-4 py-2.5 rounded-lg bg-slate-900/80 text-white placeholder-slate-500 border border-slate-700 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/40 outline-none transition"
                />
              </div>
              <div className="md:col-span-2 flex items-center gap-3 bg-slate-900/60 border border-slate-700/70 rounded-lg px-4 py-3">
                <input
                  id="restart-ck"
                  type="checkbox"
                  checked={restart}
                  onChange={(e) => setRestart(e.target.checked)}
                  className="w-4 h-4 accent-indigo-500"
                />
                <label htmlFor="restart-ck" className="text-sm text-slate-200">
                  保存后立即重启服务（推荐勾选，否则需要手动重启才能让新配置生效）
                </label>
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-red-900/40 border border-red-700/60 text-red-200 text-sm px-4 py-3 whitespace-pre-wrap">
              {error}
            </div>
          )}

          {result && (
            <div className={`rounded-lg border px-4 py-3 text-sm ${
              result.saved && (!restart || result.restart_result?.restarted)
                ? 'bg-green-900/30 border-green-700/60 text-green-200'
                : 'bg-yellow-900/30 border-yellow-700/60 text-yellow-100'
            }`}>
              <div className="font-semibold mb-1">
                {result.saved ? '✅ 配置已成功写入 .env' : '⚠️ 配置保存异常'}
              </div>
              {result.restart_result && (
                <div className="mt-1 text-xs whitespace-pre-wrap opacity-90">
                  重启服务：{result.restart_result.restarted ? '已完成' : `未完成（code=${result.restart_result.code}）`}
                  {result.restart_result.message && `\n${result.restart_result.message}`}
                </div>
              )}
              {result.saved && (!restart || result.restart_result?.restarted) && (
                <div className="mt-1 text-xs text-green-200/80">
                  正在跳转到主界面...
                </div>
              )}
            </div>
          )}

          <div className="flex items-center justify-between pt-2">
            {allowSkip && (
              <button
                type="button"
                onClick={onConfigured}
                className="px-4 py-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-700/50 text-sm transition"
              >
                跳过，暂时不配置
              </button>
            )}
            <div className="ml-auto">
              <button
                type="submit"
                disabled={submitting}
                className="px-6 py-3 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-600 disabled:text-slate-400 disabled:cursor-not-allowed text-white font-semibold shadow-lg shadow-indigo-900/40 transition flex items-center gap-2"
              >
                {submitting && (
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" className="opacity-25" />
                    <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
                  </svg>
                )}
                {submitting ? '保存中...' : '保存配置并启动'}
              </button>
            </div>
          </div>
        </form>

        <div className="mt-8 text-center text-xs text-slate-400">
          通过命令行配置：<code className="text-slate-300">./configure.sh</code>
          <span className="mx-2">·</span>
          详细文档：<code className="text-slate-300">docs/ENV_ADVANCED.md</code>
        </div>
      </div>
    </div>
  );
}
