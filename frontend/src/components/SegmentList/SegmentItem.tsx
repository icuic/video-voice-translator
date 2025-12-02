import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Segment } from '../../types/segment';
import { formatTime } from '../../utils/time';
import { segmentService } from '../../services/segments';

interface SegmentItemProps {
  segment: Segment;
  isActive: boolean;
  isEditing: boolean;
  taskId?: string;
  onSelect: () => void;
  onEdit: () => void;
  onUpdate: (segment: Segment) => void;
  onDelete: () => void;
  onCancel: () => void;
  onRetranslate: (segmentId: number, newText?: string) => Promise<void>;
  onResynthesize: (segmentId: number) => Promise<void>;
  onSplit?: (segmentId: number, splitTextPosition: number) => Promise<void>;
  isRetranslating?: boolean;
  isResynthesizing?: boolean;
}

export const SegmentItem: React.FC<SegmentItemProps> = ({
  segment,
  isActive,
  isEditing,
  taskId,
  onSelect,
  onEdit,
  onUpdate,
  onDelete,
  onCancel,
  onRetranslate,
  onResynthesize,
  onSplit,
  isRetranslating = false,
  isResynthesizing = false,
}) => {
  const [startTime, setStartTime] = useState(segment.start.toString());
  const [endTime, setEndTime] = useState(segment.end.toString());
  const [text, setText] = useState(segment.text);
  const [translatedText, setTranslatedText] = useState(segment.translated_text || '');
  const [playingRefAudio, setPlayingRefAudio] = useState(false);
  const [playingClonedAudio, setPlayingClonedAudio] = useState(false);
  const [isManualTranslating, setIsManualTranslating] = useState(false);
  const [manualTranslationText, setManualTranslationText] = useState('');
  const [isSplitting, setIsSplitting] = useState(false);
  const splitTextareaRef = useRef<HTMLTextAreaElement>(null);
  const manualTranslationTextareaRef = useRef<HTMLTextAreaElement>(null);
  const refAudioRef = useRef<HTMLAudioElement>(null);
  const clonedAudioRef = useRef<HTMLAudioElement>(null);
  // 添加音频版本状态，用于避免缓存
  const [audioVersion, setAudioVersion] = useState(0);

  useEffect(() => {
    setStartTime(segment.start.toString());
    setEndTime(segment.end.toString());
    setText(segment.text);
    setTranslatedText(segment.translated_text || '');
    // 当分段更新时，如果不在手动翻译模式，重置手动翻译文本
    if (!isManualTranslating) {
      setManualTranslationText(segment.translated_text || '');
    }
  }, [segment, isManualTranslating]);

  // 使用 useMemo 计算翻译文本的哈希值，用于检测变化
  const textHash = useMemo(() => {
    const text = segment.translated_text || '';
    return `${text.length}-${text.substring(0, 20)}`;
  }, [segment.translated_text]);

  // 使用 ref 存储上一次的文本哈希值
  const prevTextHashRef = useRef<string>('');
  // 使用 ref 存储上一次的 isResynthesizing 状态
  const prevIsResynthesizingRef = useRef<boolean>(false);

  // 监听 segment 的变化，如果 translated_text 或 cloned_audio_path 更新了，增加版本号
  useEffect(() => {
    // 只有当文本哈希值真正变化时才更新版本号
    if (textHash && textHash !== prevTextHashRef.current) {
      prevTextHashRef.current = textHash;
      setAudioVersion(prev => prev + 1);
    }
  }, [textHash, segment.cloned_audio_path]);

  // 监听 isResynthesizing 的变化，当重新合成完成时（从 true 变为 false），强制更新音频版本号
  useEffect(() => {
    // 如果 isResynthesizing 从 true 变为 false，说明重新合成完成，强制更新版本号
    if (prevIsResynthesizingRef.current && !isResynthesizing) {
      setAudioVersion(prev => prev + 1);
    }
    prevIsResynthesizingRef.current = isResynthesizing;
  }, [isResynthesizing]);

  const handleSave = () => {
    onUpdate({
      ...segment,
      start: parseFloat(startTime),
      end: parseFloat(endTime),
      text: text.trim(),
      translated_text: translatedText.trim(),
    });
  };

  const handleRetranslate = async (auto: boolean) => {
    if (auto) {
      await onRetranslate(segment.id);
    } else {
      // 手动翻译模式：进入编辑状态
      setIsManualTranslating(true);
      setManualTranslationText(translatedText);
    }
  };

  // 保存手动翻译
  const handleManualTranslationSave = async () => {
    if (manualTranslationText.trim()) {
      try {
        await onRetranslate(segment.id, manualTranslationText.trim());
        setIsManualTranslating(false);
      } catch (error) {
        // 错误已在 App.tsx 的 handleRetranslate 中处理，这里只关闭编辑模式
        console.error('保存手动翻译失败:', error);
        // 可以选择保持编辑模式让用户重试，或者关闭
        // setIsManualTranslating(false);
      }
    } else {
      // 如果文本为空，直接关闭
      setIsManualTranslating(false);
    }
  };

  // 取消手动翻译
  const handleManualTranslationCancel = () => {
    setIsManualTranslating(false);
    setManualTranslationText(translatedText);
  };

  // 当进入手动翻译模式时，聚焦到 textarea（移动端需要手动触发键盘）
  useEffect(() => {
    if (isManualTranslating && manualTranslationTextareaRef.current) {
      // 使用 setTimeout 确保 DOM 已更新，特别是在移动设备上
      setTimeout(() => {
        const textarea = manualTranslationTextareaRef.current;
        if (textarea) {
          // 先滚动到视口内（移动设备上很重要）
          textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
          // 然后聚焦
          textarea.focus();
          // 在移动设备上，有时需要稍微延迟才能触发键盘
          setTimeout(() => {
            if (textarea) {
              textarea.focus();
            }
          }, 50);
        }
      }, 100);
    }
  }, [isManualTranslating]);

  // 处理拆分
  const handleSplit = () => {
    if (!onSplit) return;
    setIsSplitting(true);
    // 聚焦到 textarea 并设置光标到中间位置
    setTimeout(() => {
      if (splitTextareaRef.current) {
        splitTextareaRef.current.focus();
        // 将光标设置到文本中间位置（作为默认位置）
        const textLength = segment.text.length;
        const middlePos = Math.floor(textLength / 2);
        splitTextareaRef.current.setSelectionRange(middlePos, middlePos);
      }
    }, 0);
  };

  // 确认拆分
  const handleConfirmSplit = async () => {
    if (!onSplit || !splitTextareaRef.current) return;
    
    const cursorPosition = splitTextareaRef.current.selectionStart;
    const textLength = segment.text.length;
    
    // 验证光标位置（不能在开头或结尾）
    if (cursorPosition <= 0 || cursorPosition >= textLength) {
      alert('光标位置无效，请在文本中间位置放置光标');
      return;
    }
    
    try {
      await onSplit(segment.id, cursorPosition);
      setIsSplitting(false);
    } catch (error) {
      console.error('拆分失败:', error);
      // 错误已在 App.tsx 中处理，这里只关闭拆分模式
      setIsSplitting(false);
    }
  };

  // 取消拆分
  const handleCancelSplit = () => {
    setIsSplitting(false);
  };

  // 处理原始音频播放/暂停
  const handleRefAudioToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!taskId) return;

    if (playingRefAudio) {
      // 暂停
      refAudioRef.current?.pause();
      setPlayingRefAudio(false);
    } else {
      // 播放 - 先暂停其他音频
      clonedAudioRef.current?.pause();
      setPlayingClonedAudio(false);
      
      // 播放原始音频
      refAudioRef.current?.play().catch((err) => {
        console.error('播放原始音频失败:', err);
        setPlayingRefAudio(false);
      });
      setPlayingRefAudio(true);
    }
  };

  // 处理克隆音频播放/暂停
  const handleClonedAudioToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!taskId) return;

    if (playingClonedAudio) {
      // 暂停
      clonedAudioRef.current?.pause();
      setPlayingClonedAudio(false);
    } else {
      // 播放 - 先暂停其他音频
      refAudioRef.current?.pause();
      setPlayingRefAudio(false);
      
      // 播放克隆音频
      clonedAudioRef.current?.play().catch((err) => {
        console.error('播放克隆音频失败:', err);
        setPlayingClonedAudio(false);
      });
      setPlayingClonedAudio(true);
    }
  };

  // 获取时长差异指示器的颜色
  const getDurationIndicatorColor = (multiplier: number): string => {
    // 红色：克隆音频时长比原始音频时长长，且倍速 > 10% (multiplier > 1.1)
    if (multiplier > 1.1) {
      // 根据倍速大小调整红色深浅
      if (multiplier <= 1.2) {
        // 轻微过长 (10%-20%): 浅红色
        return 'bg-red-400/15 text-red-200 border border-red-400/25';
      } else if (multiplier <= 1.5) {
        // 中等过长 (20%-50%): 中红色
        return 'bg-red-500/20 text-red-300 border border-red-500/30';
      } else {
        // 严重过长 (>50%): 深红色
        return 'bg-red-700/25 text-red-400 border border-red-700/35';
      }
    } else {
      // 绿色：其他情况（包括克隆音频短于原始音频的情况）
      return 'bg-green-600/20 text-green-300 border border-green-600/30';
    }
  };

  return (
    <div
      id={`segment-${segment.id}`}
      className={`
        p-3 rounded-lg border-2 transition-all cursor-pointer
        ${isActive
          ? 'border-indigo-500 bg-indigo-500/20'
          : 'border-slate-700 bg-slate-700/50 hover:border-slate-600'
        }
      `}
      onClick={!isEditing && !isManualTranslating && !isSplitting ? onSelect : undefined}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-slate-400">
          {formatTime(segment.start)} - {formatTime(segment.end)}
        </span>
        {!isEditing && !isManualTranslating && !isSplitting && (
          <div className="flex gap-2">
            {onSplit && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleSplit();
                }}
                className="text-yellow-400 hover:text-yellow-300 text-sm"
              >
                拆分
              </button>
            )}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit();
              }}
              className="text-indigo-400 hover:text-indigo-300 text-sm"
            >
              编辑
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="text-red-400 hover:text-red-300 text-sm"
            >
              删除
            </button>
          </div>
        )}
      </div>

      {isEditing ? (
        <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
          <div className="flex gap-2">
            <input
              type="number"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="flex-1 px-2 py-1 bg-slate-900 text-white rounded text-sm"
              placeholder="开始时间"
            />
            <input
              type="number"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              className="flex-1 px-2 py-1 bg-slate-900 text-white rounded text-sm"
              placeholder="结束时间"
            />
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="w-full px-2 py-1 bg-slate-900 text-white rounded text-sm"
            rows={2}
            placeholder="原文"
          />
          <textarea
            value={translatedText}
            onChange={(e) => setTranslatedText(e.target.value)}
            className="w-full px-2 py-1 bg-slate-900 text-white rounded text-sm"
            rows={2}
            placeholder="译文"
          />
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              className="px-3 py-1 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700"
            >
              保存
            </button>
            <button
              onClick={onCancel}
              className="px-3 py-1 bg-slate-600 text-white rounded text-sm hover:bg-slate-700"
            >
              取消
            </button>
          </div>
        </div>
      ) : isSplitting ? (
        <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
          <textarea
            ref={splitTextareaRef}
            defaultValue={segment.text}
            className="w-full px-2 py-1 bg-slate-900 text-white rounded text-sm border border-yellow-500 focus:border-yellow-400 focus:outline-none cursor-text"
            rows={3}
            placeholder="在此处定位光标以拆分分段"
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                handleCancelSplit();
                return;
              }
              // 允许导航键和功能键
              const allowedKeys = [
                'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown',
                'Home', 'End', 'PageUp', 'PageDown',
                'Tab', 'Escape'
              ];
              // 允许 Ctrl/Cmd + 组合键（用于选择等）
              if (e.ctrlKey || e.metaKey) {
                // 允许 Ctrl+A (全选), Ctrl+C (复制) 等
                if (['a', 'c', 'x'].includes(e.key.toLowerCase())) {
                  return; // 允许这些操作
                }
              }
              // 阻止所有其他按键（包括输入字符、删除、退格等）
              if (!allowedKeys.includes(e.key)) {
                e.preventDefault();
              }
            }}
            onInput={(e) => {
              // 阻止任何文本输入，恢复原文本
              e.preventDefault();
              if (splitTextareaRef.current) {
                const currentValue = splitTextareaRef.current.value;
                if (currentValue !== segment.text) {
                  // 保存光标位置
                  const cursorPos = splitTextareaRef.current.selectionStart;
                  // 恢复原文本
                  splitTextareaRef.current.value = segment.text;
                  // 恢复光标位置（如果可能）
                  if (cursorPos <= segment.text.length) {
                    splitTextareaRef.current.setSelectionRange(cursorPos, cursorPos);
                  }
                }
              }
            }}
            onPaste={(e) => {
              // 阻止粘贴
              e.preventDefault();
            }}
            onCut={(e) => {
              // 阻止剪切（但允许复制）
              e.preventDefault();
            }}
          />
          <div className="flex gap-2">
            <button
              onClick={handleConfirmSplit}
              className="px-3 py-1 bg-yellow-600 text-white rounded text-sm hover:bg-yellow-700"
            >
              确认拆分
            </button>
            <button
              onClick={handleCancelSplit}
              className="px-3 py-1 bg-slate-600 text-white rounded text-sm hover:bg-slate-700"
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <div>
          <p className="text-white mb-2 inline-flex items-center gap-2">
            {segment.text}
            {taskId && (
              <button
                onClick={handleRefAudioToggle}
                className="text-green-400 hover:text-green-300 text-sm transition-colors"
                title="播放原始音频"
              >
                {playingRefAudio ? '⏸️' : '▶️'}
              </button>
            )}
          </p>
          {isManualTranslating ? (
            <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
              <textarea
                ref={manualTranslationTextareaRef}
                value={manualTranslationText}
                onChange={(e) => setManualTranslationText(e.target.value)}
                className="w-full px-2 py-1 bg-slate-900 text-white rounded text-sm border border-indigo-500 focus:border-indigo-400 focus:outline-none"
                rows={3}
                placeholder="请输入翻译文本"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Escape') {
                    handleManualTranslationCancel();
                  } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    handleManualTranslationSave();
                  }
                }}
                onFocus={(e) => {
                  // 确保在移动设备上也能触发键盘
                  e.target.focus();
                }}
              />
              <div className="flex gap-2">
                <button
                  onClick={handleManualTranslationSave}
                  className="px-3 py-1 bg-indigo-600 text-white rounded text-xs hover:bg-indigo-700 transition-colors"
                >
                  保存
                </button>
                <button
                  onClick={handleManualTranslationCancel}
                  className="px-3 py-1 bg-slate-600 text-white rounded text-xs hover:bg-slate-700 transition-colors"
                >
                  取消
                </button>
              </div>
            </div>
          ) : (
            <p className="text-slate-300 text-sm inline-flex items-center gap-2">
              {segment.translated_text || '未翻译'}
              {taskId && (
                <button
                  onClick={handleClonedAudioToggle}
                  disabled={isResynthesizing}
                  className={`text-green-400 hover:text-green-300 text-sm transition-colors ${
                    isResynthesizing ? 'opacity-50 cursor-not-allowed' : ''
                  }`}
                  title={isResynthesizing ? '合成中，请稍候...' : '播放克隆音频'}
                >
                  {playingClonedAudio ? '⏸️' : '▶️'}
                </button>
              )}
            </p>
          )}
          {!isManualTranslating && (
            <div className="flex gap-2 mt-2 items-center">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleRetranslate(true);
                }}
                disabled={isRetranslating}
                className="px-2 py-1 bg-indigo-600 text-white rounded text-xs hover:bg-indigo-700 disabled:opacity-50"
              >
                {isRetranslating ? '翻译中...' : '重新翻译'}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleRetranslate(false);
                }}
                disabled={isRetranslating}
                className="px-2 py-1 bg-indigo-600 text-white rounded text-xs hover:bg-indigo-700 disabled:opacity-50"
              >
                手动翻译
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onResynthesize(segment.id);
                }}
                disabled={isResynthesizing}
                className="px-2 py-1 bg-purple-600 text-white rounded text-xs hover:bg-purple-700 disabled:opacity-50"
              >
                {isResynthesizing ? '合成中...' : '重新合成'}
              </button>

              {/* 时长差异指示器 */}
              {segment.duration_multiplier !== undefined && segment.duration_multiplier !== null && (
                <div className="ml-auto">
                  <span
                    className={`px-2 py-1 rounded text-xs font-medium ${getDurationIndicatorColor(segment.duration_multiplier)}`}
                    title={`原始时长: ${(segment.end - segment.start).toFixed(2)}s, 克隆时长: ${segment.cloned_duration?.toFixed(2)}s`}
                  >
                    {segment.duration_multiplier.toFixed(2)}x
                  </span>
                </div>
              )}
            </div>
          )}
          {/* 隐藏的音频元素 */}
          {taskId && (
            <>
              <audio
                ref={refAudioRef}
                src={segmentService.getRefAudioUrl(taskId, segment.id)}
                onEnded={() => setPlayingRefAudio(false)}
                onError={() => {
                  console.error('原始音频加载失败');
                  setPlayingRefAudio(false);
                }}
              />
              <audio
                ref={clonedAudioRef}
                src={segmentService.getClonedAudioUrl(taskId, segment.id, audioVersion)}
                onEnded={() => setPlayingClonedAudio(false)}
                onError={() => {
                  console.error('克隆音频加载失败');
                  setPlayingClonedAudio(false);
                }}
              />
            </>
          )}
        </div>
      )}
    </div>
  );
};


