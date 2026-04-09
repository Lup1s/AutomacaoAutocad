import { useEffect, useState } from 'react';
import { getWatchEvents, getWatchState, openPath, pickFolder, startWatch, stopWatch, type WatchEvent } from '../desktopApi';

export function WatchView() {
  const [folderPath, setFolderPath] = useState('');
  const [intervalSec, setIntervalSec] = useState('5');
  const [watching, setWatching] = useState(false);
  const [status, setStatus] = useState('Watch parado.');
  const [rows, setRows] = useState<WatchEvent[]>([]);

  const refreshState = async () => {
    const state = await getWatchState();
    if (!state) {
      setStatus('Watch real disponível apenas no modo desktop.');
      return;
    }
    setWatching(Boolean(state.watching));
    setFolderPath(state.folder || folderPath);
    setIntervalSec(String(state.interval || 5));
    setStatus(state.watching ? `▶ Monitorando (${state.interval}s)` : 'Watch parado.');
  };

  const refreshRows = async () => {
    const events = await getWatchEvents(300);
    setRows(events);
  };

  useEffect(() => {
    void refreshState();
    void refreshRows();

    const timer = window.setInterval(() => {
      void refreshState();
      void refreshRows();
    }, 1500);
    return () => window.clearInterval(timer);
  }, []);

  const browseFolder = async () => {
    const selected = await pickFolder();
    if (selected) {
      setFolderPath(selected);
    }
  };

  const toggleWatch = async () => {
    if (watching) {
      await stopWatch();
      await refreshState();
      return;
    }

    const value = Number(intervalSec);
    const interval = Number.isFinite(value) ? Math.max(3, Math.floor(value)) : 5;
    if (!folderPath.trim()) {
      setStatus('Selecione uma pasta antes de iniciar.');
      return;
    }
    try {
      await startWatch(folderPath.trim(), interval);
      await refreshState();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus(`Falha ao iniciar watch: ${message}`);
    }
  };

  const openEventReport = async (row: WatchEvent) => {
    const target = row.html_path || row.file_path || '';
    if (!target) {
      setStatus('Evento sem caminho para abrir.');
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
        <strong>Watch Folder</strong>
        <span className="hint-inline">Monitore uma pasta e verifique DXFs novos/alterados.</span>
      </div>

      <div className="file-row">
        <input
          className="text-input"
          placeholder="Selecione uma pasta para monitorar..."
          value={folderPath}
          onChange={(e) => setFolderPath(e.target.value)}
        />
        <button className="soft" onClick={browseFolder}>Pasta</button>
        <button className="primary" onClick={() => void toggleWatch()}>{watching ? 'Parar monitoramento' : 'Iniciar monitoramento'}</button>
        <label className="inline">Intervalo (s):</label>
        <input className="text-input mini" value={intervalSec} onChange={(e) => setIntervalSec(e.target.value)} />
      </div>

      <p className="hint">{status}</p>

      <div className="list-table">
        <div className="list-head five">
          <span>Hora</span><span>Arquivo</span><span>Status</span><span>Erros</span><span>Avisos</span>
        </div>
        <div className="list-body">
          {rows.length === 0 ? <div className="empty-row">Sem eventos de watch.</div> : null}
          {rows.map((r, idx) => (
            <div className="list-row five clickable" key={`${r.time}-${r.file}-${idx}`} onDoubleClick={() => void openEventReport(r)}>
              <span>{r.time}</span><span>{r.file}</span><span>{r.status}</span><span>{r.errors}</span><span>{r.warnings}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
