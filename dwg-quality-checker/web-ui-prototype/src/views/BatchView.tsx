import { useMemo, useState } from 'react';
import {
  cancelRecover,
  getRecoverStatus,
  listRecoverHistory,
  pickFolder,
  pauseRecover,
  resumeRecover,
  startRecoverFolder,
  toUserFriendlyError,
  type RecoverFolderResult,
  type RecoveryItem,
} from '../desktopApi';

type ModeLabel = 'Seguro' | 'Balanceado' | 'Agressivo';

const MODE_MAP: Record<ModeLabel, string> = {
  Seguro: 'safe',
  Balanceado: 'balanced',
  Agressivo: 'aggressive',
};

export function BatchView() {
  const [folderPath, setFolderPath] = useState('');
  const [status, setStatus] = useState('Selecione uma pasta para iniciar o lote.');
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState('');
  const [mode, setMode] = useState<ModeLabel>('Balanceado');
  const [retryLimit, setRetryLimit] = useState(1);
  const [previewOnly, setPreviewOnly] = useState(false);
  const [rows, setRows] = useState<RecoveryItem[]>([]);
  const [summary, setSummary] = useState<{ total: number; ok: number; fail: number } | null>(null);
  const [batchResult, setBatchResult] = useState<RecoverFolderResult | null>(null);
  const [progress, setProgress] = useState(0);
  const [stage, setStage] = useState('');
  const [processedCount, setProcessedCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [okCount, setOkCount] = useState(0);
  const [failCount, setFailCount] = useState(0);
  const [etaSeconds, setEtaSeconds] = useState<number | null>(null);
  const [paused, setPaused] = useState(false);

  const processed = useMemo(() => {
    if (busy) {
      return processedCount;
    }
    if (!summary) {
      return 0;
    }
    return summary.ok + summary.fail;
  }, [busy, processedCount, summary]);

  const totalForUi = busy ? totalCount : (summary?.total ?? 0);

  const etaLabel = useMemo(() => {
    if (!busy || etaSeconds === null || etaSeconds <= 0) {
      return '';
    }
    const min = Math.floor(etaSeconds / 60);
    const sec = etaSeconds % 60;
    if (min > 0) {
      return `ETA: ${min}m ${sec}s`;
    }
    return `ETA: ${sec}s`;
  }, [busy, etaSeconds]);

  const extSummaryLabel = useMemo(() => {
    const ext = batchResult?.by_extension;
    if (!ext) {
      return '';
    }
    const dxf = ext['.dxf'];
    const dwg = ext['.dwg'];
    const dxfTxt = dxf ? `.dxf avg ${Number(dxf.avg_seconds || 0).toFixed(2)}s` : '';
    const dwgTxt = dwg ? `.dwg avg ${Number(dwg.avg_seconds || 0).toFixed(2)}s` : '';
    return [dxfTxt, dwgTxt].filter(Boolean).join(' • ');
  }, [batchResult]);

  const doPickFolder = async () => {
    const selected = await pickFolder();
    if (selected) {
      setFolderPath(selected);
      setStatus('Pasta selecionada. Pronto para iniciar.');
    }
  };

  const runBatch = async () => {
    if (!folderPath.trim()) {
      setStatus('Selecione uma pasta antes de iniciar.');
      return;
    }
    setBusy(true);
    setJobId('');
    setRows([]);
    setSummary(null);
    setBatchResult(null);
    setProgress(1);
    setStage('Iniciando...');
    setProcessedCount(0);
    setTotalCount(0);
    setOkCount(0);
    setFailCount(0);
    setEtaSeconds(null);
    setPaused(false);
    setStatus('Executando recuperação em lote...');
    try {
      const startedJobId = await startRecoverFolder(folderPath.trim(), MODE_MAP[mode], previewOnly, retryLimit);
      if (!startedJobId) {
        throw new Error('Não foi possível iniciar o job de recuperação em lote.');
      }
      setJobId(startedJobId);

      while (true) {
        const s = await getRecoverStatus(startedJobId);
        setProgress(Math.max(1, Math.min(100, Number(s.progress || 0))));
        setStage(String(s.stage || 'Processando...'));
        setProcessedCount(Number(s.processed || 0));
        setTotalCount(Number(s.total || 0));
        setOkCount(Number(s.ok || 0));
        setFailCount(Number(s.fail || 0));
        setEtaSeconds(typeof s.eta_seconds === 'number' ? s.eta_seconds : null);
        setPaused(s.state === 'paused' || Boolean(s.pause_requested));

        if (s.state === 'done' || s.state === 'cancelled') {
          const result = s.result;
          if (result) {
            setRows(result.items ?? []);
            setSummary({ total: result.total ?? 0, ok: result.ok ?? 0, fail: result.fail ?? 0 });
            setBatchResult(result);
            setStatus(
              s.state === 'cancelled'
                ? `Lote cancelado: ${result.ok} sucesso(s), ${result.fail} falha(s).`
                : `Lote concluído: ${result.ok} sucesso(s), ${result.fail} falha(s).`,
            );
          } else {
            setStatus(s.state === 'cancelled' ? 'Lote cancelado.' : 'Lote concluído.');
          }
          break;
        }

        if (s.state === 'error' || s.state === 'not_found') {
          throw new Error(s.error || s.stage || 'Falha no lote.');
        }

        await new Promise((resolve) => window.setTimeout(resolve, 300));
      }
    } catch (error) {
      const message = toUserFriendlyError(error, 'Falha no lote.');
      setStatus(`Falha no lote: ${message}`);
    } finally {
      setBusy(false);
      setJobId('');
      setEtaSeconds(null);
      setPaused(false);
    }
  };

  const requestCancel = async () => {
    if (!busy || !jobId) {
      return;
    }
    const ok = await cancelRecover(jobId);
    if (ok) {
      setStatus('Cancelamento solicitado. Finalizando arquivo atual...');
    } else {
      setStatus('Não foi possível solicitar cancelamento agora.');
    }
  };

  const requestPause = async () => {
    if (!busy || !jobId || paused) {
      return;
    }
    const ok = await pauseRecover(jobId);
    if (ok) {
      setPaused(true);
      setStatus('Pausa solicitada. O lote vai pausar em segurança.');
    } else {
      setStatus('Não foi possível pausar agora.');
    }
  };

  const requestResume = async () => {
    if (!busy || !jobId || !paused) {
      return;
    }
    const ok = await resumeRecover(jobId);
    if (ok) {
      setPaused(false);
      setStatus('Retomando processamento do lote...');
    } else {
      setStatus('Não foi possível retomar agora.');
    }
  };

  const loadLastHistory = async () => {
    if (busy) {
      return;
    }
    try {
      const rowsHistory = await listRecoverHistory(1);
      const last = rowsHistory[0];
      if (!last) {
        setStatus('Nenhum histórico de lote encontrado.');
        return;
      }
      const result = last.result;
      if (!result) {
        setStatus('Último lote não possui resultado detalhado salvo.');
        return;
      }

      setRows(result.items ?? []);
      setSummary({ total: result.total ?? 0, ok: result.ok ?? 0, fail: result.fail ?? 0 });
      setBatchResult(result);
      setProgress(Number(last.progress || 0));
      setStage(String(last.stage || ''));      
      setProcessedCount(Number(last.processed || 0));
      setTotalCount(Number(last.total || 0));
      setOkCount(Number(last.ok || 0));
      setFailCount(Number(last.fail || 0));
      setEtaSeconds(typeof last.eta_seconds === 'number' ? last.eta_seconds : null);
      setStatus(`Histórico carregado: ${result.ok} sucesso(s), ${result.fail} falha(s).`);
    } catch (error) {
      const message = toUserFriendlyError(error, 'Falha ao carregar histórico.');
      setStatus(`Falha ao carregar histórico: ${message}`);
    }
  };

  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Verificação em Lote</strong>
        <span className="hint-inline">Escolha a pasta, inicie o lote e acompanhe por arquivo.</span>
      </div>

      <div className="file-row">
        <input
          className="text-input"
          placeholder="Selecione uma pasta com arquivos DXF..."
          value={folderPath}
          onChange={(e) => setFolderPath(e.target.value)}
        />
        <button className="soft" onClick={doPickFolder} disabled={busy}>Pasta</button>
        <button className="primary" onClick={runBatch} disabled={busy}>Iniciar Lote</button>
        <button className="soft" onClick={requestPause} disabled={!busy || !jobId || paused}>Pausar</button>
        <button className="soft" onClick={requestResume} disabled={!busy || !jobId || !paused}>Retomar</button>
        <button className="soft" onClick={requestCancel} disabled={!busy || !jobId}>Cancelar</button>
        <button className="soft" onClick={loadLastHistory} disabled={busy}>Último histórico</button>
        <label className="check"><input type="checkbox" checked={previewOnly} onChange={(e) => setPreviewOnly(e.target.checked)} /> Preview</label>
        <select className="select compact" value={mode} onChange={(e) => setMode(e.target.value as ModeLabel)}>
          <option>Seguro</option>
          <option>Balanceado</option>
          <option>Agressivo</option>
        </select>
        <select className="select compact" value={retryLimit} onChange={(e) => setRetryLimit(Number(e.target.value || 1))}>
          <option value={0}>Sem retentativa</option>
          <option value={1}>1 retentativa</option>
          <option value={2}>2 retentativas</option>
          <option value={3}>3 retentativas</option>
        </select>
        <button className="soft" onClick={() => {
          setRows([]);
          setSummary(null);
          setBatchResult(null);
          setStatus('Lista limpa.');
          setProgress(0);
          setStage('');
          setProcessedCount(0);
          setTotalCount(0);
          setOkCount(0);
          setFailCount(0);
          setEtaSeconds(null);
          setPaused(false);
        }} disabled={busy}>Limpar</button>
      </div>

      <p className="hint">{status}</p>
      <p className="hint-inline">
        Processando {processed}/{totalForUi} • OK {busy ? okCount : (summary?.ok ?? 0)} • Falha {busy ? failCount : (summary?.fail ?? 0)} {paused ? '• PAUSADO' : ''} {etaLabel}
      </p>
      {!busy && batchResult ? (
        <p className="hint-inline">
          Tempo total: {Number(batchResult.elapsed_seconds || 0).toFixed(2)}s • Média/arquivo: {Number(batchResult.avg_seconds_per_file || 0).toFixed(2)}s {extSummaryLabel ? `• ${extSummaryLabel}` : ''}
        </p>
      ) : null}

      {busy ? (
        <div className="progress-wrap" aria-live="polite">
          <div className="progress-head">
            <span className="spinner" />
            <strong>{stage || 'Processando lote...'}</strong>
            <span>{Math.max(1, Math.min(100, progress))}%</span>
          </div>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${Math.max(1, Math.min(100, progress))}%` }} />
          </div>
        </div>
      ) : null}

      <div className="list-table">
        <div className="list-head four-batch">
          <span>Arquivo</span><span>Status</span><span>Score</span><span>Info</span>
        </div>
        <div className="list-body">
          {rows.length === 0 ? <div className="empty-row">Nenhum lote executado ainda</div> : null}
          {rows.map((r, index) => (
            <div className="list-row four-batch" key={`${r.file}-${index}`}>
              <span>{r.file}</span>
              <span>{r.status}</span>
              <span>{r.health_score ?? '-'}</span>
              <span>{r.error ?? `${r.issues ?? 0} issue(s)`}{typeof r.attempts === 'number' ? ` • tentativas: ${r.attempts}` : ''}{typeof r.elapsed_seconds === 'number' ? ` • ${r.elapsed_seconds.toFixed(2)}s` : ''}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
