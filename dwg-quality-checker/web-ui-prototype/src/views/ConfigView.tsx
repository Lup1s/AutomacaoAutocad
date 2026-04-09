export function ConfigView() {
  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Configurações</strong>
        <span className="hint-inline">Protótipo das abas: Geral, Layers, Textos e Desenho.</span>
      </div>

      <div className="config-layout">
        <aside className="config-tabs">
          <button className="seg active">⚙️ Geral</button>
          <button className="seg">🗂 Layers</button>
          <button className="seg">✏️ Textos</button>
          <button className="seg">📐 Desenho</button>
        </aside>

        <div className="config-body">
          <div className="form-grid">
            <label>Layer obrigatória
              <input className="text-input" placeholder="Ex: TEXTO" />
            </label>
            <label>Regex de nomenclatura
              <input className="text-input" placeholder="^[A-Z]{2,4}-[A-Z0-9_-]+$" />
            </label>
            <label>Altura mínima de texto
              <input className="text-input" defaultValue="0.03" />
            </label>
            <label>Altura máxima de texto
              <input className="text-input" defaultValue="50.0" />
            </label>
          </div>

          <div className="check-grid">
            <label className="check"><input type="checkbox" defaultChecked /> Entidades na Layer 0</label>
            <label className="check"><input type="checkbox" defaultChecked /> Blocos não utilizados</label>
            <label className="check"><input type="checkbox" defaultChecked /> Layers vazias</label>
            <label className="check"><input type="checkbox" defaultChecked /> XREFs acessíveis</label>
            <label className="check"><input type="checkbox" defaultChecked /> Fontes externas</label>
            <label className="check"><input type="checkbox" defaultChecked /> Plot styles</label>
          </div>

          <div className="file-row">
            <button className="primary">Salvar</button>
            <button className="soft">Fechar</button>
          </div>
        </div>
      </div>
    </section>
  );
}
