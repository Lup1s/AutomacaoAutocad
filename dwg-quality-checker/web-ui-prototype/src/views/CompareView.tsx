import { useMemo, useState } from 'react';
import { compareFiles, pickFile, type CompareItem } from '../desktopApi';

type CompareFilter = 'Todos' | 'Adicionado' | 'Removido' | 'Modificado';

export function CompareView() {
  const [fileA, setFileA] = useState('');
  const [fileB, setFileB] = useState('');
  const [status, setStatus] = useState('Selecione os arquivos A e B para comparar.');
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<CompareFilter>('Todos');
  const [rows, setRows] = useState<CompareItem[]>([]);

  const visibleRows = useMemo(() => {
    if (filter === 'Todos') {
      return rows;
    }
    return rows.filter((r) => r.type === filter);
  }, [rows, filter]);

  const pickA = async () => {
    const selected = await pickFile();
    if (selected) {
      setFileA(selected);
    }
  };

  const pickB = async () => {
    const selected = await pickFile();
    if (selected) {
      setFileB(selected);
    }
  };

  const runCompare = async () => {
    if (!fileA.trim() || !fileB.trim()) {
      setStatus('Selecione revisão A e B antes de comparar.');
      return;
    }
    setBusy(true);
    setStatus('Comparando revisões...');
    try {
      const result = await compareFiles(fileA.trim(), fileB.trim());
      setRows(result.items ?? []);
      setStatus(
        `Comparação concluída: +${result.added} / -${result.removed} / ~${result.modified} (total ${result.total})`,
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setStatus(`Falha na comparação: ${message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Comparar Revisões</strong>
        <span className="hint-inline">Selecione revisão A e B para listar diferenças.</span>
      </div>

      <div className="stack-fields">
        <div className="file-row">
          <label className="inline">Revisão anterior (A):</label>
          <input className="text-input" placeholder="Selecionar arquivo .DXF..." value={fileA} onChange={(e) => setFileA(e.target.value)} />
          <button className="soft" onClick={pickA} disabled={busy}>Abrir</button>
        </div>
        <div className="file-row">
          <label className="inline">Revisão nova (B):</label>
          <input className="text-input" placeholder="Selecionar arquivo .DXF..." value={fileB} onChange={(e) => setFileB(e.target.value)} />
          <button className="soft" onClick={pickB} disabled={busy}>Abrir</button>
        </div>
      </div>

      <div className="file-row">
        <button className="primary" onClick={() => void runCompare()} disabled={busy}>Comparar</button>
        <button className="soft" onClick={() => { const a = fileA; setFileA(fileB); setFileB(a); }} disabled={busy}>Trocar</button>
        <button className="soft" onClick={() => { setRows([]); setStatus('Comparação limpa.'); }} disabled={busy}>Limpar</button>
        <div className="segmented tiny">
          {(['Todos', 'Adicionado', 'Removido', 'Modificado'] as const).map((item) => (
            <button key={item} className={filter === item ? 'seg active' : 'seg'} onClick={() => setFilter(item)}>{item}</button>
          ))}
        </div>
      </div>

      <p className="hint">{status}</p>

      <div className="list-table">
        <div className="list-head four">
          <span>Tipo</span><span>Layer</span><span>Handle</span><span>Detalhe</span>
        </div>
        <div className="list-body">
          {visibleRows.length === 0 ? <div className="empty-row">Sem diferenças para exibir.</div> : null}
          {visibleRows.map((r) => (
            <div className="list-row four" key={`${r.handle}-${r.type}`}>
              <span>{r.type}</span><span>{r.layer}</span><span>{r.handle}</span><span>{r.detail}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
