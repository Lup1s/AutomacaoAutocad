import { useEffect, useMemo, useState } from 'react';
import { fetchDiagnostics, type DiagnosticsResult } from '../desktopApi';

export function DiagnosticsView() {
  const [diagnostics, setDiagnostics] = useState<DiagnosticsResult | null>(null);
  const [status, setStatus] = useState('Carregando diagnóstico...');

  const loadDiagnostics = async () => {
    try {
      const data = await fetchDiagnostics();
      if (!data) {
        setStatus('Diagnóstico real disponível apenas no modo desktop.');
        setDiagnostics(null);
        return;
      }
      setDiagnostics(data);
      setStatus('Diagnóstico atualizado.');
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus(`Falha ao atualizar: ${message}`);
    }
  };

  useEffect(() => {
    void loadDiagnostics();
  }, []);

  const text = useMemo(() => JSON.stringify(diagnostics ?? { message: status }, null, 2), [diagnostics, status]);

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setStatus('Diagnóstico copiado para a área de transferência.');
    } catch {
      setStatus('Falha ao copiar diagnóstico.');
    }
  };

  const saveToFile = () => {
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'diagnostics.json';
    a.click();
    URL.revokeObjectURL(url);
    setStatus('Arquivo diagnostics.json exportado.');
  };

  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Diagnóstico do Ambiente</strong>
        <span className="hint-inline">Painel técnico para suporte.</span>
      </div>

      <p className="hint">{status}</p>
      <pre className="diagnostic-box">{text}</pre>

      <div className="file-row">
        <button className="soft" onClick={() => void loadDiagnostics()}>Atualizar</button>
        <button className="soft" onClick={() => void copyToClipboard()}>Copiar</button>
        <button className="soft" onClick={saveToFile}>Salvar</button>
      </div>
    </section>
  );
}
