export interface Word {
  word: string;
  start: number;
  end: number;
  probability?: number;
}

export interface Segment {
  id: number;
  start: number;
  end: number;
  text: string;
  speaker_id?: string;
  words?: Word[];
  translated_text?: string;
  cloned_audio_path?: string;
  // 时长信息
  original_duration?: number;    // 原始音频时长（秒）
  cloned_duration?: number;      // 克隆音频时长（秒）
  duration_multiplier?: number;  // 速度倍率（克隆/原始）
}

export interface SegmentUpdate {
  id: number;
  start?: number;
  end?: number;
  text?: string;
  translated_text?: string;
}


