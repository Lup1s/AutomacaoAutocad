export type Severity = 'ERROR' | 'WARNING' | 'INFO';

export type DesktopIssue = {
  severity: Severity;
  rule: string;
  message: string;
  entity_type: string;
  layer: string;
  location: string;
  handle: string;
  details: string;
};

export type VerifyResult = {
  file: string;
  passed: boolean;
  errors: number;
  warnings: number;
  infos: number;
  total_issues: number;
  issues: DesktopIssue[];
  reports: {
    html?: string | null;
    csv?: string | null;
    pdf?: string | null;
    xlsx?: string | null;
  };
};

export type VerifyJobStatus = {
  found: boolean;
  job_id: string;
  state: 'running' | 'done' | 'error' | 'not_found';
  progress: number;
  stage: string;
  result?: VerifyResult | null;
  error?: string;
  created_at?: string;
  updated_at?: string;
};

export type RecoveryItem = {
  file: string;
  extension?: string;
  status: string;
  output?: string;
  report?: string;
  health_score?: number;
  issues?: number;
  error?: string;
  attempts?: number;
  retries_used?: number;
  elapsed_seconds?: number;
};

export type RecoverFolderResult = {
  folder: string;
  timestamp: string;
  mode: string;
  preview_only: boolean;
  max_retries?: number;
  recursive: boolean;
  total: number;
  processed?: number;
  ok: number;
  fail: number;
  cancelled?: boolean;
  elapsed_seconds?: number;
  avg_seconds_per_file?: number;
  by_extension?: Record<
    string,
    {
      total: number;
      processed: number;
      ok: number;
      fail: number;
      avg_seconds: number;
      total_seconds: number;
    }
  >;
  items: RecoveryItem[];
  summary_file?: string;
};

export type RecoverJobStatus = {
  found: boolean;
  job_id: string;
  state: 'running' | 'paused' | 'done' | 'cancelled' | 'error' | 'not_found';
  progress: number;
  stage: string;
  processed: number;
  total: number;
  ok: number;
  fail: number;
  max_retries?: number;
  eta_seconds?: number | null;
  current_file?: string;
  cancel_requested?: boolean;
  pause_requested?: boolean;
  result?: RecoverFolderResult | null;
  error?: string;
  created_at?: string;
  updated_at?: string;
};

export type RecoverHistoryItem = RecoverJobStatus;

export type HistoryRow = {
  timestamp?: string;
  file?: string;
  file_path?: string;
  passed?: boolean;
  errors?: number;
  warnings?: number;
  infos?: number;
  total?: number;
  html_path?: string;
};

export type DiagnosticsResult = {
  app_version: string;
  platform: string;
  python: string;
  cwd: string;
  base_dir: string;
  history_exists: boolean;
};

export type CompareItem = {
  type: 'Adicionado' | 'Removido' | 'Modificado';
  layer: string;
  handle: string;
  detail: string;
};

export type CompareResult = {
  file_a: string;
  file_b: string;
  added: number;
  removed: number;
  modified: number;
  total: number;
  items: CompareItem[];
};

export type WatchState = {
  watching: boolean;
  folder: string;
  interval: number;
  events: number;
};

export type WatchEvent = {
  time: string;
  file: string;
  file_path: string;
  status: string;
  errors: number;
  warnings: number;
  html_path?: string;
  error?: string;
};

export type AppConfig = {
  layers?: {
    required?: string[];
    naming_convention?: string;
  };
  text?: {
    min_height?: number;
    max_height?: number;
  };
  drawing?: Record<string, boolean>;
  [key: string]: unknown;
};

export type UiBootState = {
  mode: 'auto' | 'web' | 'legacy';
  fallback_to_legacy: boolean;
};

export type AuthUser = {
  id: string;
  name: string;
  email: string;
};

export type AuthState = {
  enabled: boolean;
  backend: string;
  authenticated: boolean;
  user: AuthUser | null;
  can_register: boolean;
  require_subscription: boolean;
  config_error: string;
};

