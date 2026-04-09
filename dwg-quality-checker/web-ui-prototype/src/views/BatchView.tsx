const batchRows = [
  { file: 'projeto_A.dxf', status: '✅ OK', errors: 0, warnings: 1 },
  { file: 'projeto_B.dxf', status: '❌ FALHOU', errors: 3, warnings: 2 },
  { file: 'projeto_C.dxf', status: '⏳ Aguardando', errors: 0, warnings: 0 },
];

export function BatchView() {
  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Verificação em Lote</strong>
        <span className="hint-inline">Escolha a pasta, inicie o lote e acompanhe por arquivo.</span>
      </div>

      <div className="file-row">
        <input className="text-input" placeholder="Selecione uma pasta com arquivos DXF..." />
        <button className="soft">Pasta</button>
        <button className="primary">Iniciar Lote</button>
        <button className="soft">Parar</button>
        <button className="soft">Limpar</button>
        <button className="soft">Dashboard</button>
      </div>

      <p className="hint">Processando 2/3 • aguarde...</p>

      <div className="list-table">
        <div className="list-head four">
          <span>Arquivo</span><span>Status</span><span>Erros</span><span>Avisos</span>
        </div>
        <div className="list-body">
          {batchRows.map((r) => (
            <div className="list-row four" key={r.file}>
              <span>{r.file}</span><span>{r.status}</span><span>{r.errors}</span><span>{r.warnings}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
