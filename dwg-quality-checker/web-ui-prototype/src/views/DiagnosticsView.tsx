const diagnostics = {
  timestamp: '2026-04-09T11:42:00',
  app_version: '2.7.9',
  platform: 'Windows 11',
  python_version: '3.12.10',
  oda_found: true,
  dnd_enabled: true,
  auth_mode: 'local + supabase',
};

export function DiagnosticsView() {
  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Diagnóstico do Ambiente</strong>
        <span className="hint-inline">Painel técnico para suporte.</span>
      </div>

      <pre className="diagnostic-box">{JSON.stringify(diagnostics, null, 2)}</pre>

      <div className="file-row">
        <button className="soft">Atualizar</button>
        <button className="soft">Copiar</button>
        <button className="soft">Salvar</button>
        <button className="primary">Fechar</button>
      </div>
    </section>
  );
}