export type AuthActionResult = {
  ok: boolean;
  error?: string;
  message?: string;
  user?: AuthUser;
};

type DesktopApi = {
  get_bootstrap_state: () => Promise<unknown>;
  pick_file: () => Promise<string>;
  pick_folder: () => Promise<string>;
  open_path: (path: string) => Promise<boolean>;
  verify_file: (filePath: string) => Promise<VerifyResult>;
  start_verify: (filePath: string) => Promise<{ job_id: string }>;
  get_verify_status: (jobId: string) => Promise<VerifyJobStatus>;
  recover_file: (filePath: string, mode?: string, preview_only?: boolean) => Promise<Record<string, unknown>>;
  recover_folder: (folderPath: string, mode?: string, preview_only?: boolean) => Promise<RecoverFolderResult>;
  start_recover_folder: (folderPath: string, mode?: string, preview_only?: boolean, max_retries?: number) => Promise<{ job_id: string }>;
  get_recover_status: (jobId: string) => Promise<RecoverJobStatus>;
  cancel_recover: (jobId: string) => Promise<{ found: boolean; job_id: string; state: string; cancel_requested: boolean }>;
  pause_recover: (jobId: string) => Promise<{ found: boolean; job_id: string; state: string; pause_requested: boolean }>;
  resume_recover: (jobId: string) => Promise<{ found: boolean; job_id: string; state: string; pause_requested: boolean }>;
  list_recover_history: (limit?: number) => Promise<RecoverHistoryItem[]>;
  list_history: () => Promise<HistoryRow[]>;
  diagnostics: () => Promise<DiagnosticsResult>;
  compare_files: (fileA: string, fileB: string) => Promise<CompareResult>;
  get_watch_state: () => Promise<WatchState>;
  get_watch_events: (limit?: number) => Promise<WatchEvent[]>;
  start_watch: (folderPath: string, intervalSec?: number) => Promise<WatchState>;
  stop_watch: () => Promise<WatchState>;
  get_config_state: () => Promise<AppConfig>;
  save_config_state: (config: AppConfig) => Promise<boolean>;
  list_profiles: () => Promise<string[]>;
  load_profile: (profileName: string) => Promise<AppConfig>;
  save_profile: (profileName: string, config: AppConfig) => Promise<boolean>;
  delete_profile: (profileName: string) => Promise<boolean>;
  get_ui_boot_state: () => Promise<UiBootState>;
  save_ui_boot_state: (state: UiBootState) => Promise<boolean>;
  get_auth_state: () => Promise<AuthState>;
  auth_login: (email: string, password: string) => Promise<AuthActionResult>;
  auth_register: (name: string, email: string, password: string) => Promise<AuthActionResult>;
  auth_logout: () => Promise<boolean>;
};

type MaybePywebview = {
  api?: DesktopApi;
};

function getPywebview(): MaybePywebview | undefined {
  return (window as Window & { pywebview?: MaybePywebview }).pywebview;
}

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return String(error.message || '').trim();
  }
  return String(error ?? '').trim();
}

export function toUserFriendlyError(error: unknown, fallback = 'Operação falhou.'): string {
  const raw = extractErrorMessage(error);
  const lower = raw.toLowerCase();

  if (
    lower.includes('login obrigatório') ||
    lower.includes('sessão expirada') ||
    lower.includes('sessao expirada') ||
    lower.includes('sessão inválida') ||
    lower.includes('sessao invalida') ||
    lower.includes('permissionerror') ||
    lower.includes('not authenticated')
  ) {
    return 'Sua sessão expirou ou não está autenticada. Faça login novamente para continuar.';
  }

  const cleaned = raw
    .replace(/^javascript error:\s*/i, '')
    .replace(/^error:\s*/i, '')
    .trim();

  return cleaned || fallback;
}

export function isDesktopRuntime(): boolean {
  return Boolean(getPywebview()?.api);
}

export async function pickFile(): Promise<string> {
  return (await getPywebview()?.api?.pick_file?.()) ?? '';
}

