import React, { useRef, useEffect } from 'react';

interface VideoPlayerProps {
  src: string;
  videoRef?: React.RefObject<HTMLVideoElement>;
  currentTime?: number;
  isSeeking?: boolean;
  onTimeUpdate?: (time: number) => void;
  onEnded?: () => void;
  onLoadedMetadata?: () => void;
}

export const VideoPlayer: React.FC<VideoPlayerProps> = ({
  src,
  videoRef: externalVideoRef,
  currentTime,
  isSeeking = false,
  onTimeUpdate,
  onEnded,
  onLoadedMetadata,
}) => {
  // 如果外部提供了 videoRef，使用外部的；否则创建自己的
  const internalVideoRef = useRef<HTMLVideoElement>(null);
  const videoRef = externalVideoRef || internalVideoRef;

  // 同步外部 currentTime 到 video（拖动时完全阻止）
  useEffect(() => {
    if (isSeeking) return; // 拖动时完全阻止同步
    if (videoRef.current && currentTime !== undefined) {
      const timeDiff = Math.abs(videoRef.current.currentTime - currentTime);
      // 只有当时间差超过 0.2 秒时才同步，避免频繁更新
      if (timeDiff > 0.2) {
        videoRef.current.currentTime = currentTime;
      }
    }
  }, [currentTime, isSeeking, videoRef]);

  // 处理视频时间更新
  const handleTimeUpdate = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    if (isSeeking) return; // 拖动时完全忽略
    const target = e.target as HTMLVideoElement;
    if (onTimeUpdate) {
      onTimeUpdate(target.currentTime);
    }
  };

  // 处理视频加载完成
  const handleLoadedMetadata = () => {
    if (onLoadedMetadata) {
      onLoadedMetadata();
    }
  };

  // 处理视频播放完成
  const handleEnded = () => {
    if (onEnded) {
      onEnded();
    }
  };

  return (
    <div className="relative w-full bg-slate-900 rounded-lg overflow-hidden flex justify-center">
      <video
        ref={videoRef}
        src={src}
        className="max-h-[60vh] w-auto"
        controls
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
      />
    </div>
  );
};


