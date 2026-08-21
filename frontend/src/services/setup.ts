import api from './api';

export interface SetupStatus {
  configured: boolean;
  env_file_exists: boolean;
  current: {
    llm_base_url: string;
    llm_model: string;
    llm_api_key_masked: string;
    llm_temperature: string;
    llm_timeout: string;
  };
}

export interface SetupApplyRequest {
  llm_base_url: string;
  llm_api_key: string;
  llm_model: string;
  llm_temperature?: string;
  llm_timeout?: string;
  restart?: boolean;
}

export interface SetupApplyResult {
  saved: boolean;
  env_file: string;
  restart: boolean;
  restart_result: {
    restarted: boolean;
    message: string;
    code: number | null;
  };
}

export const setupService = {
  async getStatus(): Promise<SetupStatus> {
    const res = await api.get('/api/setup/status');
    return res.data as SetupStatus;
  },

  async apply(req: SetupApplyRequest): Promise<SetupApplyResult> {
    const res = await api.post('/api/setup/apply', req, { timeout: 650000 });
    return res.data as SetupApplyResult;
  },
};
