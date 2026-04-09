import { useEffect, useMemo, useState } from 'react';
import {
  deleteProfile,
  getConfigState,
  getUiBootState,
  listProfiles,
  loadProfile,
  saveConfigState,
  saveProfile,
  saveUiBootState,
  type AppConfig,
  type UiBootState,
} from '../desktopApi';

type DrawingFlag =
  | 'check_entities_on_layer_0'
  | 'check_unused_blocks'
  | 'check_empty_layers'
  | 'check_xrefs'
  | 'check_external_fonts'
  | 'check_plot_styles';

type ConfigForm = {
  requiredLayers: string;
  namingConvention: string;
  minHeight: string;
  maxHeight: string;
  drawing: Record<DrawingFlag, boolean>;
};

const EMPTY_FORM: ConfigForm = {
  requiredLayers: '',
  namingConvention: '',
  minHeight: '0.03',
  maxHeight: '50.0',
  drawing: {
    check_entities_on_layer_0: true,
    check_unused_blocks: true,
    check_empty_layers: true,
    check_xrefs: true,
    check_external_fonts: true,
    check_plot_styles: true,
  },
};

function toForm(cfg: AppConfig | null): ConfigForm {
  if (!cfg) {
    return EMPTY_FORM;
  }
  const required = Array.isArray(cfg.layers?.required) ? cfg.layers?.required ?? [] : [];
  return {
    requiredLayers: required.join(', '),
    namingConvention: String(cfg.layers?.naming_convention ?? ''),
    minHeight: String(cfg.text?.min_height ?? 0.03),
    maxHeight: String(cfg.text?.max_height ?? 50.0),
    drawing: {
      check_entities_on_layer_0: Boolean(cfg.drawing?.check_entities_on_layer_0 ?? true),
      check_unused_blocks: Boolean(cfg.drawing?.check_unused_blocks ?? true),
      check_empty_layers: Boolean(cfg.drawing?.check_empty_layers ?? true),
      check_xrefs: Boolean(cfg.drawing?.check_xrefs ?? true),
      check_external_fonts: Boolean(cfg.drawing?.check_external_fonts ?? true),
      check_plot_styles: Boolean(cfg.drawing?.check_plot_styles ?? true),
    },
  };
}

function toConfig(form: ConfigForm): AppConfig {
  const required = form.requiredLayers
    .split(',')
    .map((v) => v.trim())
    .filter(Boolean);

  return {
    layers: {
      required,
      naming_convention: form.namingConvention,
    },
    text: {
      min_height: Number(form.minHeight || '0.03'),
      max_height: Number(form.maxHeight || '50'),
    },
    drawing: {
      check_entities_on_layer_0: form.drawing.check_entities_on_layer_0,
      check_unused_blocks: form.drawing.check_unused_blocks,
      check_empty_layers: form.drawing.check_empty_layers,
      check_xrefs: form.drawing.check_xrefs,
      check_external_fonts: form.drawing.check_external_fonts,
      check_plot_styles: form.drawing.check_plot_styles,
    },
  };
}

