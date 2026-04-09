import { useEffect, useState } from 'react';
import { listHistory, openPath, type HistoryRow } from '../desktopApi';

export function HistoryView() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [status, setStatus] = useState('Carregando histórico...');

  const loadHistory = async () => {
    try {
      const data = await listHistory();
      setRows(data ?? []);
      setStatus(`Histórico carregado: ${(data ?? []).length} registro(s).`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus(`Falha ao carregar histórico: ${message}`);
    }
  };

  useEffect(() => {
    void loadHistory();
  }, []);

  const openHistoryReport = async (row: HistoryRow) => {
    const target = row.html_path || row.file_path || '';
    if (!target) {
      setStatus('Registro sem caminho de relatório/arquivo.');
      return;
    }
    const ok = await openPath(target);
    if (!ok) {
      setStatus(`Não foi possível abrir: ${target}`);
    }
  };

  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Histórico de Verificações</strong>
        <span className="hint-inline">Duplo clique para abrir o relatório HTML.</span>
      </div>

      <div className="file-row">
        <button className="soft" onClick={() => void loadHistory()}>Atualizar</button>
        <span className="hint-inline">{status}</span>
      </div>

      <div className="list-table">
        <div className="list-head five">
          <span>Data/Hora</span><span>Arquivo</span><span>Status</span><span>Erros</span><span>Avisos</span>
        </div>
        <div className="list-body">
          {rows.length === 0 ? <div className="empty-row">Histórico vazio</div> : null}
          {rows.map((r, index) => (
            <div className="list-row five clickable" key={`${r.timestamp ?? ''}-${r.file ?? ''}-${index}`} onDoubleClick={() => void openHistoryReport(r)}>
              <span>{r.timestamp ?? '-'}</span>
              <span>{r.file ?? '-'}</span>
              <span>{r.passed ? '✅ Aprovado' : '❌ Reprovado'}</span>
              <span>{r.errors ?? 0}</span>
              <span>{r.warnings ?? 0}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
