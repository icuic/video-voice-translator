/**
 * 时间格式化工具函数
 */

export const formatTime = (seconds: number): string => {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = (seconds % 60).toFixed(3);
  
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.padStart(6, '0')}`;
  }
  return `${minutes}:${secs.padStart(6, '0')}`;
};

export const parseTime = (timeString: string): number => {
  // 解析 "00:00:01.515" 或 "1.515" 格式
  const parts = timeString.split(':');
  if (parts.length === 3) {
    const hours = parseInt(parts[0], 10);
    const minutes = parseInt(parts[1], 10);
    const seconds = parseFloat(parts[2]);
    return hours * 3600 + minutes * 60 + seconds;
  } else if (parts.length === 1) {
    return parseFloat(parts[0]);
  }
  return 0;
};