export function ConfigView() {
  const [status, setStatus] = useState('Carregando configurações...');
  const [activeTab, setActiveTab] = useState<'geral' | 'layers' | 'textos' | 'desenho'>('geral');
  const [form, setForm] = useState<ConfigForm>(EMPTY_FORM);
  const [uiBoot, setUiBoot] = useState<UiBootState>({ mode: 'auto', fallback_to_legacy: true });
  const [profiles, setProfiles] = useState<string[]>([]);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [newProfileName, setNewProfileName] = useState('');

  const profileOptions = useMemo(() => profiles, [profiles]);

  const refresh = async () => {
    const [cfg, profs, boot] = await Promise.all([getConfigState(), listProfiles(), getUiBootState()]);
    setForm(toForm(cfg));
    setProfiles(profs);
    if (boot) {
      setUiBoot(boot);
    }
    if (profs.length > 0 && !selectedProfile) {
      setSelectedProfile(profs[0]);
    }
    setStatus('Configuração carregada.');
  };

  useEffect(() => {
    void refresh();
  }, []);

  const updateFlag = (flag: DrawingFlag, checked: boolean) => {
    setForm((prev) => ({
      ...prev,
      drawing: {
        ...prev.drawing,
        [flag]: checked,
      },
    }));
  };

  const onSaveConfig = async () => {
    const okCfg = await saveConfigState(toConfig(form));
    const okBoot = await saveUiBootState(uiBoot);
    if (okCfg && okBoot) {
      setStatus('Configuração salva em config.yaml e ui_boot.json.');
      return;
    }
    if (okCfg && !okBoot) {
      setStatus('Configuração salva, mas falhou ao gravar política de boot.');
      return;
    }
    setStatus('Falha ao salvar configuração.');
  };

  const onApplyProfile = async () => {
    if (!selectedProfile) {
      setStatus('Selecione um perfil para aplicar.');
      return;
    }
    const cfg = await loadProfile(selectedProfile);
    if (!cfg) {
      setStatus('Falha ao carregar perfil.');
      return;
    }
    setForm(toForm(cfg));
    setStatus(`Perfil '${selectedProfile}' aplicado na tela.`);
  };

  const onSaveProfile = async () => {
    const name = newProfileName.trim();
    if (!name) {
      setStatus('Informe um nome para salvar perfil.');
      return;
    }
    const ok = await saveProfile(name, toConfig(form));
    if (!ok) {
      setStatus('Falha ao salvar perfil.');
      return;
    }
    setStatus(`Perfil '${name}' salvo.`);
    setNewProfileName('');
    await refresh();
    setSelectedProfile(name);
  };

  const onDeleteProfile = async () => {
    if (!selectedProfile) {
      setStatus('Selecione um perfil para excluir.');
      return;
    }
    const ok = await deleteProfile(selectedProfile);
    setStatus(ok ? `Perfil '${selectedProfile}' excluído.` : 'Falha ao excluir perfil.');
    await refresh();
  };

  return (
    <section className="panel page-panel">
      <div className="page-header">
        <strong>Configurações</strong>
        <span className="hint-inline">Configuração real com leitura/gravação de config e perfis.</span>
      </div>

      <p className="hint">{status}</p>

      <div className="file-row">
        <label className="inline">Perfil:</label>
        <select className="select" value={selectedProfile} onChange={(e) => setSelectedProfile(e.target.value)}>
          {profileOptions.length === 0 ? <option value="">(sem perfis)</option> : null}
          {profileOptions.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>
        <button className="soft" onClick={() => void onApplyProfile()}>Aplicar perfil</button>
        <input
          className="text-input mini"
          placeholder="Nome do novo perfil"
          value={newProfileName}
          onChange={(e) => setNewProfileName(e.target.value)}
        />
        <button className="soft" onClick={() => void onSaveProfile()}>Salvar perfil</button>
        <button className="soft" onClick={() => void onDeleteProfile()}>Excluir perfil</button>
      </div>

      <div className="config-layout">
        <aside className="config-tabs">
          <button className={activeTab === 'geral' ? 'seg active' : 'seg'} onClick={() => setActiveTab('geral')}>⚙️ Geral</button>
          <button className={activeTab === 'layers' ? 'seg active' : 'seg'} onClick={() => setActiveTab('layers')}>🗂 Layers</button>
          <button className={activeTab === 'textos' ? 'seg active' : 'seg'} onClick={() => setActiveTab('textos')}>✏️ Textos</button>
          <button className={activeTab === 'desenho' ? 'seg active' : 'seg'} onClick={() => setActiveTab('desenho')}>📐 Desenho</button>
        </aside>

        <div className="config-body">
          {activeTab === 'geral' ? (
            <div className="file-row">
              <label className="inline">Inicialização da UI:</label>
              <select
                className="select compact"
                value={uiBoot.mode}
                onChange={(e) => setUiBoot((prev) => ({ ...prev, mode: e.target.value as UiBootState['mode'] }))}
              >
                <option value="auto">auto</option>
                <option value="web">web</option>
                <option value="legacy">legacy</option>
              </select>
              <label className="check">
                <input
                  type="checkbox"
                  checked={uiBoot.fallback_to_legacy}
                  onChange={(e) => setUiBoot((prev) => ({ ...prev, fallback_to_legacy: e.target.checked }))}
                />
                Fallback para legacy
              </label>
            </div>
          ) : null}

          {activeTab === 'layers' ? (
            <div className="form-grid">
              <label>
                Layers obrigatórias
                <input
                  className="text-input"
                  placeholder="Ex: TEXTO, COTA"
                  value={form.requiredLayers}
                  onChange={(e) => setForm((p) => ({ ...p, requiredLayers: e.target.value }))}
                />
              </label>
              <label>
                Regex de nomenclatura
                <input
                  className="text-input"
                  placeholder="^[A-Z]{2,4}-[A-Z0-9_-]+$"
                  value={form.namingConvention}
                  onChange={(e) => setForm((p) => ({ ...p, namingConvention: e.target.value }))}
                />
              </label>
            </div>
          ) : null}

          {activeTab === 'textos' ? (
            <div className="form-grid">
              <label>
                Altura mínima de texto
                <input className="text-input" value={form.minHeight} onChange={(e) => setForm((p) => ({ ...p, minHeight: e.target.value }))} />
              </label>
              <label>
                Altura máxima de texto
                <input className="text-input" value={form.maxHeight} onChange={(e) => setForm((p) => ({ ...p, maxHeight: e.target.value }))} />
              </label>
            </div>
          ) : null}

          {activeTab === 'desenho' ? (
            <div className="check-grid">
              <label className="check"><input type="checkbox" checked={form.drawing.check_entities_on_layer_0} onChange={(e) => updateFlag('check_entities_on_layer_0', e.target.checked)} /> Entidades na Layer 0</label>
              <label className="check"><input type="checkbox" checked={form.drawing.check_unused_blocks} onChange={(e) => updateFlag('check_unused_blocks', e.target.checked)} /> Blocos não utilizados</label>
              <label className="check"><input type="checkbox" checked={form.drawing.check_empty_layers} onChange={(e) => updateFlag('check_empty_layers', e.target.checked)} /> Layers vazias</label>
              <label className="check"><input type="checkbox" checked={form.drawing.check_xrefs} onChange={(e) => updateFlag('check_xrefs', e.target.checked)} /> XREFs acessíveis</label>
              <label className="check"><input type="checkbox" checked={form.drawing.check_external_fonts} onChange={(e) => updateFlag('check_external_fonts', e.target.checked)} /> Fontes externas</label>
              <label className="check"><input type="checkbox" checked={form.drawing.check_plot_styles} onChange={(e) => updateFlag('check_plot_styles', e.target.checked)} /> Plot styles</label>
            </div>
          ) : null}

          <div className="file-row">
            <button className="primary" onClick={() => void onSaveConfig()}>Salvar</button>
            <button className="soft" onClick={() => void refresh()}>Recarregar</button>
          </div>
        </div>
      </div>
    </section>
  );
}