export async function pickFolder(): Promise<string> {
  return (await getPywebview()?.api?.pick_folder?.()) ?? '';
}

export async function openPath(path: string): Promise<boolean> {
  if (!path) {
    return false;
  }
  if (getPywebview()?.api?.open_path) {
    return getPywebview()!.api!.open_path(path);
  }
  return false;
}

export async function verifyFile(filePath: string): Promise<VerifyResult> {
  if (!getPywebview()?.api?.verify_file) {
    throw new Error('Verificação real disponível apenas no modo desktop.');
  }
  return getPywebview()!.api!.verify_file(filePath);
}

export async function startVerify(filePath: string): Promise<string> {
  if (!getPywebview()?.api?.start_verify) {
    throw new Error('Verificação com progresso disponível apenas no modo desktop.');
  }
  const data = await getPywebview()!.api!.start_verify(filePath);
  return String(data?.job_id || '');
}

export async function getVerifyStatus(jobId: string): Promise<VerifyJobStatus> {
  if (!getPywebview()?.api?.get_verify_status) {
    throw new Error('Status de verificação disponível apenas no modo desktop.');
  }
  return getPywebview()!.api!.get_verify_status(jobId);
}

export async function recoverFile(filePath: string, mode: string, previewOnly: boolean): Promise<Record<string, unknown>> {
  if (!getPywebview()?.api?.recover_file) {
    throw new Error('Recuperação real disponível apenas no modo desktop.');
  }
  return getPywebview()!.api!.recover_file(filePath, mode, previewOnly);
}

export async function recoverFolder(folderPath: string, mode: string, previewOnly: boolean): Promise<RecoverFolderResult> {
  if (!getPywebview()?.api?.recover_folder) {
    throw new Error('Recuperação em lote real disponível apenas no modo desktop.');
  }
  return getPywebview()!.api!.recover_folder(folderPath, mode, previewOnly);
}

export async function startRecoverFolder(folderPath: string, mode: string, previewOnly: boolean, maxRetries = 1): Promise<string> {
  if (!getPywebview()?.api?.start_recover_folder) {
    throw new Error('Recuperação em lote com progresso disponível apenas no modo desktop.');
  }
  const data = await getPywebview()!.api!.start_recover_folder(folderPath, mode, previewOnly, maxRetries);
  return String(data?.job_id || '');
}

export async function getRecoverStatus(jobId: string): Promise<RecoverJobStatus> {
  if (!getPywebview()?.api?.get_recover_status) {
    throw new Error('Status de recuperação disponível apenas no modo desktop.');
  }
  return getPywebview()!.api!.get_recover_status(jobId);
}

export async function cancelRecover(jobId: string): Promise<boolean> {
  if (!getPywebview()?.api?.cancel_recover) {
    return false;
  }
  const data = await getPywebview()!.api!.cancel_recover(jobId);
  return Boolean(data?.found && data?.cancel_requested);
}

export async function pauseRecover(jobId: string): Promise<boolean> {
  if (!getPywebview()?.api?.pause_recover) {
    return false;
  }
  const data = await getPywebview()!.api!.pause_recover(jobId);
  return Boolean(data?.found && data?.pause_requested);
}

export async function resumeRecover(jobId: string): Promise<boolean> {
  if (!getPywebview()?.api?.resume_recover) {
    return false;
  }
  const data = await getPywebview()!.api!.resume_recover(jobId);
  return Boolean(data?.found && !data?.pause_requested);
}

export async function listRecoverHistory(limit = 20): Promise<RecoverHistoryItem[]> {
  if (!getPywebview()?.api?.list_recover_history) {
    return [];
  }
  return getPywebview()!.api!.list_recover_history(limit);
}

export async function listHistory(): Promise<HistoryRow[]> {
  if (!getPywebview()?.api?.list_history) {
    return [];
  }
  return getPywebview()!.api!.list_history();
}

