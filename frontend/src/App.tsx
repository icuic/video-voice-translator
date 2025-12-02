import { useState, useRef, useEffect } from 'react';
import { FileUpload } from './components/Upload/FileUpload';
import { VideoPlayer } from './components/VideoPlayer/VideoPlayer';
import { SegmentList } from './components/SegmentList/SegmentList';
import { Timeline } from './components/Timeline/Timeline';
import { TranslationProgress } from './components/Progress/TranslationProgress';
import { useSegmentStore } from './stores/useSegmentStore';
import { segmentService } from './services/segments';
import { translationService } from './services/translation';
import { mediaService } from './services/media';
import { Segment } from './types/segment';
import { TranslationTask } from './types/media';

function App() {
  const { segments, setSegments, updateSegment, deleteSegment } = useSegmentStore();
  const [currentTime, setCurrentTime] = useState(0);
  const [videoSrc, setVideoSrc] = useState('');
  const [originalVideoUrl, setOriginalVideoUrl] = useState('');
  const [dubbedVideoUrl, setDubbedVideoUrl] = useState<string | null>(null);
  const [videoSource, setVideoSource] = useState<'original' | 'dubbed'>('original');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [isRetranslating, setIsRetranslating] = useState<{ [key: number]: boolean }>({});
  const [isResynthesizing, setIsResynthesizing] = useState<{ [key: number]: boolean }>({});
  const [videoDuration, setVideoDuration] = useState(0);
  const [showEditor, setShowEditor] = useState(false);
  const [showProgress, setShowProgress] = useState(false);
  const [translationTask, setTranslationTask] = useState<TranslationTask | null>(null);
  const [resynthesizedSegments, setResynthesizedSegments] = useState<Set<number>>(new Set()); // 已重新合成的分段ID集合
  const [isRegenerating, setIsRegenerating] = useState(false); // 是否正在重新生成
  
  // 计算待重新生成的分段数量
  const pendingRegenerateCount = resynthesizedSegments.size;

  const videoRef = useRef<HTMLVideoElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const regenerateCheckIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null); // 存储重新生成检查的定时器引用
  const hasShownRegenerateAlertRef = useRef<boolean>(false); // 标记是否已经显示过重新生成完成的提示

  // 根据当前选择的视频源更新实际播放的 src
  useEffect(() => {
    if (videoSource === 'dubbed' && dubbedVideoUrl) {
      setVideoSrc(dubbedVideoUrl);
    } else if (originalVideoUrl) {
      setVideoSrc(originalVideoUrl);
    }
  }, [videoSource, originalVideoUrl, dubbedVideoUrl]);

  // WebSocket 连接，用于接收重新合成完成通知
  useEffect(() => {
    if (!taskId) {
      // 如果没有任务ID，关闭现有连接
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      return;
    }

    const connectWebSocket = () => {
      // 如果已有连接，先关闭
      if (wsRef.current) {
        wsRef.current.close();
      }

      // 建立 WebSocket 连接
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/api/websocket/${taskId}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('WebSocket 连接已建立:', taskId);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'resynthesize_complete') {
            const segmentId = data.segment_id;
            console.log('收到重新合成完成通知:', segmentId);

            // 更新按钮状态
            setIsResynthesizing(prev => ({ ...prev, [segmentId]: false }));

            // 重新加载分段列表，确保获取最新的音频路径
            // 注意：只更新音频路径，避免覆盖用户的翻译文本修改
            segmentService.getSegments(taskId).then(updatedSegments => {
              // 合并更新：保留前端状态中的翻译文本，只更新音频相关字段
              const mergedSegments = segments.map(existingSegment => {
                const updatedSegment = updatedSegments.find(s => s.id === existingSegment.id);
                if (updatedSegment) {
                  return {
                    ...updatedSegment,
                    // 保留用户手动修改的翻译文本
                    translated_text: existingSegment.translated_text || updatedSegment.translated_text,
                    // 更新音频路径等后端生成的内容
                    cloned_audio_path: updatedSegment.cloned_audio_path,
                    original_duration: updatedSegment.original_duration,
                    cloned_duration: updatedSegment.cloned_duration,
                    duration_multiplier: updatedSegment.duration_multiplier,
                  };
                }
                return existingSegment;
              });
              setSegments(mergedSegments);
            }).catch(error => {
              console.error('重新加载分段列表失败:', error);
            });
          }
        } catch (error) {
          console.error('解析WebSocket消息失败:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket 错误:', error);
      };

      ws.onclose = (event) => {
        console.log('WebSocket 连接已关闭，原因:', event.code, event.reason);
        wsRef.current = null;

        // 如果是非正常关闭（不是组件卸载导致的），尝试重连
        if (event.code !== 1000 && event.code !== 1001) {
          console.log('尝试重连WebSocket...');
          setTimeout(connectWebSocket, 2000); // 2秒后重试
        }
      };
    };

    // 初始连接
    connectWebSocket();

    // 清理函数
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [taskId]);

  // 轮询任务状态（使用递归setTimeout实现动态间隔）
  const pollTaskStatus = async (tid: string, pollCount = 0) => {
      try {
        const status = await translationService.getStatus(tid);
        setTranslationTask(status); // 更新任务状态用于显示进度
        
        // 如果任务完成或需要编辑，显示编辑器
        if (status.status === 'completed' || status.status === 'paused_step4' || status.status === 'paused_step5') {
          setShowProgress(false); // 隐藏进度显示
          setShowEditor(true);
          
          // 加载分段数据（如果任务完成，分段数据仍然可用）
          try {
            const segs = await segmentService.getSegments(tid);
            setSegments(segs);
          } catch (error) {
            console.warn('无法加载分段数据（可能任务已完成，分段文件不存在）:', error);
            // 如果分段数据不存在，设置为空数组
            setSegments([]);
          }

          // 根据任务状态设置视频源
          if (status.status === 'completed') {
            // 任务完成：使用翻译后的视频
            const result = await translationService.getResult(tid);
            if (result.video_path) {
              const dubbedUrl = `/api/media/result/${tid}`;
              setDubbedVideoUrl(dubbedUrl);
              setVideoSource('dubbed');
            } else {
              // 如果没有生成配音视频，则回退到原始视频
              setVideoSource('original');
            }
          } else if (status.status === 'paused_step4' || status.status === 'paused_step5') {
            // 任务暂停：使用原始视频（因为翻译还没完成）
            // videoSrc 已经在 handleUploadComplete 中设置了原始视频URL
            // 这里不需要修改
          }
        return; // 停止轮询
        } else if (status.status === 'failed') {
          setShowProgress(false);
          setShowEditor(false);
          alert('翻译任务失败: ' + status.message);
        return; // 停止轮询
        } else if (status.status === 'processing' || status.status === 'pending') {
          // 任务处理中或等待中，显示进度
          setShowProgress(true);
          setShowEditor(false);
        }

      // 计算下次轮询间隔
      let nextInterval = 1000; // 默认1秒
      if (pollCount > 30) { // 30秒后
        nextInterval = 2000; // 2秒
      }
      if (pollCount > 120) { // 2分钟后
        nextInterval = 3000; // 3秒
      }
      if (status.current_step && status.current_step >= 7) { // 步骤7及以后
        nextInterval = Math.min(nextInterval * 1.5, 5000); // 最长5秒
      }

      // 继续轮询（如果还没到15分钟超时）
      if (pollCount * 1000 < 15 * 60 * 1000) { // 15分钟超时
        setTimeout(() => pollTaskStatus(tid, pollCount + 1), nextInterval);
      }

      } catch (error) {
        console.error('获取任务状态失败:', error);
      // 网络错误时使用更长的间隔重试
      const retryInterval = Math.min(5000 + pollCount * 500, 15000); // 最长15秒
      if (pollCount * 1000 < 15 * 60 * 1000) {
        setTimeout(() => pollTaskStatus(tid, pollCount + 1), retryInterval);
      }
    }
  };

  // 处理上传完成
  const handleUploadComplete = async (uploadedFileId: string, uploadedTaskId: string) => {
    setTaskId(uploadedTaskId);
    
    // 获取视频URL
    const videoUrl = mediaService.getMedia(uploadedFileId);
    setOriginalVideoUrl(videoUrl);
    setDubbedVideoUrl(null);
    setVideoSource('original');
    
    // 显示进度界面（隐藏编辑器）
    setShowProgress(true);
    setShowEditor(false);
    
    // 获取初始任务状态
    try {
      const initialStatus = await translationService.getStatus(uploadedTaskId);
      setTranslationTask(initialStatus);
      
      // 如果初始状态不是处理中，也要显示进度界面（等待任务开始）
      if (initialStatus.status === 'pending') {
        // 任务还在等待中，显示进度界面等待任务开始
        setShowProgress(true);
        setShowEditor(false);
      } else if (initialStatus.status === 'processing') {
        // 任务正在处理中，显示进度界面
        setShowProgress(true);
        setShowEditor(false);
      } else if (initialStatus.status === 'completed' || initialStatus.status === 'paused_step4' || initialStatus.status === 'paused_step5') {
        // 任务已完成或暂停，显示编辑器
        setShowProgress(false);
        setShowEditor(true);
      }
    } catch (error) {
      console.error('获取初始任务状态失败:', error);
      // 即使获取失败，也显示进度界面
      setShowProgress(true);
      setShowEditor(false);
    }
    
    // 开始轮询任务状态
    pollTaskStatus(uploadedTaskId);
  };

  // 处理视频时长更新
  const handleVideoLoaded = () => {
    if (videoRef.current) {
      setVideoDuration(videoRef.current.duration || 0);
    }
  };

  // 处理视频时间更新（来自VideoPlayer的唯一video元素）
  const handleVideoTimeUpdate = (time: number) => {
    // 拖动时完全忽略，避免冲突
    if (!isDraggingPlayhead) {
      setCurrentTime(time);
    }
  };

  // 处理视频播放完成
  const handleVideoEnded = () => {
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      setCurrentTime(0);
    }
  };

  // 点击分段时跳转视频
  const handleSegmentClick = (segment: Segment) => {
    if (videoRef.current) {
      videoRef.current.currentTime = segment.start;
      videoRef.current.play();
    }
  };

  // 处理时间轴跳转（简化版本：直接更新视频，不通过复杂的状态管理）
  const [isDraggingPlayhead, setIsDraggingPlayhead] = useState(false);
  const wasPlayingRef = useRef(false);
  
  const handleTimelineSeek = (time: number) => {
    // 直接更新VideoPlayer的video元素（这是唯一的真相源）
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      setCurrentTime(time);
    }
  };

  // 处理拖动开始
  const handleDragStart = () => {
    if (videoRef.current) {
      wasPlayingRef.current = !videoRef.current.paused;
      if (!videoRef.current.paused) {
        videoRef.current.pause();
      }
    }
    setIsDraggingPlayhead(true);
  };

  // 处理拖动结束
  const handleDragEnd = () => {
    setIsDraggingPlayhead(false);
    // 如果之前正在播放，恢复播放
    if (wasPlayingRef.current && videoRef.current) {
      videoRef.current.play().catch(() => {
        // 忽略播放失败
      });
    }
  };

  // 更新分段
  const handleSegmentUpdate = async (segment: Segment) => {
    if (!taskId) return;
    try {
      console.log('准备更新分段:', segment);
      console.log('当前segments数组长度:', segments.length);

      // 直接构造更新后的segments数组，确保包含所有分段
      const updatedSegments = segments.map(s => s.id === segment.id ? segment : s);
      console.log('更新后的segments长度:', updatedSegments.length);

      // 更新store状态
      updateSegment(segment);

      // 发送完整的分段列表，确保后端不会丢失其他分段
      await segmentService.updateSegments(taskId, updatedSegments);
      console.log('分段更新成功');
    } catch (error) {
      console.error('保存分段失败:', error);
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      alert(`保存分段失败: ${errorMessage}`);
      // 如果保存失败，回滚前端状态
      // 这里可以重新加载分段列表，或者显示错误状态
    }
  };

  // 删除分段
  const handleSegmentDelete = async (segmentId: number) => {
    if (!taskId) return;
    deleteSegment(segmentId);
    await segmentService.deleteSegments(taskId, [segmentId]);
  };

  // 重新翻译
  const handleRetranslate = async (segmentId: number, newText?: string) => {
    if (!taskId) return;
    setIsRetranslating(prev => ({ ...prev, [segmentId]: true }));
    try {
      const updated = await segmentService.retranslateSegment(taskId, segmentId, newText);
      updateSegment(updated);
    } catch (error) {
      console.error('翻译失败:', error);
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      alert(`翻译失败: ${errorMessage}`);
    } finally {
      setIsRetranslating(prev => ({ ...prev, [segmentId]: false }));
    }
  };

  // 重新合成
  const handleResynthesize = async (segmentId: number) => {
    if (!taskId) return;
    setIsResynthesizing(prev => ({ ...prev, [segmentId]: true }));
    try {
      await segmentService.resynthesizeSegment(taskId, segmentId);
      // 不显示弹窗，避免打扰用户
      // alert('重新合成任务已启动，请稍候...');

      // 将分段ID添加到已重新合成的集合中（如果已存在则不会重复添加）
      setResynthesizedSegments(prev => new Set(prev).add(segmentId));

      // 开始轮询检查合成状态，作为WebSocket的后备方案
      pollSegmentStatus(taskId, segmentId);

    } catch (error) {
      console.error('启动重新合成失败:', error);
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      alert(`启动重新合成失败: ${errorMessage}`);
      setIsResynthesizing(prev => ({ ...prev, [segmentId]: false }));
    }
  };

  // 拆分分段
  const handleSegmentSplit = async (segmentId: number, splitTextPosition: number) => {
    if (!taskId) return;
    try {
      const newSegments = await segmentService.splitSegment(taskId, segmentId, undefined, undefined, splitTextPosition);
      setSegments(newSegments);
      // 选中第一个新分段（原分段位置，即 segmentId）
      const firstNewSegment = newSegments.find(s => s.id === segmentId);
      if (firstNewSegment) {
        handleSegmentClick(firstNewSegment);
      }
    } catch (error) {
      console.error('拆分分段失败:', error);
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      alert(`拆分分段失败: ${errorMessage}`);
      throw error; // 重新抛出错误，让 SegmentItem 知道拆分失败
    }
  };

  // 轮询检查分段合成状态（作为WebSocket的后备方案）
  const pollSegmentStatus = async (taskId: string, segmentId: number, attemptCount = 0) => {
    const maxAttempts = 30; // 最多检查30次（约30秒）
    const pollInterval = 1000; // 每1秒检查一次

    try {
      const response = await fetch(`/api/segments/${taskId}/segments/${segmentId}/status`);
      if (response.ok) {
        const status = await response.json();
        if (status.status === 'completed') {
          console.log(`轮询检测到分段 ${segmentId} 合成完成`);
          // 更新按钮状态
          setIsResynthesizing(prev => ({ ...prev, [segmentId]: false }));

          // 重新加载分段列表，确保获取最新的音频路径
          // 注意：只更新音频路径，避免覆盖用户的翻译文本修改
          segmentService.getSegments(taskId).then(updatedSegments => {
            // 合并更新：保留前端状态中的翻译文本，只更新音频相关字段
            const mergedSegments = segments.map(existingSegment => {
              const updatedSegment = updatedSegments.find(s => s.id === existingSegment.id);
              if (updatedSegment) {
                return {
                  ...updatedSegment,
                  // 保留用户手动修改的翻译文本
                  translated_text: existingSegment.translated_text || updatedSegment.translated_text,
                  // 更新音频路径等后端生成的内容
                  cloned_audio_path: updatedSegment.cloned_audio_path,
                  original_duration: updatedSegment.original_duration,
                  cloned_duration: updatedSegment.cloned_duration,
                  duration_multiplier: updatedSegment.duration_multiplier,
                };
              }
              return existingSegment;
            });
            setSegments(mergedSegments);
          }).catch(error => {
            console.error('重新加载分段列表失败:', error);
          });

          return; // 停止轮询
        }
      } else if (response.status === 404) {
        // 任务目录不存在，可能是后端重启导致任务状态丢失
        // 直接尝试获取音频文件来检查是否已完成
        try {
          const audioResponse = await fetch(`/api/segments/${taskId}/segments/${segmentId}/cloned-audio`, { method: 'HEAD' });
          if (audioResponse.ok) {
            console.log(`检测到分段 ${segmentId} 音频文件存在，假设合成已完成`);
            // 更新按钮状态
            setIsResynthesizing(prev => ({ ...prev, [segmentId]: false }));

            // 重新加载分段列表
            // 注意：只更新音频路径，避免覆盖用户的翻译文本修改
            segmentService.getSegments(taskId).then(updatedSegments => {
              // 合并更新：保留前端状态中的翻译文本，只更新音频相关字段
              const mergedSegments = segments.map(existingSegment => {
                const updatedSegment = updatedSegments.find(s => s.id === existingSegment.id);
                if (updatedSegment) {
                  return {
                    ...updatedSegment,
                    // 保留用户手动修改的翻译文本
                    translated_text: existingSegment.translated_text || updatedSegment.translated_text,
                    // 更新音频路径等后端生成的内容
                    cloned_audio_path: updatedSegment.cloned_audio_path,
                    original_duration: updatedSegment.original_duration,
                    cloned_duration: updatedSegment.cloned_duration,
                    duration_multiplier: updatedSegment.duration_multiplier,
                  };
                }
                return existingSegment;
              });
              setSegments(mergedSegments);
            }).catch(error => {
              console.error('重新加载分段列表失败:', error);
            });

            return; // 停止轮询
          }
        } catch (audioError) {
          console.warn('检查音频文件失败:', audioError);
        }
      }
    } catch (error) {
      console.error('检查分段状态失败:', error);
    }

    // 如果还没完成且未达到最大尝试次数，继续轮询
    if (attemptCount < maxAttempts) {
      setTimeout(() => pollSegmentStatus(taskId, segmentId, attemptCount + 1), pollInterval);
    } else {
      console.warn(`分段 ${segmentId} 合成状态检查超时，停止轮询`);
      // 超时后设置按钮状态为非合成中（用户可以手动刷新或重试）
      setIsResynthesizing(prev => ({ ...prev, [segmentId]: false }));
    }
  };

  // 重新生成最终视频
  const handleRegenerateFinal = async () => {
    if (!taskId) return;
    
    // 如果已经有定时器在运行，先清除它
    if (regenerateCheckIntervalRef.current) {
      clearInterval(regenerateCheckIntervalRef.current);
      regenerateCheckIntervalRef.current = null;
    }
    
    // 重置提示标志
    hasShownRegenerateAlertRef.current = false;
    
    setIsRegenerating(true);
    try {
      await segmentService.regenerateFinal(taskId);
      alert('重新生成最终视频任务已启动，请稍候...');
      
      // 清空已重新合成的分段集合
      setResynthesizedSegments(new Set());
      
      // 等待一段时间后刷新视频URL，确保使用新的视频文件
      // 使用轮询方式检查任务状态，最多等待30秒
      let attempts = 0;
      const maxAttempts = 15;
      regenerateCheckIntervalRef.current = setInterval(async () => {
        attempts++;
        if (taskId && attempts <= maxAttempts) {
          try {
            // 重新获取任务结果，检查视频是否已更新
            const result = await translationService.getResult(taskId);
            if (result.video_path) {
              // 更新配音视频URL，添加时间戳避免缓存
              const timestamp = Date.now();
              const newDubbedUrl = `/api/media/result/${taskId}?t=${timestamp}`;
              setDubbedVideoUrl(newDubbedUrl);
              // 如果当前正在查看配音视频，强制刷新视频源
              if (videoSource === 'dubbed') {
                // 先设置为空，再设置为新URL，强制浏览器重新加载
                setVideoSrc('');
                setTimeout(() => {
                  setVideoSrc(newDubbedUrl);
                  // 强制视频元素重新加载
                  if (videoRef.current) {
                    videoRef.current.load();
                  }
                }, 100);
              }
              
              // 清除定时器
              if (regenerateCheckIntervalRef.current) {
                clearInterval(regenerateCheckIntervalRef.current);
                regenerateCheckIntervalRef.current = null;
              }
              
              // 只弹出一次提示
              if (!hasShownRegenerateAlertRef.current) {
                hasShownRegenerateAlertRef.current = true;
                alert('最终视频已重新生成！');
              }
            }
          } catch (error) {
            console.error('检查视频生成状态失败:', error);
            if (attempts >= maxAttempts) {
              if (regenerateCheckIntervalRef.current) {
                clearInterval(regenerateCheckIntervalRef.current);
                regenerateCheckIntervalRef.current = null;
              }
            }
          }
        } else {
          if (regenerateCheckIntervalRef.current) {
            clearInterval(regenerateCheckIntervalRef.current);
            regenerateCheckIntervalRef.current = null;
          }
          if (!hasShownRegenerateAlertRef.current) {
            hasShownRegenerateAlertRef.current = true;
            alert('视频生成可能需要更长时间，请稍后刷新页面查看。');
          }
        }
      }, 2000); // 每2秒检查一次
    } catch (error) {
      console.error('启动重新生成失败:', error);
      const errorMessage = error instanceof Error ? error.message : '未知错误';
      alert(`启动重新生成失败: ${errorMessage}`);
    } finally {
      setIsRegenerating(false);
    }
  };

      // 如果还没有上传文件，显示上传界面
      if (!showEditor && !showProgress) {
        return <FileUpload onUploadComplete={handleUploadComplete} />;
      }
      
      // 如果正在处理中或等待中，显示进度界面
      if (showProgress) {
        // 如果没有任务状态，创建一个默认的等待状态
        const displayTask = translationTask || {
          id: taskId || '',
          file_id: '',
          status: 'pending' as const,
          current_step: 0,
          progress: 0,
          message: '正在启动翻译任务...',
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
              </div>
              
              {/* 进度显示 */}
              <TranslationProgress task={displayTask} />
            </div>
          </div>
        );
      }

  // 显示编辑界面
  return (
    <div className="min-h-screen bg-slate-900 text-white">
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <h1 className="text-3xl font-bold">Video Voice Translator</h1>
          </div>
          <div className="flex items-center gap-3">
            {/* 重新生成最终视频按钮 */}
            {pendingRegenerateCount > 0 && (
              <button
                onClick={handleRegenerateFinal}
                disabled={isRegenerating}
                className={`
                  relative px-4 py-2 rounded-lg transition-colors font-medium
                  ${isRegenerating
                    ? 'bg-slate-600 text-slate-400 cursor-not-allowed'
                    : 'bg-orange-600 hover:bg-orange-700 text-white'
                  }
                `}
                title={`有 ${pendingRegenerateCount} 个分段已重新合成，需要重新生成最终视频以应用更改`}
              >
                重新生成最终视频
                <span className="absolute -top-2 -right-2 bg-red-500 text-white text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center">
                  {pendingRegenerateCount}
                </span>
              </button>
            )}
            <button
              onClick={() => {
                setShowEditor(false);
                setTaskId(null);
                setVideoSrc('');
                setOriginalVideoUrl('');
                setDubbedVideoUrl(null);
                setVideoSource('original');
                setSegments([]);
                setResynthesizedSegments(new Set());
              }}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            >
              上传新文件
            </button>
          </div>
        </div>
        
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 视频播放器 */}
          <div className="lg:col-span-2 sticky top-0 z-10 lg:static lg:z-auto bg-slate-900 pb-4 lg:pb-0">
            {/* 原始视频 / 配音视频 切换标签 */}
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm text-slate-400">视频源：</span>
              <div className="flex rounded-lg bg-slate-800 p-1 text-sm">
                <button
                  onClick={() => setVideoSource('original')}
                  className={`px-3 py-1 rounded-md transition-colors ${
                    videoSource === 'original'
                      ? 'bg-white text-slate-900'
                      : 'text-slate-300 hover:text-white'
                  }`}
                >
                  原始视频
                </button>
                <button
                  onClick={() => dubbedVideoUrl && setVideoSource('dubbed')}
                  className={`ml-1 px-3 py-1 rounded-md transition-colors ${
                    videoSource === 'dubbed'
                      ? 'bg-white text-slate-900'
                      : dubbedVideoUrl
                        ? 'text-slate-300 hover:text-white'
                        : 'text-slate-500 cursor-not-allowed'
                  }`}
                  disabled={!dubbedVideoUrl}
                  title={dubbedVideoUrl ? '查看配音后视频' : '配音视频尚未生成'}
                >
                  配音视频
                </button>
              </div>
            </div>
            <div>
              <VideoPlayer
                src={videoSrc}
                videoRef={videoRef}
                currentTime={currentTime}
                isSeeking={isDraggingPlayhead}
                onTimeUpdate={handleVideoTimeUpdate}
                onEnded={handleVideoEnded}
                onLoadedMetadata={handleVideoLoaded}
              />
            </div>
          </div>

          {/* 分段列表 */}
          <div>
            <SegmentList
              segments={segments}
              currentTime={currentTime}
              taskId={taskId || undefined}
              onSegmentClick={handleSegmentClick}
              onSegmentUpdate={handleSegmentUpdate}
              onSegmentDelete={handleSegmentDelete}
              onRetranslate={handleRetranslate}
              onResynthesize={handleResynthesize}
              onSplit={handleSegmentSplit}
              isRetranslating={isRetranslating}
              isResynthesizing={isResynthesizing}
            />
          </div>
        </div>

        {/* 时间轴 */}
        <div className="mt-6">
          <Timeline
            segments={segments}
            duration={videoDuration}
            currentTime={currentTime}
            onSeek={handleTimelineSeek}
            onSegmentClick={handleSegmentClick}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          />
        </div>
      </div>
    </div>
  );
}

export default App;
