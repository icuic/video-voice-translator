import React, { useState, useRef, useCallback } from 'react';
import { mediaService } from '../../services/media';
import { translationService } from '../../services/translation';
import { TranslationHistoryItem } from '../../types/media';
import { HistoryTaskList } from './HistoryTaskList';
import { translateTaskText } from '../../utils/taskText';

interface FileUploadProps {
  onUploadComplete: (fileId: string, taskId: string) => void;
  onOpenHistoryTask: (task: TranslationHistoryItem) => void;
}

export const FileUpload: React.FC<FileUploadProps> = ({
  onUploadComplete,
  onOpenHistoryTask,
}) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sourceLanguage, setSourceLanguage] = useState('en');
  const [targetLanguage, setTargetLanguage] = useState('zh');
  const [isStarting, setIsStarting] = useState(false);
  const [historyTasks, setHistoryTasks] = useState<TranslationHistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [deletingTaskIds, setDeletingTaskIds] = useState<Record<string, boolean>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    const loadHistory = async () => {
      try {
        const tasks = await translationService.getHistory(12, 'completed');
        setHistoryTasks(tasks);
      } catch (error) {
        console.error('Failed to load history tasks:', error);
      } finally {
        setIsLoadingHistory(false);
      }
    };

    loadHistory();
  }, []);

  const handleSourceLanguageChange = (value: string) => {
    setSourceLanguage(value);
    if (value === 'en') setTargetLanguage('zh');
    if (value === 'zh') setTargetLanguage('en');
  };

  const handleTargetLanguageChange = (value: string) => {
    setTargetLanguage(value);
    if (value === 'en') setSourceLanguage('zh');
    if (value === 'zh') setSourceLanguage('en');
  };

  const handleDeleteHistoryTask = async (task: TranslationHistoryItem) => {
    const displayName = task.original_filename || task.file_name || task.task_id;
    const confirmed = window.confirm(
      `Delete the history task "${displayName}"?\n\nThis will remove the task record and its output directory.`
    );

    if (!confirmed) {
      return;
    }

    setDeletingTaskIds((prev) => ({ ...prev, [task.task_id]: true }));
    try {
      await translationService.deleteHistoryTask(task.task_id);
      setHistoryTasks((prev) => prev.filter((item) => item.task_id !== task.task_id));
    } catch (error) {
      console.error('Failed to delete history task:', error);
      alert('Failed to delete the history task. Please try again later or check the backend logs.');
    } finally {
      setDeletingTaskIds((prev) => {
        const next = { ...prev };
        delete next[task.task_id];
        return next;
      });
    }
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelect(files[0]);
    }
  }, []);

  const handleFileSelect = (file: File) => {
    // 检查文件类型
    const ext = file.name.toLowerCase().split('.').pop();
    const videoExts = ['mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv'];
    const audioExts = ['wav', 'mp3', 'm4a', 'flac', 'aac', 'ogg'];
    
    if (!videoExts.includes(ext || '') && !audioExts.includes(ext || '')) {
      alert('Unsupported file format. Supported formats: video (MP4, AVI, MOV, MKV) or audio (WAV, MP3, M4A).');
      return;
    }

    // 从URL参数获取最大文件大小限制（单位：MB）
    const urlParams = new URLSearchParams(window.location.search);
    const maxSizeMB = urlParams.get('ms');
    const maxSizeBytes = maxSizeMB 
      ? parseFloat(maxSizeMB) * 1024 * 1024  // 如果提供了参数，使用参数值
      : 100 * 1024 * 1024;  // 默认100MB

    // 检查文件大小
    if (file.size > maxSizeBytes) {
      const maxSizeDisplay = maxSizeMB || '100';
      alert(`File size exceeds ${maxSizeDisplay}MB. Please choose a smaller file.`);
      return;
    }

    setSelectedFile(file);
  };

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileSelect(files[0]);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setUploadProgress(0);

    try {
      // 上传文件，使用真实的上传进度回调
      const mediaFile = await mediaService.uploadMedia(
        selectedFile,
        (progress) => {
          // 上传进度：0-90%（留10%给启动任务）
          setUploadProgress(Math.min(progress * 0.9, 90));
        }
      );

      // 启动翻译任务
      setIsStarting(true);
      setUploadProgress(90); // 上传完成，进度设为90%
      
      console.log('Starting translation task...', { fileId: mediaFile.id, sourceLanguage, targetLanguage });
      
      // 添加超时处理
      const startTranslationPromise = translationService.startTranslation({
        fileId: mediaFile.id,
        sourceLanguage,
        targetLanguage,
        singleSpeaker: true,  // 默认跳过多说话人分离步骤
        enableSegmentEditing: false,  // 不暂停，直接完成整个流程
        enableTranslationEditing: false,  // 不暂停，直接完成整个流程
      });

      // 设置超时（30秒）
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => {
          reject(new Error('Starting the translation task timed out. Please make sure the backend service is running.'));
        }, 30000);
      });
      
      const task = await Promise.race([startTranslationPromise, timeoutPromise]) as any;

      console.log('Translation task started successfully:', task);
      setUploadProgress(100); // 任务启动完成
      // 上传和启动任务成功，通知父组件（父组件会显示进度界面）
      onUploadComplete(mediaFile.id, task.id);
      // 注意：这里不重置状态，让父组件处理界面切换
    } catch (error: any) {
      console.error('Upload error:', error);
      let errorMessage = 'Unknown error';
      
      if (error.message) {
        errorMessage = translateTaskText(error.message);
      } else if (error.response?.data?.detail) {
        errorMessage = translateTaskText(error.response.data.detail);
      } else if (error.response?.data?.message) {
        errorMessage = translateTaskText(error.response.data.message);
      } else if (error.code === 'ECONNABORTED') {
        errorMessage = 'Request timed out. Please check your network connection or backend service.';
      } else if (error.message?.includes('超时') || error.message?.toLowerCase().includes('timeout')) {
        errorMessage = translateTaskText(error.message);
      } else {
        errorMessage = 'Network error. Please make sure the backend service is running.';
      }
      
      alert(`Upload failed: ${errorMessage}\n\nIf the issue persists, please check:\n1. Whether the backend service is running\n2. Whether the browser console shows more errors\n3. The backend log files`);
      setIsUploading(false);
      setIsStarting(false);
      setUploadProgress(0);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-900 to-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-4xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <h1 className="text-3xl font-bold text-white">Video Voice Translator</h1>
          </div>
          <a
            href="https://notebooks.amd.com"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center"
          >
            <img
              src="https://notebooks.amd.com/static/image.png"
              alt="AMD Notebooks"
              className="h-8 w-auto max-w-[160px] object-contain brightness-0 invert"
            />
          </a>
        </div>

        {/* Main Content */}
        <div className="text-center mb-8">
          <h2 className="text-5xl font-bold text-white mb-2">
            Break Language Barriers
          </h2>
          <p className="text-5xl font-bold text-white mb-4">
            In Your Videos
          </p>
          <p className="text-lg text-slate-300 max-w-2xl mx-auto">
            Upload a video, choose a language, and dub it with realistic AI voices instantly.
          </p>
        </div>

        {/* Upload Area */}
        <div
          className={`
            relative border-2 border-dashed rounded-lg p-12 text-center
            transition-all duration-200
            ${isDragging 
              ? 'border-indigo-500 bg-indigo-500/20' 
              : 'border-slate-600 bg-slate-800/50'
            }
            ${selectedFile ? 'border-indigo-500 bg-indigo-500/10' : ''}
          `}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="video/*,audio/*"
            onChange={handleFileInputChange}
            className="hidden"
          />

          {!selectedFile ? (
            <>
              <div className="flex justify-center mb-4">
                <div className="w-16 h-16 bg-indigo-600 rounded-full flex items-center justify-center">
                  <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">Upload Video</h3>
              <p className="text-slate-400 mb-1">Drag & drop or click to select a video file</p>
            </>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-center gap-3">
                <div className="w-12 h-12 bg-indigo-600 rounded-lg flex items-center justify-center">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                </div>
                <div className="text-left">
                  <p className="text-white font-medium">{selectedFile.name}</p>
                  <p className="text-sm text-slate-400">{formatFileSize(selectedFile.size)}</p>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFile(null);
                    if (fileInputRef.current) {
                      fileInputRef.current.value = '';
                    }
                  }}
                  className="text-slate-400 hover:text-white"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {/* Language Selection */}
              <div className="flex gap-4 justify-center">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Source Language</label>
                  <select
                    value={sourceLanguage}
                    onChange={(e) => handleSourceLanguageChange(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    className="px-4 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">Select source language</option>
                    <option value="zh">Chinese</option>
                    <option value="en">English</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Target Language</label>
                  <select
                    value={targetLanguage}
                    onChange={(e) => handleTargetLanguageChange(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    className="px-4 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">Select target language</option>
                    <option value="zh">Chinese</option>
                    <option value="en">English</option>
                  </select>
                </div>
              </div>

              {/* Upload Progress */}
              {(isUploading || isStarting) && (
                <div className="space-y-2">
                  <div className="w-full bg-slate-700 rounded-full h-2">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${uploadProgress}%` }}
                    />
                  </div>
                  <p className="text-sm text-slate-400">
                    {isStarting
                      ? 'Starting translation task...'
                      : `Uploading file... ${Math.round(uploadProgress)}%`}
                  </p>
                </div>
              )}

              {/* Start Button */}
              {!isUploading && !isStarting && (
                <button
                  disabled={isStarting || !selectedFile || !sourceLanguage || !targetLanguage}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleUpload();
                  }}
                  className="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors mx-auto block"
                >
                  Start Translation
                </button>
              )}
            </div>
          )}
        </div>

        <HistoryTaskList
          tasks={historyTasks}
          isLoading={isLoadingHistory}
          onOpenTask={onOpenHistoryTask}
          onDeleteTask={handleDeleteHistoryTask}
          deletingTaskIds={deletingTaskIds}
        />
      </div>
    </div>
  );
};
