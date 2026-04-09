export function AboutView({ onClose }: { onClose?: () => void }) {
  return (
    <section className="panel page-panel center-panel">
      <div className="logo large">🏗️</div>
      <h2>DWG Quality Checker</h2>
      <p className="hint-inline">Versão 3.0.1 • Protótipo de interface web</p>
      <p className="hint-inline">Vantara Tech • Luiz Q. Melo • luiz.queiroz240202@gmail.com</p>
      <button className="soft" onClick={onClose}>Fechar</button>
    </section>
  );
}
