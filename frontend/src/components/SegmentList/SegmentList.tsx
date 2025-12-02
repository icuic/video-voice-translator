import React, { useState, useEffect, useRef } from 'react';
import { Segment } from '../../types/segment';
import { SegmentItem } from './SegmentItem';

interface SegmentListProps {
  segments: Segment[];
  currentTime?: number;
  taskId?: string;
  onSegmentClick: (segment: Segment) => void;
  onSegmentUpdate: (segment: Segment) => void;
  onSegmentDelete: (segmentId: number) => void;
  onRetranslate: (segmentId: number, newText?: string) => Promise<void>;
  onResynthesize: (segmentId: number) => Promise<void>;
  onSplit?: (segmentId: number, splitTextPosition: number) => Promise<void>;
  isRetranslating?: { [key: number]: boolean };
  isResynthesizing?: { [key: number]: boolean };
}

export const SegmentList: React.FC<SegmentListProps> = ({
  segments,
  currentTime = 0,
  taskId,
  onSegmentClick,
  onSegmentUpdate,
  onSegmentDelete,
  onRetranslate,
  onResynthesize,
  onSplit,
  isRetranslating = {},
  isResynthesizing = {},
}) => {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  // 根据当前播放时间更新当前激活的分段，并自动滚动到视野内
  useEffect(() => {
    if (!segments.length) return;

    const active = segments.find(
      (segment) => currentTime >= segment.start && currentTime <= segment.end
    );

    if (active && active.id !== activeId) {
      setActiveId(active.id);
      // 自动滚动：将当前分段滚动到容器顶部（只滚动容器内部，不影响整个页面）
      const el = document.getElementById(`segment-${active.id}`);
      const container = listRef.current;
      if (el && container) {
        // 使用 requestAnimationFrame 确保 DOM 已更新
        requestAnimationFrame(() => {
          // 计算目标元素相对于容器的位置
          const containerRect = container.getBoundingClientRect();
          const elementRect = el.getBoundingClientRect();
          // 计算需要滚动的距离（元素顶部到容器顶部的距离）
          const scrollTop = container.scrollTop + (elementRect.top - containerRect.top);
          // 平滑滚动到目标位置（只滚动容器，不影响页面）
          // 使用 scrollTo 而不是 scrollIntoView，避免触发页面滚动
          container.scrollTo({
            top: scrollTop,
            behavior: 'smooth'
          });
        });
      }
    }
  }, [currentTime, segments, activeId]);

  const isActive = (segment: Segment): boolean => {
    return segment.id === activeId;
  };

  return (
    <div className="bg-slate-800 rounded-lg p-4">
      <h3 className="text-xl font-semibold text-white mb-4">字幕列表</h3>
      <div
        ref={listRef}
        className="space-y-2 max-h-[600px] overflow-y-auto"
      >
        {segments.map((segment) => (
          <SegmentItem
            key={segment.id}
            segment={segment}
            isActive={isActive(segment)}
            isEditing={editingId === segment.id}
            taskId={taskId}
            onSelect={() => onSegmentClick(segment)}
            onEdit={() => setEditingId(segment.id)}
            onUpdate={(updated) => {
              onSegmentUpdate(updated);
              setEditingId(null);
            }}
            onDelete={() => {
              onSegmentDelete(segment.id);
              setEditingId(null);
            }}
            onCancel={() => setEditingId(null)}
            onRetranslate={onRetranslate}
            onResynthesize={onResynthesize}
            onSplit={onSplit}
            isRetranslating={isRetranslating[segment.id]}
            isResynthesizing={isResynthesizing[segment.id]}
          />
        ))}
      </div>
    </div>
  );
};


