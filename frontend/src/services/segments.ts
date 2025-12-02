import api from './api';
import { Segment } from '../types/segment';

export const segmentService = {
  getSegments: async (taskId: string): Promise<Segment[]> => {
    const { data } = await api.get(`/api/segments/${taskId}`);
    return data.segments || [];
  },

  updateSegments: async (taskId: string, segments: Segment[]): Promise<void> => {
    await api.put(`/api/segments/${taskId}`, { segments });
  },

  retranslateSegment: async (
    taskId: string,
    segmentId: number,
    newText?: string
  ): Promise<Segment> => {
    const { data } = await api.post(
      `/api/segments/${taskId}/segments/${segmentId}/retranslate`,
      { new_text: newText }
    );
    return data.segment;
  },

  resynthesizeSegment: async (
    taskId: string,
    segmentId: number,
    useOriginalTimbre: boolean = true
  ): Promise<void> => {
    await api.post(
      `/api/segments/${taskId}/segments/${segmentId}/resynthesize`,
      { use_original_timbre: useOriginalTimbre }
    );
  },

  mergeSegments: async (taskId: string, segmentIds: number[]): Promise<Segment[]> => {
    const { data } = await api.post(`/api/segments/${taskId}/merge`, { segment_ids: segmentIds });
    return data.segments || [];
  },

  splitSegment: async (
    taskId: string,
    segmentId: number,
    splitTime?: number,
    splitText?: string,
    splitTextPosition?: number
  ): Promise<Segment[]> => {
    const { data } = await api.post(`/api/segments/${taskId}/split?segment_id=${segmentId}`, {
      split_time: splitTime,
      split_text: splitText,
      split_text_position: splitTextPosition,
    });
    return data.segments || [];
  },

  deleteSegments: async (taskId: string, segmentIds: number[]): Promise<void> => {
    await api.delete(`/api/segments/${taskId}`, { data: { segment_ids: segmentIds } });
  },

  regenerateFinal: async (taskId: string): Promise<void> => {
    await api.post(`/api/segments/${taskId}/regenerate-final`);
  },

  getRefAudioUrl: (taskId: string, segmentId: number): string => {
    return `/api/segments/${taskId}/segments/${segmentId}/ref-audio`;
  },

  getClonedAudioUrl: (taskId: string, segmentId: number, timestamp?: number): string => {
    const baseUrl = `/api/segments/${taskId}/segments/${segmentId}/cloned-audio`;
    // 如果提供了时间戳，添加到URL中避免缓存
    return timestamp ? `${baseUrl}?t=${timestamp}` : baseUrl;
  },
};


