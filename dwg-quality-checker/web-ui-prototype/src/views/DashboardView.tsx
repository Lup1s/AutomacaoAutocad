import { useMemo, useState } from 'react';
import {
  getVerifyStatus,
  isDesktopRuntime,
  openPath,
  pickFile,
  recoverFile,
  toUserFriendlyError,
  type Severity,
  startVerify,
  verifyFile,
  type VerifyResult,
} from '../desktopApi';

type ModeLabel = 'Seguro' | 'Balanceado' | 'Agressivo';

const MODE_MAP: Record<ModeLabel, string> = {
  Seguro: 'safe',
  Balanceado: 'balanced',
  Agressivo: 'aggressive',
};

export function DashboardView({ onNavigate }: { onNavigate?: (view: 'batch') => void }) {
  const [uiMode, setUiMode] = useState<'Básico' | 'Avançado'>('Básico');
  const [severityFilter, setSeverityFilter] = useState<'Todos' | Severity>('Todos');
  const [query, setQuery] = useState('');
  const [filePath, setFilePath] = useState('');
  const [recoverMode, setRecoverMode] = useState<ModeLabel>('Balanceado');
  const [previewOnly, setPreviewOnly] = useState(false);
  const [status, setStatus] = useState('Aguardando arquivo para iniciar');
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStage, setProgressStage] = useState('');
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);

  const visibleRows = useMemo(() => {
    const rows = verifyResult?.issues ?? [];
    return rows.filter((row) => {
      const passSeverity = severityFilter === 'Todos' || row.severity === severityFilter;
      const q = query.trim().toLowerCase();
      const passText = !q || [row.rule, row.message, row.layer, row.location, row.handle, row.details].some((v) => String(v).toLowerCase().includes(q));
      return passSeverity && passText;
    });
  }, [query, severityFilter, verifyResult]);

  const reports = verifyResult?.reports;

  const doPickFile = async () => {
    if (!isDesktopRuntime()) {
      setStatus('Seleção nativa disponível apenas no modo desktop.');
      return;
    }
    const selected = await pickFile();
    if (selected) {
      setFilePath(selected);
      setStatus('Arquivo selecionado. Pronto para verificar.');
    }
  };

  const runVerify = async () => {
    if (!filePath.trim()) {
      setStatus('Selecione um arquivo antes de verificar.');
      return;
    }

    setBusy(true);
    setProgress(1);
    setProgressStage('Iniciando...');
    setStatus('Executando verificação...');

    try {
      let result: VerifyResult | null = null;

      try {
        const jobId = await startVerify(filePath.trim());
        if (jobId) {
          while (true) {
            const s = await getVerifyStatus(jobId);
            setProgress(Math.max(1, Math.min(100, Number(s.progress || 0))));
            setProgressStage(String(s.stage || 'Processando...'));

            if (s.state === 'done') {
              result = s.result ?? null;
              break;
            }
            if (s.state === 'error' || s.state === 'not_found') {
              throw new Error(s.error || s.stage || 'Falha na verificação.');
            }

            await new Promise((resolve) => window.setTimeout(resolve, 250));
          }
        }
      } catch {
        setProgressStage('Modo compatível sem progresso avançado');
        result = await verifyFile(filePath.trim());
      }

      if (!result) {
        throw new Error('A verificação não retornou resultado.');
      }

      setVerifyResult(result);
      setStatus(`Verificação concluída: ${result.errors} erro(s), ${result.warnings} aviso(s).`);
      setProgress(100);
      setProgressStage('Concluído');
    } catch (error) {
      const message = toUserFriendlyError(error, 'Falha na verificação.');
      setStatus(`Falha na verificação: ${message}`);
      setProgressStage('Falha');
    } finally {
      setBusy(false);
    }
  };

  const runRecover = async () => {
    if (!filePath.trim()) {
      setStatus('Selecione um arquivo antes de recuperar.');
      return;
    }
    setBusy(true);
    setStatus('Executando recuperação...');
    try {
      const result = await recoverFile(filePath.trim(), MODE_MAP[recoverMode], previewOnly);
      const health = Number(result.health_score ?? 0);
      const output = String(result.output ?? '');
      setStatus(`Recuperação finalizada${previewOnly ? ' (preview)' : ''}. Score: ${health}${output ? ` • ${output}` : ''}`);
    } catch (error) {
      const message = toUserFriendlyError(error, 'Falha na recuperação.');
      setStatus(`Falha na recuperação: ${message}`);
    } finally {
      setBusy(false);
    }
  };

  const openReport = async (path?: string | null) => {
    if (!path) {
      setStatus('Relatório não disponível para esta execução.');
      return;
    }
    const ok = await openPath(path);
    if (!ok) {
      setStatus(`Não foi possível abrir: ${path}`);
    }
  };

  return (
    <>
      <section className="panel controls">
        <label className="label">Arquivo:</label>
        <div className="file-row">
          <input
            className="text-input"
            placeholder="Selecione ou informe um arquivo .DXF/.DWG"
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
          />
          <button className="primary" onClick={doPickFile} disabled={busy}>Abrir</button>
          <button className="soft" onClick={() => setFilePath('')} disabled={busy}>Limpar</button>
        </div>

        <p className="hint">Fluxo: 1) selecione arquivo DXF/DWG 2) clique em Verificar 3) abra os relatórios</p>

        <div className="run-row">
          <button className="primary large" onClick={runVerify} disabled={busy}>Verificar</button>
          {uiMode === 'Avançado' ? (
            <>
              <button className="primary large secondary" onClick={runRecover} disabled={busy}>Recuperar</button>
              <select className="select compact" value={recoverMode} onChange={(e) => setRecoverMode(e.target.value as ModeLabel)}>
                <option>Seguro</option>
                <option>Balanceado</option>
                <option>Agressivo</option>
              </select>
              <label className="check"><input type="checkbox" checked={previewOnly} onChange={(e) => setPreviewOnly(e.target.checked)} /> Preview</label>
            </>
          ) : null}
          <div className="status-line"><span className="status-icon">{busy ? '⏳' : '✅'}</span><span>{status}</span></div>
          <div className="badges">
            <span className="badge err">❌ {verifyResult?.errors ?? 0}</span>
            <span className="badge warn">⚠️ {verifyResult?.warnings ?? 0}</span>
            <span className="badge info">ℹ️ {verifyResult?.infos ?? 0}</span>
          </div>
          <button className="soft" onClick={() => void openReport(reports?.html)} disabled={busy || !reports?.html}>HTML</button>
          {uiMode === 'Avançado' ? (
            <>
              <button className="soft" onClick={() => void openReport(reports?.csv)} disabled={busy || !reports?.csv}>CSV</button>
              <button className="soft" onClick={() => void openReport(reports?.pdf)} disabled={busy || !reports?.pdf}>PDF</button>
              <button className="soft" onClick={() => void openReport(reports?.xlsx)} disabled={busy || !reports?.xlsx}>XLSX</button>
            </>
          ) : null}
        </div>

        {busy ? (
          <div className="progress-wrap" aria-live="polite">
            <div className="progress-head">
              <span className="spinner" />
              <strong>{progressStage || 'Processando...'}</strong>
              <span>{Math.max(1, Math.min(100, progress))}%</span>
            </div>
            <div className="progress-bar">
              <div className="progress-fill" style={{ width: `${Math.max(1, Math.min(100, progress))}%` }} />
            </div>
          </div>
        ) : null}

        <div className="mode-row">
          <span className="inline">Modo de interface:</span>
          <div className="segmented">
            <button className={uiMode === 'Básico' ? 'seg active' : 'seg'} onClick={() => setUiMode('Básico')}>Básico</button>
            <button className={uiMode === 'Avançado' ? 'seg active' : 'seg'} onClick={() => setUiMode('Avançado')}>Avançado</button>
          </div>
          <span className="hint-inline">{uiMode === 'Básico' ? 'Básico: foco em verificar + HTML' : 'Avançado: todos os controles'}</span>
          <button className="soft" onClick={() => onNavigate?.('batch')}>Recuperação em lote (Ctrl+Shift+R)</button>
        </div>
      </section>

      <section className="panel table-panel">
        <div className="table-header">
          <strong>Resultados</strong>
          <div className="table-tools">
            <input className="text-input mini" placeholder="Filtrar..." value={query} onChange={(e) => setQuery(e.target.value)} />
            <div className="segmented tiny">
              {(['Todos', 'ERROR', 'WARNING', 'INFO'] as const).map((item) => (
                <button key={item} className={severityFilter === item ? 'seg active' : 'seg'} onClick={() => setSeverityFilter(item)}>{item}</button>
              ))}
            </div>
          </div>
        </div>
        <div className="grid-head">
          <span>Severidade</span><span>Regra</span><span>Mensagem</span><span>Layer</span><span>Localização</span><span>Handle</span>
        </div>
        <div className="grid-body">
          {visibleRows.length === 0 ? <div className="empty-row">Nenhum arquivo verificado ainda</div> : null}
          {visibleRows.map((row, idx) => (
            <div className="row" key={`${row.rule}-${row.handle}-${idx}`}>
              <span>{row.severity}</span>
              <span>{row.rule}</span>
              <span>{row.message}</span>
              <span>{row.layer}</span>
              <span>{row.location}</span>
              <span>{row.handle}</span>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
