const watchRows = [
  { time: '10:11:30', file: 'implantacao.dxf', status: '✅ OK', errors: 0, warnings: 0 },
  { time: '10:13:08', file: 'detalhe_hidraulico.dxf', status: '❌ FALHOU', errors: 2, warnings: 1 },
];

export function WatchView() {
  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Watch Folder</strong>
        <span className="hint-inline">Monitore uma pasta e verifique DXFs novos/alterados.</span>
      </div>

      <div className="file-row">
        <input className="text-input" placeholder="Selecione uma pasta para monitorar..." />
        <button className="soft">Pasta</button>
        <button className="primary">Iniciar monitoramento</button>
        <button className="soft">Parar monitoramento</button>
        <label className="inline">Intervalo (s):</label>
        <input className="text-input mini" defaultValue="5" />
      </div>

      <p className="hint">▶ Monitorando — verificando a cada 5s</p>

      <div className="list-table">
        <div className="list-head five">
          <span>Hora</span><span>Arquivo</span><span>Status</span><span>Erros</span><span>Avisos</span>
        </div>
        <div className="list-body">
          {watchRows.map((r) => (
            <div className="list-row five" key={`${r.time}-${r.file}`}>
              <span>{r.time}</span><span>{r.file}</span><span>{r.status}</span><span>{r.errors}</span><span>{r.warnings}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
