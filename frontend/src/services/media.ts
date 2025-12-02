import api from './api';
import { MediaFile } from '../types/media';

export const mediaService = {
  uploadMedia: async (
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<MediaFile> => {
    const formData = new FormData();
    formData.append('file', file);
    
    const { data } = await api.post('/api/media/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 300000,  // 5分钟超时，用于大文件上传
      onUploadProgress: (progressEvent) => {
        if (onProgress) {
          // 如果 total 存在，计算精确进度
          if (progressEvent.total) {
            const percentCompleted = Math.round(
              (progressEvent.loaded * 100) / progressEvent.total
            );
            onProgress(percentCompleted);
          } else if (progressEvent.loaded > 0) {
            // 如果 total 不存在，使用已加载字节数估算进度
            // 假设至少上传了1%，避免卡在0%
            const estimatedProgress = Math.max(1, Math.min(99, Math.round(progressEvent.loaded / 1024 / 1024))); // 每MB约1%
            onProgress(estimatedProgress);
          }
        }
      },
    });
    
    return {
      id: data.file_id,
      filename: data.filename,
      size: data.size,
      duration: 0, // TODO: 从元数据获取
      type: data.type,
      url: `/api/media/${data.file_id}`,
    };
  },

  getMedia: (fileId: string): string => {
    // 使用相对路径，通过 Vite proxy 或生产环境的反向代理
    return `/api/media/${fileId}`;
  },

  getMediaMetadata: async (fileId: string) => {
    const { data } = await api.get(`/api/media/${fileId}/metadata`);
    return data;
  },
};


