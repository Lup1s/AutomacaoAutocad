const diffRows = [
  { type: 'Adicionado', layer: 'TEXTO', handle: 'A1F2', detail: 'MTEXT adicionado na revisão B' },
  { type: 'Modificado', layer: 'COTA', handle: 'B9C0', detail: 'DIMENSION alterada na revisão B' },
  { type: 'Removido', layer: 'EIXO', handle: 'C330', detail: 'LINE removida na revisão B' },
];

export function CompareView() {
  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Comparar Revisões</strong>
        <span className="hint-inline">Selecione revisão A e B para listar diferenças.</span>
      </div>

      <div className="stack-fields">
        <div className="file-row">
          <label className="inline">Revisão anterior (A):</label>
          <input className="text-input" placeholder="Selecionar arquivo .DXF..." />
          <button className="soft">Abrir</button>
        </div>
        <div className="file-row">
          <label className="inline">Revisão nova (B):</label>
          <input className="text-input" placeholder="Selecionar arquivo .DXF..." />
          <button className="soft">Abrir</button>
        </div>
      </div>

      <div className="file-row">
        <button className="primary">Comparar</button>
        <button className="soft">Trocar</button>
        <button className="soft">Limpar</button>
        <div className="segmented tiny">
          <button className="seg active">Todos</button>
          <button className="seg">Adicionado</button>
          <button className="seg">Removido</button>
          <button className="seg">Modificado</button>
        </div>
      </div>

      <div className="list-table">
        <div className="list-head four">
          <span>Tipo</span><span>Layer</span><span>Handle</span><span>Detalhe</span>
        </div>
        <div className="list-body">
          {diffRows.map((r) => (
            <div className="list-row four" key={`${r.handle}-${r.type}`}>
              <span>{r.type}</span><span>{r.layer}</span><span>{r.handle}</span><span>{r.detail}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
