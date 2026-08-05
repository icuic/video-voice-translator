import api from './api';
import { TranslationTask, TranslationHistoryItem } from '../types/media';

export const translationService = {
  startTranslation: async (params: {
    fileId: string;
    sourceLanguage: string;
    targetLanguage: string;
    singleSpeaker: boolean;
    enableSegmentEditing: boolean;
    enableTranslationEditing: boolean;
  }): Promise<TranslationTask> => {
    // 将前端字段名转换为后端期望的格式（snake_case）
    const { data } = await api.post('/api/translation/start', {
      file_id: params.fileId,
      source_language: params.sourceLanguage,
      target_language: params.targetLanguage,
      single_speaker: params.singleSpeaker,
      enable_segment_editing: params.enableSegmentEditing,
      enable_translation_editing: params.enableTranslationEditing,
    });
    return {
      id: data.task_id,
      file_id: params.fileId,
      status: data.status,
      current_step: 0,
      progress: 0,
      message: data.message,
    };
  },

  getStatus: async (taskId: string): Promise<TranslationTask> => {
    const { data } = await api.get(`/api/translation/${taskId}/status`);
    return {
      id: data.task_id,
      file_id: data.file_id || '',
      status: data.status,
      current_step: data.current_step || 0,
      progress: data.progress || 0,
      message: data.message || '',
      step_name: data.step_name || '',
      current_segment: data.current_segment || 0,
      total_segments: data.total_segments || 0,
      source_language: data.source_language || '',
      target_language: data.target_language || '',
    };
  },

  getProgress: async (taskId: string) => {
    const { data } = await api.get(`/api/translation/${taskId}/progress`);
    return data;
  },

  continueTranslation: async (taskId: string): Promise<void> => {
    await api.post(`/api/translation/${taskId}/continue`);
  },

  getResult: async (taskId: string) => {
    const { data } = await api.get(`/api/translation/${taskId}/result`);
    return data;
  },

  getHistory: async (
    limit: number = 20,
    status?: string
  ): Promise<TranslationHistoryItem[]> => {
    const { data } = await api.get('/api/translation/history', {
      params: status ? { limit, status } : { limit },
    });
    return data.tasks || [];
  },

  deleteHistoryTask: async (taskId: string) => {
    const { data } = await api.delete(`/api/translation/history/${taskId}`);
    return data;
  },
};
