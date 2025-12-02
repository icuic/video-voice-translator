import { useRef, useState, useEffect } from 'react';

export const useVideoPlayer = (src: string) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);

  const seekTo = (time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  const play = () => {
    videoRef.current?.play();
    setIsPlaying(true);
  };

  const pause = () => {
    videoRef.current?.pause();
    setIsPlaying(false);
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let endedProtectionTimeout: ReturnType<typeof setTimeout> | null = null;
    let isEndedProtectionActive = false;

    const handleTimeUpdate = () => {
      // 如果处于播放完成保护期，忽略 timeupdate 事件
      if (isEndedProtectionActive) return;
      setCurrentTime(video.currentTime);
    };

    const handleLoadedMetadata = () => {
      setDuration(video.duration);
    };

    const handlePlay = () => {
      // 播放开始时，清除保护期
      if (endedProtectionTimeout) {
        clearTimeout(endedProtectionTimeout);
        endedProtectionTimeout = null;
      }
      isEndedProtectionActive = false;
      setIsPlaying(true);
    };

    const handlePause = () => setIsPlaying(false);
    
    const handleEnded = () => {
      // 视频播放完成后，重置到开头
      video.currentTime = 0;
      setCurrentTime(0);
      setIsPlaying(false);
      
      // 启动保护期，防止 timeupdate 事件继续触发导致颤动
      isEndedProtectionActive = true;
      if (endedProtectionTimeout) {
        clearTimeout(endedProtectionTimeout);
      }
      endedProtectionTimeout = setTimeout(() => {
        isEndedProtectionActive = false;
        endedProtectionTimeout = null;
      }, 500); // 500ms 保护期
    };

    video.addEventListener('timeupdate', handleTimeUpdate);
    video.addEventListener('loadedmetadata', handleLoadedMetadata);
    video.addEventListener('play', handlePlay);
    video.addEventListener('pause', handlePause);
    video.addEventListener('ended', handleEnded);

    return () => {
      video.removeEventListener('timeupdate', handleTimeUpdate);
      video.removeEventListener('loadedmetadata', handleLoadedMetadata);
      video.removeEventListener('play', handlePlay);
      video.removeEventListener('pause', handlePause);
      video.removeEventListener('ended', handleEnded);
      if (endedProtectionTimeout) {
        clearTimeout(endedProtectionTimeout);
      }
    };
  }, [src]);

  return {
    videoRef,
    currentTime,
    duration,
    isPlaying,
    seekTo,
    play,
    pause,
  };
};


