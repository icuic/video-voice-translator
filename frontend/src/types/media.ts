export interface MediaFile {
  id: string;
  filename: string;
  size: number;
  duration: number;
  type: 'video' | 'audio';
  url: string;
}

export interface TranslationTask {
  id: string;
  file_id: string;
  status: 'pending' | 'processing' | 'paused_step4' | 'paused_step5' | 'completed' | 'failed';
  current_step: number;
  progress: number;
  message: string;
  step_name?: string;
  current_segment?: number;
  total_segments?: number;
}