export async function fetchDiagnostics(): Promise<DiagnosticsResult | null> {
  if (!getPywebview()?.api?.diagnostics) {
    return null;
  }
  return getPywebview()!.api!.diagnostics();
}

export async function compareFiles(fileA: string, fileB: string): Promise<CompareResult> {
  if (!getPywebview()?.api?.compare_files) {
    throw new Error('Comparação real disponível apenas no modo desktop.');
  }
  return getPywebview()!.api!.compare_files(fileA, fileB);
}

export async function getWatchState(): Promise<WatchState | null> {
  if (!getPywebview()?.api?.get_watch_state) {
    return null;
  }
  return getPywebview()!.api!.get_watch_state();
}

export async function getWatchEvents(limit = 200): Promise<WatchEvent[]> {
  if (!getPywebview()?.api?.get_watch_events) {
    return [];
  }
  return getPywebview()!.api!.get_watch_events(limit);
}

export async function startWatch(folderPath: string, intervalSec: number): Promise<WatchState> {
  if (!getPywebview()?.api?.start_watch) {
    throw new Error('Watch real disponível apenas no modo desktop.');
  }
  return getPywebview()!.api!.start_watch(folderPath, intervalSec);
}

export async function stopWatch(): Promise<WatchState | null> {
  if (!getPywebview()?.api?.stop_watch) {
    return null;
  }
  return getPywebview()!.api!.stop_watch();
}

export async function getConfigState(): Promise<AppConfig | null> {
  if (!getPywebview()?.api?.get_config_state) {
    return null;
  }
  return getPywebview()!.api!.get_config_state();
}

export async function saveConfigState(config: AppConfig): Promise<boolean> {
  if (!getPywebview()?.api?.save_config_state) {
    return false;
  }
  return getPywebview()!.api!.save_config_state(config);
}

export async function listProfiles(): Promise<string[]> {
  if (!getPywebview()?.api?.list_profiles) {
    return [];
  }
  return getPywebview()!.api!.list_profiles();
}

export async function loadProfile(profileName: string): Promise<AppConfig | null> {
  if (!getPywebview()?.api?.load_profile) {
    return null;
  }
  return getPywebview()!.api!.load_profile(profileName);
}

export async function saveProfile(profileName: string, config: AppConfig): Promise<boolean> {
  if (!getPywebview()?.api?.save_profile) {
    return false;
  }
  return getPywebview()!.api!.save_profile(profileName, config);
}

export async function deleteProfile(profileName: string): Promise<boolean> {
  if (!getPywebview()?.api?.delete_profile) {
    return false;
  }
  return getPywebview()!.api!.delete_profile(profileName);
}

export async function getUiBootState(): Promise<UiBootState | null> {
  if (!getPywebview()?.api?.get_ui_boot_state) {
    return null;
  }
  return getPywebview()!.api!.get_ui_boot_state();
}

export async function saveUiBootState(state: UiBootState): Promise<boolean> {
  if (!getPywebview()?.api?.save_ui_boot_state) {
    return false;
  }
  return getPywebview()!.api!.save_ui_boot_state(state);
}

export async function getAuthState(): Promise<AuthState | null> {
  if (!getPywebview()?.api?.get_auth_state) {
    return null;
  }
  return getPywebview()!.api!.get_auth_state();
}

export async function authLogin(email: string, password: string): Promise<AuthActionResult> {
  if (!getPywebview()?.api?.auth_login) {
    return {
      ok: false,
      error: 'Login real disponível apenas no modo desktop.',
    };
  }
  return getPywebview()!.api!.auth_login(email, password);
}

export async function authRegister(name: string, email: string, password: string): Promise<AuthActionResult> {
  if (!getPywebview()?.api?.auth_register) {
    return {
      ok: false,
      error: 'Cadastro real disponível apenas no modo desktop.',
    };
  }
  return getPywebview()!.api!.auth_register(name, email, password);
}

export async function authLogout(): Promise<boolean> {
  if (!getPywebview()?.api?.auth_logout) {
    return false;
  }
  return getPywebview()!.api!.auth_logout();
}
