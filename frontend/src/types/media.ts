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
  source_language?: string;
  target_language?: string;
}

export interface TranslationHistoryItem {
  task_id: string;
  file_id: string;
  file_path?: string;
  file_name?: string;
  original_filename?: string;
  stored_file_name?: string;
  status: string;
  message?: string;
  step_name?: string;
  source_language?: string;
  target_language?: string;
  media_type?: 'video' | 'audio' | 'unknown' | string;
  task_dir?: string;
  task_dir_name?: string;
  final_video_path?: string | null;
  thumbnail_url?: string | null;
}
