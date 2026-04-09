const historyRows = [
  { date: '09/04/2026 10:14', file: 'fachada_v3.dxf', status: '✅ Aprovado', errors: 0, warnings: 2 },
  { date: '09/04/2026 09:02', file: 'estrutural_rev2.dxf', status: '❌ Reprovado', errors: 4, warnings: 1 },
];

export function HistoryView() {
  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Histórico de Verificações</strong>
        <span className="hint-inline">Duplo clique para abrir o relatório HTML.</span>
      </div>

      <div className="list-table">
        <div className="list-head five">
          <span>Data/Hora</span><span>Arquivo</span><span>Status</span><span>Erros</span><span>Avisos</span>
        </div>
        <div className="list-body">
          {historyRows.map((r) => (
            <div className="list-row five" key={`${r.date}-${r.file}`}>
              <span>{r.date}</span><span>{r.file}</span><span>{r.status}</span><span>{r.errors}</span><span>{r.warnings}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
