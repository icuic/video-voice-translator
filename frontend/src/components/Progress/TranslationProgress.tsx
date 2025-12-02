import React from 'react';
import { TranslationTask } from '../../types/media';

interface TranslationProgressProps {
  task: TranslationTask;
}

export const TranslationProgress: React.FC<TranslationProgressProps> = ({ task }) => {
  const { status, progress, message, step_name, current_segment, total_segments } = task;

  // 构建进度文本
  const getProgressText = () => {
    if (status === 'processing') {
      return step_name || message || '处理中...';
    }
    return message;
  };

  return (
    <div className="w-full max-w-2xl mx-auto bg-slate-800 rounded-lg p-6 border border-slate-700">
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold text-white">翻译进度</h3>
          <span className="text-sm text-slate-400">{Math.round(progress)}%</span>
        </div>
        
        {/* 进度条 */}
        <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden relative">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 via-indigo-400 to-indigo-500 rounded-full transition-all duration-300 ease-out relative overflow-hidden"
            style={{ width: `${progress}%` }}
          >
            {/* 流动光效 */}
            <div 
              className="absolute inset-0 bg-gradient-to-r from-transparent via-white/50 to-transparent"
              style={{
                width: '50%',
                animation: 'shimmer 1.5s ease-in-out infinite',
              }}
            />
          </div>
        </div>
        <style>{`
          @keyframes shimmer {
            0% {
              transform: translateX(-200%);
            }
            100% {
              transform: translateX(200%);
            }
          }
        `}</style>
      </div>

      {/* 当前状态信息 */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-pulse" />
          <p className="text-white font-medium">{getProgressText()}</p>
        </div>
        
        {/* 详细进度信息（如果有片段信息） */}
        {(current_segment ?? 0) > 0 && (total_segments ?? 0) > 0 && (
          <div className="ml-4 text-sm text-slate-400">
            正在处理第 {current_segment} 个片段，共 {total_segments} 个片段
          </div>
        )}
      </div>
    </div>
  );
};

