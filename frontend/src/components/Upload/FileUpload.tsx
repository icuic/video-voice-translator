import React, { useState, useRef, useCallback } from 'react';
import { mediaService } from '../../services/media';
import { translationService } from '../../services/translation';

interface FileUploadProps {
  onUploadComplete: (fileId: string, taskId: string) => void;
}

export const FileUpload: React.FC<FileUploadProps> = ({ onUploadComplete }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sourceLanguage, setSourceLanguage] = useState('');
  const [targetLanguage, setTargetLanguage] = useState('');
  const [isStarting, setIsStarting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 从URL参数获取最大文件大小限制（单位：MB）
  const urlParams = new URLSearchParams(window.location.search);
  const maxSizeMB = urlParams.get('ms');
  const displayMaxSize = maxSizeMB || '100';

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
      alert('不支持的文件格式。支持的格式：视频 (MP4, AVI, MOV, MKV) 或 音频 (WAV, MP3, M4A)');
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
      alert(`文件大小超过 ${maxSizeDisplay}MB，请使用较小的文件`);
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
      
      console.log('正在启动翻译任务...', { fileId: mediaFile.id, sourceLanguage, targetLanguage });
      
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
          reject(new Error('启动翻译任务超时，请检查后端服务是否正常运行'));
        }, 30000);
      });
      
      const task = await Promise.race([startTranslationPromise, timeoutPromise]) as any;

      console.log('翻译任务启动成功:', task);
      setUploadProgress(100); // 任务启动完成
      // 上传和启动任务成功，通知父组件（父组件会显示进度界面）
      onUploadComplete(mediaFile.id, task.id);
      // 注意：这里不重置状态，让父组件处理界面切换
    } catch (error: any) {
      console.error('上传错误:', error);
      let errorMessage = '未知错误';
      
      if (error.message) {
        errorMessage = error.message;
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      } else if (error.response?.data?.message) {
        errorMessage = error.response.data.message;
      } else if (error.code === 'ECONNABORTED') {
        errorMessage = '请求超时，请检查网络连接或后端服务是否正常运行';
      } else if (error.message?.includes('超时')) {
        errorMessage = error.message;
      } else {
        errorMessage = '网络错误，请检查后端服务是否运行';
      }
      
      alert(`上传失败: ${errorMessage}\n\n如果问题持续，请检查：\n1. 后端服务是否正常运行\n2. 浏览器控制台是否有更多错误信息\n3. 后端日志文件`);
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
            href="https://github.com" 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-white hover:text-indigo-400 transition-colors"
          >
            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
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
              <p className="text-sm text-slate-500">Max {displayMaxSize}MB supported in browser</p>
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
                  <label className="block text-sm text-slate-400 mb-1">源语言</label>
                  <select
                    value={sourceLanguage}
                    onChange={(e) => setSourceLanguage(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    className="px-4 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">请选择源语言</option>
                    <option value="zh">中文</option>
                    <option value="en">English</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">目标语言</label>
                  <select
                    value={targetLanguage}
                    onChange={(e) => setTargetLanguage(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    className="px-4 py-2 bg-slate-700 text-white rounded-lg border border-slate-600 focus:border-indigo-500 focus:outline-none"
                  >
                    <option value="">请选择目标语言</option>
                    <option value="zh">中文</option>
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
                      ? '正在启动翻译任务...'
                      : `正在上传文件... ${Math.round(uploadProgress)}%`}
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
                  开始翻译
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

