import React from 'react';
import { TranslationHistoryItem } from '../../types/media';

interface HistoryTaskListProps {
  tasks: TranslationHistoryItem[];
  isLoading: boolean;
  onOpenTask: (task: TranslationHistoryItem) => void;
  onDeleteTask: (task: TranslationHistoryItem) => void | Promise<void>;
  deletingTaskIds: Record<string, boolean>;
}

const statusLabelMap: Record<string, string> = {
  completed: '已完成',
  failed: '失败',
  processing: '处理中',
  pending: '等待中',
  paused_step4: '待编辑分段',
  paused_step5: '待编辑翻译',
};

const ThumbnailPreview: React.FC<{ task: TranslationHistoryItem }> = ({ task }) => {
  if (task.media_type !== 'video' || !task.thumbnail_url) {
    return (
      <div className="flex h-20 w-32 items-center justify-center rounded-lg bg-slate-800 text-xs text-slate-400">
        {task.media_type === 'audio' ? '音频任务' : '无缩略图'}
      </div>
    );
  }

  return (
    <div className="relative h-20 w-32 overflow-hidden rounded-lg bg-slate-800">
      <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-500">
        视频预览
      </div>
      <img
        src={task.thumbnail_url}
        alt={task.original_filename || task.file_name || task.task_id}
        className="absolute inset-0 h-full w-full object-cover"
        loading="lazy"
        onError={(event) => {
          event.currentTarget.style.display = 'none';
        }}
      />
    </div>
  );
};

export const HistoryTaskList: React.FC<HistoryTaskListProps> = ({
  tasks,
  isLoading,
  onOpenTask,
  onDeleteTask,
  deletingTaskIds,
}) => {
  return (
    <div className="mt-10 rounded-2xl border border-slate-700 bg-slate-800/40 p-6">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-xl font-semibold text-white">历史任务</h3>
        </div>
      </div>

      {isLoading ? (
        <div className="py-8 text-center text-slate-400">正在加载历史任务...</div>
      ) : tasks.length === 0 ? (
        <div className="py-8 text-center text-slate-400">暂无历史任务</div>
      ) : (
        <div className="space-y-3">
          {tasks.map((task) => (
            <div
              key={task.task_id}
              className="flex items-start gap-3 rounded-xl border border-slate-700 bg-slate-900/60 p-3"
            >
              <button
                type="button"
                onClick={() => onOpenTask(task)}
                className="flex flex-1 items-start gap-4 text-left transition-colors hover:text-indigo-200"
              >
                <ThumbnailPreview task={task} />
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-2 text-base font-medium text-white">
                    {task.original_filename || task.file_name || task.task_dir_name || task.task_id}
                  </div>
                  <div className="mt-1 text-sm text-slate-400">
                    {task.source_language || '-'} {'->'} {task.target_language || '-'}
                  </div>
                  <div className="mt-2 line-clamp-2 text-sm text-slate-500">
                    {task.message || task.task_dir_name || task.task_id}
                  </div>
                  <div className="mt-2 text-xs text-slate-500">{task.task_id}</div>
                </div>
              </button>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <div className="rounded-full bg-slate-700 px-3 py-1 text-xs text-slate-200">
                  {statusLabelMap[task.status] || task.status}
                </div>
                <button
                  type="button"
                  onClick={() => onDeleteTask(task)}
                  disabled={!!deletingTaskIds[task.task_id]}
                  className="rounded-lg border border-rose-500/50 px-3 py-1 text-xs text-rose-300 transition-colors hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {deletingTaskIds[task.task_id] ? '删除中...' : '删除'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
