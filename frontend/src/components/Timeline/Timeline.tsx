import React, { useRef, useState, useEffect } from 'react';
import { Segment } from '../../types/segment';
import { formatTime } from '../../utils/time';

interface TimelineProps {
  segments: Segment[];
  duration: number;
  currentTime: number;
  onSeek: (time: number) => void;
  onSegmentClick: (segment: Segment) => void;
  onDragStart?: () => void;
  onDragEnd?: () => void;
}

export const Timeline: React.FC<TimelineProps> = ({
  segments,
  duration,
  currentTime,
  onSeek,
  onSegmentClick,
  onDragStart,
  onDragEnd,
}) => {
  const timelineRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const playheadRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [selectedSegmentId, setSelectedSegmentId] = useState<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [scrollWidth, setScrollWidth] = useState(0);
  const [clientWidth, setClientWidth] = useState(0);
  const [isDraggingScrollbar, setIsDraggingScrollbar] = useState(false);
  const scrollbarRef = useRef<HTMLDivElement>(null);

  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    // 如果正在拖动播放头，不处理点击事件
    if (isDragging) return;
    if (!timelineRef.current || !scrollContainerRef.current) return;
    const containerRect = scrollContainerRef.current.getBoundingClientRect();
    const x = e.clientX - containerRect.left + scrollLeft;
    const time = positionToTime(x);
    onSeek(time);
  };

  // 计算时间对应的像素位置（考虑缩放）
  const timeToPosition = (time: number): number => {
    if (duration === 0) return 0;
    // 基础宽度：假设 1 秒 = 100px
    const baseWidth = 100;
    const totalWidth = duration * baseWidth * zoom;
    return (time / duration) * totalWidth;
  };

  // 计算像素位置对应的时间
  const positionToTime = (pixels: number): number => {
    if (duration === 0) return 0;
    const baseWidth = 100;
    const totalWidth = duration * baseWidth * zoom;
    const percentage = pixels / totalWidth;
    return Math.max(0, Math.min(duration, percentage * duration));
  };

  const handleSegmentClick = (segment: Segment, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedSegmentId(segment.id);
    onSegmentClick(segment);
  };

  // 拖动播放头
  const handlePlayheadMouseDown = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setIsDragging(true);
    // 通知父组件开始拖动
    if (onDragStart) {
      onDragStart();
    }
  };

  useEffect(() => {
    if (!isDragging) return;

    let lastUpdateTime = 0;
    const throttleDelay = 16; // 约 60fps

    const handleMouseMove = (e: MouseEvent) => {
      const now = Date.now();
      if (now - lastUpdateTime < throttleDelay) return;
      lastUpdateTime = now;

      if (!timelineRef.current || !scrollContainerRef.current) return;
      const containerRect = scrollContainerRef.current.getBoundingClientRect();
      const x = e.clientX - containerRect.left + scrollLeft;
      const time = positionToTime(x);
      onSeek(time);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      // 通知父组件拖动结束
      if (onDragEnd) {
        onDragEnd();
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, duration, onSeek, scrollLeft, zoom, onDragStart, onDragEnd]);

  // 隐藏 WebKit 滚动条
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    // 添加样式隐藏滚动条
    const style = document.createElement('style');
    style.textContent = `
      .timeline-scroll-container::-webkit-scrollbar {
        display: none;
      }
    `;
    document.head.appendChild(style);
    container.classList.add('timeline-scroll-container');

    return () => {
      document.head.removeChild(style);
      container.classList.remove('timeline-scroll-container');
    };
  }, []);

  // 监听滚动，更新进度条
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      setScrollLeft(container.scrollLeft);
      setScrollWidth(container.scrollWidth);
      setClientWidth(container.clientWidth);
    };

    container.addEventListener('scroll', handleScroll);
    handleScroll(); // 初始计算

    return () => {
      container.removeEventListener('scroll', handleScroll);
    };
  }, [zoom, duration]);

  // 当播放时间变化时，自动滚动到播放头位置（拖动进度条时禁用）
  useEffect(() => {
    if (isDraggingScrollbar) return; // 拖动进度条时禁用自动滚动
    
    const container = scrollContainerRef.current;
    const playhead = playheadRef.current;
    if (!container || !playhead) return;

    const playheadPosition = timeToPosition(currentTime);
    const containerLeft = container.scrollLeft;
    const containerRight = containerLeft + container.clientWidth;
    const playheadLeft = playheadPosition - 50; // 留一些边距
    const playheadRight = playheadPosition + 50;

    if (playheadPosition < containerLeft || playheadPosition > containerRight) {
      container.scrollTo({
        left: playheadLeft,
        behavior: 'smooth',
      });
    }
  }, [currentTime, zoom, duration, isDraggingScrollbar]);

  // 处理滚动进度条的拖动
  const handleScrollbarMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation();
    e.preventDefault();
    if (!scrollbarRef.current || !scrollContainerRef.current || scrollWidth <= clientWidth) return;
    
    setIsDraggingScrollbar(true);
    updateScrollFromMouse(e, true); // 点击时也跳转视频
  };

  const updateScrollFromMouse = (
    e: MouseEvent | React.MouseEvent<HTMLDivElement>, 
    shouldSeek: boolean = false
  ) => {
    if (!scrollbarRef.current || !scrollContainerRef.current || scrollWidth <= clientWidth) return;
    
    const scrollbarRect = scrollbarRef.current.getBoundingClientRect();
    const clickX = e.clientX - scrollbarRect.left;
    const scrollbarWidth = scrollbarRect.width;
    const percentage = Math.max(0, Math.min(1, clickX / scrollbarWidth));
    
    // 计算目标滚动位置
    const targetScrollLeft = percentage * (scrollWidth - clientWidth);
    scrollContainerRef.current.scrollLeft = targetScrollLeft;
    
    // 只有在点击时（不是拖动时）才跳转视频
    if (shouldSeek) {
      const targetTime = positionToTime(targetScrollLeft + clientWidth / 2);
      onSeek(targetTime);
    }
  };

  useEffect(() => {
    if (!isDraggingScrollbar) return;

    const handleMouseMove = (e: MouseEvent) => {
      updateScrollFromMouse(e, false); // 拖动时只滚动，不跳转视频
    };

    const handleMouseUp = (e: MouseEvent) => {
      setIsDraggingScrollbar(false);
      // 松开时跳转到当前位置
      updateScrollFromMouse(e, true);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingScrollbar, scrollWidth, clientWidth, zoom, duration, onSeek]);

  // 计算时间刻度（根据缩放级别调整）
  const baseTickInterval = duration > 60 ? 10 : duration > 10 ? 5 : 1;
  const tickInterval = baseTickInterval / zoom; // 缩放越大，刻度越密
  const ticks = [];
  for (let i = 0; i <= duration; i += tickInterval) {
    ticks.push(i);
  }

  // 计算总宽度
  const baseWidth = 100; // 1秒 = 100px
  const totalWidth = duration * baseWidth * zoom;

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-semibold text-white">时间轴</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setZoom(Math.max(0.1, zoom - 0.2))}
            className="px-2 py-1 bg-slate-700 text-white rounded text-sm hover:bg-slate-600"
            disabled={zoom <= 0.1}
          >
            −
          </button>
          <span className="text-slate-400 text-sm min-w-[50px] text-center">
            {Math.round(zoom * 100)}%
          </span>
          <button
            onClick={() => setZoom(Math.min(10, zoom + 0.2))}
            className="px-2 py-1 bg-slate-700 text-white rounded text-sm hover:bg-slate-600"
            disabled={zoom >= 10}
          >
            +
          </button>
        </div>
      </div>

      <div className="relative">
        {/* 时间刻度容器（可滚动，隐藏原生滚动条） */}
        <div
          ref={scrollContainerRef}
          className="overflow-x-auto overflow-y-hidden"
          style={{ 
            scrollbarWidth: 'none', // 隐藏 Firefox 滚动条
            msOverflowStyle: 'none', // 隐藏 IE/Edge 滚动条
          }}
        >
          <div
            className="relative h-8 bg-slate-900 rounded-t border-b border-slate-700"
            style={{ width: `${totalWidth}px`, minWidth: '100%' }}
          >
            {ticks.map((tick) => {
              const position = timeToPosition(tick);
              return (
                <div
                  key={tick}
                  className="absolute top-0 bottom-0 border-l border-slate-600"
                  style={{ left: `${position}px` }}
                >
                  <span className="absolute top-1 left-1 text-xs text-slate-500 whitespace-nowrap">
                    {formatTime(tick)}
                  </span>
                </div>
              );
            })}
            
            {/* 播放头指示器（延伸到时间刻度区域） */}
            <div
              ref={playheadRef}
              className="absolute top-0 bottom-0 w-0.5 bg-blue-500 z-30 cursor-ew-resize"
              style={{ left: `${timeToPosition(currentTime)}px` }}
              onMouseDown={handlePlayheadMouseDown}
            >
              {/* 顶部拖动句柄（蓝色矩形） */}
              <div className="absolute top-0 left-1/2 transform -translate-x-1/2 w-3 h-3 bg-blue-500 border border-blue-400 rounded-sm cursor-ew-resize" />
            </div>
          </div>

          {/* 时间轴主体（可滚动） */}
          <div
            ref={timelineRef}
            className="relative h-32 bg-slate-900 rounded-b cursor-pointer"
            onClick={handleTimelineClick}
            style={{ width: `${totalWidth}px`, minWidth: '100%' }}
          >
            {/* 分段块 */}
            {segments.map((segment) => {
              const left = timeToPosition(segment.start);
              const width = timeToPosition(segment.end - segment.start);
              const isSelected = selectedSegmentId === segment.id;

              return (
                <div
                  key={segment.id}
                  className={`
                    absolute h-full border rounded cursor-pointer transition-all
                    ${isSelected 
                      ? 'bg-indigo-500/70 border-indigo-400 z-10' 
                      : 'bg-indigo-500/50 border-indigo-400/50 hover:bg-indigo-500/60 z-0'
                    }
                  `}
                  style={{
                    left: `${left}px`,
                    width: `${width}px`,
                    minWidth: '4px', // 确保即使很小的分段也可见
                  }}
                  onClick={(e) => handleSegmentClick(segment, e)}
                  title={`${formatTime(segment.start)} - ${formatTime(segment.end)}\n${segment.text}`}
                >
                  {/* 分段文本标签（如果分段足够宽） */}
                  {width > 30 && (
                    <div className="absolute inset-0 flex items-center px-1 overflow-hidden">
                      <span className="text-xs text-white truncate">
                        {segment.text.substring(0, Math.floor(width / 10))}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}

            {/* 当前播放位置指示器（延伸到时间轴主体） */}
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-blue-500 z-20 pointer-events-none"
              style={{ left: `${timeToPosition(currentTime)}px` }}
            />

            {/* 时间轴背景网格 */}
            <div className="absolute inset-0 opacity-20 pointer-events-none">
              {ticks.map((tick) => {
                const position = timeToPosition(tick);
                return (
                  <div
                    key={tick}
                    className="absolute top-0 bottom-0 border-l border-slate-700"
                    style={{ left: `${position}px` }}
                  />
                );
              })}
            </div>
          </div>
        </div>

        {/* 水平滚动进度条（隐藏浏览器原生滚动条，使用自定义进度条） */}
        <div 
          ref={scrollbarRef}
          className="mt-2 h-2 bg-slate-700 rounded-full overflow-hidden relative cursor-pointer"
          onMouseDown={handleScrollbarMouseDown}
        >
          {scrollWidth > clientWidth ? (
            <>
              {/* 可视区域指示器 */}
              <div
                className="h-full bg-indigo-500/50 rounded-full absolute transition-all"
                style={{
                  width: `${(clientWidth / scrollWidth) * 100}%`,
                  left: `${(scrollLeft / scrollWidth) * 100}%`,
                }}
              />
              {/* 当前播放位置指示器（在进度条上） */}
              <div
                className="h-full w-1 bg-blue-500 rounded-full absolute z-10 transition-all pointer-events-none"
                style={{
                  left: `${(timeToPosition(currentTime) / scrollWidth) * 100}%`,
                }}
              />
            </>
          ) : (
            // 如果不需要滚动，只显示播放位置
            <div
              className="h-full w-1 bg-blue-500 rounded-full absolute z-10 transition-all pointer-events-none"
              style={{
                left: `${(timeToPosition(currentTime) / totalWidth) * 100}%`,
              }}
            />
          )}
        </div>

        {/* 时间显示 */}
        <div className="mt-2 text-center text-sm text-slate-400">
          当前: {formatTime(currentTime)} / 总时长: {formatTime(duration)}
        </div>
      </div>
    </div>
  );
};

