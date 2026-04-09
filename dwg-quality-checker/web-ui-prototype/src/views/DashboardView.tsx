import { useMemo, useState } from 'react';

type Severity = 'ERROR' | 'WARNING' | 'INFO';

type Issue = {
  severity: Severity;
  rule: string;
  message: string;
  layer: string;
  location: string;
  handle: string;
};

const rows: Issue[] = [];

export function DashboardView() {
  const [uiMode, setUiMode] = useState<'Básico' | 'Avançado'>('Básico');
  const [severityFilter, setSeverityFilter] = useState<'Todos' | Severity>('Todos');
  const [query, setQuery] = useState('');

  const visibleRows = useMemo(() => {
    return rows.filter((row) => {
      const passSeverity = severityFilter === 'Todos' || row.severity === severityFilter;
      const q = query.trim().toLowerCase();
      const passText =
        !q || [row.rule, row.message, row.layer, row.location, row.handle].some((v) => v.toLowerCase().includes(q));
      return passSeverity && passText;
    });
  }, [query, severityFilter]);

  return (
    <>
      <section className="panel controls">
        <label className="label">Arquivo:</label>
        <div className="file-row">
          <input className="text-input" placeholder="Selecione ou arraste um arquivo .DXF ou .DWG aqui..." />
          <button className="primary">Abrir</button>
          <button className="soft">Pasta</button>
          <button className="soft">Limpar</button>
        </div>

        <p className="hint">Fluxo: 1) selecione arquivo DXF/DWG 2) clique em Verificar 3) abra os relatórios</p>

        <div className="run-row">
          <button className="primary large">Verificar</button>
          <button className="primary large secondary">Recuperar</button>
          <select className="select compact" defaultValue="Balanceado">
            <option>Seguro</option>
            <option>Balanceado</option>
            <option>Agressivo</option>
          </select>
          <label className="check"><input type="checkbox" /> Strict</label>
          <label className="inline">Perfil:</label>
          <select className="select" defaultValue="config.yaml(base)">
            <option>config.yaml(base)</option>
            <option>NBR_5410</option>
            <option>NBR_9050</option>
          </select>
          <input className="text-input mini" placeholder="NBR_5410, NBR_9050" />
          <div className="status-line"><span className="status-icon">⏳</span><span>Aguardando arquivo para iniciar</span></div>
          <div className="badges">
            <span className="badge err">❌ 0</span>
            <span className="badge warn">⚠️ 0</span>
            <span className="badge info">ℹ️ 0</span>
          </div>
          <button className="soft">HTML</button>
          <button className="soft">CSV</button>
          <button className="soft">PDF</button>
          <button className="soft">XLSX</button>
          <button className="soft">Anotar DXF</button>
          <button className="soft">Saída</button>
          <label className="check"><input type="checkbox" defaultChecked /> Auto HTML</label>
        </div>

        <div className="mode-row">
          <span className="inline">Modo de interface:</span>
          <div className="segmented">
            <button className={uiMode === 'Básico' ? 'seg active' : 'seg'} onClick={() => setUiMode('Básico')}>Básico</button>
            <button className={uiMode === 'Avançado' ? 'seg active' : 'seg'} onClick={() => setUiMode('Avançado')}>Avançado</button>
          </div>
          <span className="hint-inline">{uiMode === 'Básico' ? 'Básico: foco em verificar + HTML' : 'Avançado: todos os controles'}</span>
          <button className="soft">Recuperação em lote (Ctrl+Shift+R)</button>
        </div>
      </section>

      <section className="panel table-panel">
        <div className="table-header">
          <strong>Resultados</strong>
          <div className="table-tools">
            <input className="text-input mini" placeholder="Filtrar..." value={query} onChange={(e) => setQuery(e.target.value)} />
            <div className="segmented tiny">
              {(['Todos', 'ERROR', 'WARNING', 'INFO'] as const).map((item) => (
                <button key={item} className={severityFilter === item ? 'seg active' : 'seg'} onClick={() => setSeverityFilter(item)}>{item}</button>
              ))}
            </div>
          </div>
        </div>
        <div className="grid-head">
          <span>Severidade</span><span>Regra</span><span>Mensagem</span><span>Layer</span><span>Localização</span><span>Handle</span>
        </div>
        <div className="grid-body">
          {visibleRows.length === 0 ? <div className="empty-row">Nenhum arquivo verificado ainda</div> : null}
        </div>
      </section>
    </>
  );
}
