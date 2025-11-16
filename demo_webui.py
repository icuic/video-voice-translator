#!/usr/bin/env python3
"""
音视频翻译 Web UI - 演示版
仅用于演示UI界面，不包含实际翻译功能
"""

import gradio as gr
import os
import tempfile
import shutil
import subprocess
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 支持的语言列表
LANGUAGES = {
    "中文": "zh",
    "English": "en"
}


def create_interface():
    with gr.Blocks(
        title="音视频翻译系统 - 演示版",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container { max-width: 1200px !important; }
        .video-container { display: flex; gap: 20px; align-items: flex-start; }
        .video-item { flex: 1; }
        .model-status-box { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 10px; margin: 10px 0; font-family: 'Courier New', monospace; font-size: 12px; }
        .status-loading { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .status-success { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
        .status-error { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
        
        /* 页面全屏样式 */
        .page-fullscreen-video {
            position: fixed !important;
            top: 0 !important;
            left: 0 !important;
            width: 100vw !important;
            height: 100vh !important;
            z-index: 99999 !important;
            background: #000 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            margin: 0 !important;
            padding: 0 !important;
            overflow: hidden !important;
        }
        
        .page-fullscreen-video video {
            max-width: 100vw !important;
            max-height: 100vh !important;
            width: auto !important;
            height: auto !important;
            object-fit: contain !important;
            display: block !important;
        }
        
        /* 全屏时隐藏其他内容 - 使用更温和的方式 */
        body.page-fullscreen-active {
            overflow: hidden !important;
        }
        
        body.page-fullscreen-active > *:not(.page-fullscreen-video) {
            visibility: hidden !important;
            pointer-events: none !important;
        }
        
        /* 确保全屏容器始终可见 */
        body.page-fullscreen-active .page-fullscreen-video {
            visibility: visible !important;
            pointer-events: auto !important;
        }
        
        /* 全屏时确保按钮可见 - 使用更高优先级的选择器 */
        body.page-fullscreen-active #input_fullscreen_btn,
        body.page-fullscreen-active #output_fullscreen_btn,
        .page-fullscreen-video #input_fullscreen_btn,
        .page-fullscreen-video #output_fullscreen_btn {
            position: fixed !important;
            top: 20px !important;
            left: 20px !important;
            z-index: 1000000 !important;
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
            background: rgba(0, 0, 0, 0.85) !important;
            color: white !important;
            border: 2px solid rgba(255, 255, 255, 0.9) !important;
            padding: 8px 16px !important;
            border-radius: 4px !important;
            font-size: 14px !important;
            font-weight: bold !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.6) !important;
            cursor: pointer !important;
        }
        
        /* 视频容器包装器 - 用于定位全屏按钮 */
        .video-container-wrapper {
            position: relative !important;
            display: block !important;
            width: 100% !important;
        }
        
        /* 全屏按钮样式 - 绝对定位在视频左上角 */
        #input_fullscreen_btn,
        #output_fullscreen_btn {
            position: absolute !important;
            top: 10px !important;
            left: 10px !important;
            z-index: 10000 !important;
            background: rgba(0, 0, 0, 0.75) !important;
            color: white !important;
            border: 2px solid rgba(255, 255, 255, 0.9) !important;
            padding: 6px 12px !important;
            border-radius: 4px !important;
            cursor: pointer !important;
            font-size: 13px !important;
            font-weight: bold !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.6) !important;
            transition: all 0.2s ease !important;
            margin: 0 !important;
            min-width: auto !important;
            width: auto !important;
            pointer-events: auto !important;
            opacity: 1 !important;
            visibility: visible !important;
        }
        
        #input_fullscreen_btn:hover,
        #output_fullscreen_btn:hover {
            background: rgba(0, 0, 0, 0.95) !important;
            border-color: #4facfe !important;
            transform: scale(1.05) !important;
        }
        """
    ) as demo:
        gr.HTML('''
        <div style="text-align: center; padding: 20px;">
            <h1>AI音视频翻译</h1>
            <p>支持中英互译、音色克隆</p>
        </div>
        <script>
        (function() {
            'use strict';
            
            // 隐藏Gradio的视频播放错误提示
            function hideVideoErrors() {
                // 查找并隐藏所有视频播放错误消息
                const errorSelectors = [
                    '.error',
                    '[class*="error"]',
                    '[class*="Error"]',
                    '.gradio-error',
                    '.error-message',
                    '[role="alert"]',
                    '.alert',
                    '.notification',
                    '.toast',
                    '[class*="toast"]',
                    '.banner',
                    '[class*="banner"]'
                ];
                
                errorSelectors.forEach(selector => {
                    try {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            const text = (el.textContent || el.innerText || '').trim();
                            if (text.includes('Video not playable') || 
                                text.includes('视频无法播放') ||
                                text.includes('Error') && text.includes('Video')) {
                                el.style.display = 'none';
                                el.style.visibility = 'hidden';
                                el.style.opacity = '0';
                                el.style.height = '0';
                                el.style.overflow = 'hidden';
                                el.style.margin = '0';
                                el.style.padding = '0';
                            }
                        });
                    } catch (e) {
                        // 静默处理
                    }
                });
            }
            
            // 拦截控制台错误
            const originalError = window.console.error;
            window.console.error = function(...args) {
                const message = args.join(' ');
                if (message.includes('Video not playable') || 
                    message.includes('视频无法播放')) {
                    // 静默处理视频播放错误
                    return;
                }
                originalError.apply(console, args);
            };
            
            // 定期隐藏错误消息
            setInterval(hideVideoErrors, 500);
            
            // 监听DOM变化，自动隐藏错误
            const errorObserver = new MutationObserver(() => {
                hideVideoErrors();
            });
            errorObserver.observe(document.body, {
                childList: true,
                subtree: true
            });
            
            // 全屏状态管理
            let currentFullscreenVideo = null;
            let currentFullscreenContainer = null;
            
            // 查找视频元素的容器
            function findVideoContainer(videoEl) {
                let container = videoEl.parentElement;
                let bestContainer = null;
                let maxArea = 0;
                
                // 向上查找最大的合适容器
                while (container && container !== document.body) {
                    const rect = container.getBoundingClientRect();
                    const area = rect.width * rect.height;
                    if (rect.width > 100 && rect.height > 100 && area > maxArea) {
                        if (container.contains(videoEl)) {
                            bestContainer = container;
                            maxArea = area;
                        }
                    }
                    container = container.parentElement;
                }
                
                if (bestContainer) {
                    return bestContainer;
                }
                
                // 备用方案：查找第一个足够大的父容器
                container = videoEl.parentElement;
                while (container && container !== document.body) {
                    const rect = container.getBoundingClientRect();
                    if (rect.width > 50 && rect.height > 50) {
                        return container;
                    }
                    container = container.parentElement;
                }
                
                return videoEl.parentElement || document.body;
            }
            
            // 进入全屏
            function enterFullscreen(videoEl, container) {
                if (currentFullscreenVideo) {
                    exitFullscreen();
                }
                
                currentFullscreenVideo = videoEl;
                currentFullscreenContainer = container;
                
                // 将容器移到body下（如果不在body下）
                if (container.parentElement !== document.body) {
                    document.body.appendChild(container);
                }
                
                // 添加全屏样式
                container.classList.add('page-fullscreen-video');
                document.body.classList.add('page-fullscreen-active');
                document.body.style.overflow = 'hidden';
                document.documentElement.style.overflow = 'hidden';
                
                // 更新按钮文本
                updateFullscreenButtons('✕ 退出全屏');
                
                // 添加ESC键监听
                document.addEventListener('keydown', handleEscapeKey);
                
                console.log('已进入全屏模式');
            }
            
            // 退出全屏
            function exitFullscreen() {
                if (currentFullscreenContainer) {
                    // 移除全屏样式
                    currentFullscreenContainer.classList.remove('page-fullscreen-video');
                    document.body.classList.remove('page-fullscreen-active');
                    document.body.style.overflow = '';
                    document.documentElement.style.overflow = '';
                    
                    updateFullscreenButtons('⛶ 页面全屏');
                }
                
                currentFullscreenVideo = null;
                currentFullscreenContainer = null;
                
                // 移除ESC键监听
                document.removeEventListener('keydown', handleEscapeKey);
                
                console.log('已退出全屏模式');
            }
            
            // ESC键处理
            function handleEscapeKey(e) {
                if (e.key === 'Escape' && currentFullscreenVideo) {
                    exitFullscreen();
                }
            }
            
            // 更新全屏按钮文本
            function updateFullscreenButtons(text) {
                const inputBtn = document.getElementById('input_fullscreen_btn');
                const outputBtn = document.getElementById('output_fullscreen_btn');
                if (inputBtn) inputBtn.textContent = text;
                if (outputBtn) outputBtn.textContent = text;
            }
            
            // 查找对应的视频元素
            function findVideoForButton(buttonId) {
                const button = document.getElementById(buttonId);
                if (!button) return null;
                
                // 向上查找包含视频的容器
                let container = button.closest('.gradio-column');
                if (!container) return null;
                
                // 在容器中查找video元素
                const video = container.querySelector('video');
                return video;
            }
            
            // 全屏按钮点击处理函数
            function handleFullscreenClick(buttonId) {
                console.log('全屏按钮被点击，buttonId:', buttonId);
                
                // 查找按钮
                const btn = document.getElementById(buttonId);
                if (!btn) {
                    console.error('未找到按钮:', buttonId);
                    return false;
                }
                
                // 查找视频元素
                let video = null;
                let container = null;
                
                // 从按钮向上查找包含视频的列
                const column = btn.closest('.gradio-column');
                if (column) {
                    video = column.querySelector('video');
                    if (video) {
                        container = findVideoContainer(video);
                    }
                }
                
                // 如果方式1失败，查找最近的视频元素
                if (!video) {
                    const allVideos = document.querySelectorAll('video');
                    let minDistance = Infinity;
                    for (let v of allVideos) {
                        const btnRect = btn.getBoundingClientRect();
                        const vRect = v.getBoundingClientRect();
                        const distance = Math.abs(btnRect.top - vRect.top) + Math.abs(btnRect.left - vRect.left);
                        if (distance < minDistance) {
                            minDistance = distance;
                            video = v;
                        }
                    }
                    if (video) {
                        container = findVideoContainer(video);
                    }
                }
                
                if (!video || !container) {
                    console.error('未找到视频元素或容器');
                    alert('未找到视频元素，请先上传视频');
                    return false;
                }
                
                // 切换全屏状态
                const isFullscreen = container.classList.contains('page-fullscreen-video');
                if (isFullscreen) {
                    console.log('退出全屏');
                    exitFullscreen();
                } else {
                    console.log('进入全屏');
                    enterFullscreen(video, container);
                }
                return true;
            }
            
            // 初始化全屏按钮事件（不覆盖Gradio的事件，只确保按钮可见和定位）
            function initFullscreenButtons() {
                // 不在这里绑定事件，让Gradio的click事件处理
                // 只负责按钮的显示和定位
            }
            
            // 定位按钮到视频播放器左上角
            function positionButtonOnVideo(buttonId) {
                const btn = document.getElementById(buttonId);
                if (!btn) {
                    console.log('按钮不存在:', buttonId);
                    return;
                }
                
                // 查找对应的视频元素
                const video = findVideoForButton(buttonId);
                if (!video) {
                    console.log('未找到视频元素:', buttonId);
                    return;
                }
                
                // 查找视频的父容器（Gradio视频组件容器）
                let videoContainer = video.parentElement;
                let bestContainer = null;
                let maxArea = 0;
                
                // 向上查找最大的合适容器
                while (videoContainer && videoContainer !== document.body) {
                    const rect = videoContainer.getBoundingClientRect();
                    const area = rect.width * rect.height;
                    if (rect.width > 100 && rect.height > 100 && area > maxArea && videoContainer.contains(video)) {
                        bestContainer = videoContainer;
                        maxArea = area;
                    }
                    videoContainer = videoContainer.parentElement;
                }
                
                if (bestContainer) {
                    // 确保容器是相对定位
                    const containerStyle = getComputedStyle(bestContainer);
                    if (containerStyle.position === 'static') {
                        bestContainer.style.position = 'relative';
                    }
                    
                    // 将按钮移动到视频容器内
                    if (btn.parentElement !== bestContainer) {
                        bestContainer.appendChild(btn);
                    }
                    
                    // 设置按钮样式 - 左上角
                    btn.style.position = 'absolute';
                    btn.style.top = '10px';
                    btn.style.left = '10px';
                    btn.style.zIndex = '10000';
                    btn.style.display = 'block';
                    btn.style.visibility = 'visible';
                    btn.style.opacity = '1';
                    btn.style.pointerEvents = 'auto';
                    btn.style.cursor = 'pointer';
                } else {
                    console.log('未找到合适的视频容器:', buttonId);
                }
            }
            
            // 检查视频是否存在并显示/隐藏按钮，同时定位按钮
            function updateFullscreenButtonVisibility() {
                const inputBtn = document.getElementById('input_fullscreen_btn');
                const outputBtn = document.getElementById('output_fullscreen_btn');
                
                // 检查输入视频
                const inputVideo = findVideoForButton('input_fullscreen_btn');
                if (inputBtn) {
                    const hasVideo = inputVideo && (
                        inputVideo.src || 
                        inputVideo.currentSrc || 
                        inputVideo.querySelector('source') ||
                        inputVideo.querySelector('source[src]')
                    );
                    
                    if (hasVideo) {
                        inputBtn.style.display = 'block';
                        inputBtn.style.visibility = 'visible';
                        inputBtn.style.opacity = '1';
                        inputBtn.style.pointerEvents = 'auto';
                        inputBtn.style.cursor = 'pointer';
                        inputBtn.style.zIndex = '10000';
                        positionButtonOnVideo('input_fullscreen_btn');
                        initFullscreenButtons();
                    } else {
                        inputBtn.style.display = 'none';
                    }
                }
                
                // 检查输出视频
                const outputVideo = findVideoForButton('output_fullscreen_btn');
                if (outputBtn) {
                    const hasVideo = outputVideo && (
                        outputVideo.src || 
                        outputVideo.currentSrc || 
                        outputVideo.querySelector('source') ||
                        outputVideo.querySelector('source[src]')
                    );
                    
                    if (hasVideo) {
                        outputBtn.style.display = 'block';
                        outputBtn.style.visibility = 'visible';
                        outputBtn.style.opacity = '1';
                        outputBtn.style.pointerEvents = 'auto';
                        outputBtn.style.cursor = 'pointer';
                        outputBtn.style.zIndex = '10000';
                        positionButtonOnVideo('output_fullscreen_btn');
                        initFullscreenButtons();
                    } else {
                        outputBtn.style.display = 'none';
                    }
                }
            }
            
            // 将函数暴露到全局作用域
            window.updateFullscreenButtonVisibility = updateFullscreenButtonVisibility;
            window.initFullscreenButtons = initFullscreenButtons;
            window.handleFullscreenClick = handleFullscreenClick;
            window.positionButtonOnVideo = positionButtonOnVideo;
            
            // 初始化
            function init() {
                initFullscreenButtons();
                updateFullscreenButtonVisibility();
            }
            
            // 延迟初始化
            setTimeout(init, 50);
            setTimeout(init, 100);
            setTimeout(init, 200);
            setTimeout(init, 500);
            setTimeout(init, 1000);
            
            // 使用MutationObserver监听DOM变化
            const observer = new MutationObserver((mutations) => {
                setTimeout(() => {
                    initFullscreenButtons();
                    updateFullscreenButtonVisibility();
                }, 50);
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['class', 'style']
            });
            
            // 监听窗口加载完成
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => {
                    setTimeout(init, 100);
                });
            } else {
                setTimeout(init, 100);
            }
        })();
        </script>
        ''')

        with gr.Row():
            with gr.Column(scale=1):
                with gr.Group():
                    gr.Markdown("### 上传文件")
                    input_mode = gr.Radio(choices=["视频", "音频"], value="视频", label="输入类型")
                    with gr.Row():
                        with gr.Column(scale=1, elem_classes="video-container-wrapper"):
                            input_video = gr.Video(label=" ", height=300, format="mp4", visible=True)
                            input_fullscreen_btn = gr.Button("⛶ 页面全屏", size="sm", visible=False, elem_id="input_fullscreen_btn", variant="secondary")
                    input_audio = gr.Audio(label=" ", sources=["upload"], type="filepath", interactive=True, visible=False)
                    file_info = gr.Textbox(label="文件信息", value="请上传媒体文件（视频或音频）...", interactive=False, lines=3)
                    current_media = gr.State(value=None)
                    converted_video_path = gr.State(value=None)  # 存储转换后的视频路径

            with gr.Column(scale=1):
                with gr.Group():
                    gr.Markdown("### 翻译设置")
                    with gr.Row():
                        source_language = gr.Dropdown(choices=list(LANGUAGES.keys()), value="中文", label="源语言", interactive=True)
                        target_language = gr.Dropdown(choices=list(LANGUAGES.keys()), value="English", label="目标语言", interactive=True)
                    single_speaker = gr.Checkbox(label="仅一人说话", value=False, interactive=True)
                    enable_editing = gr.Checkbox(
                        label="步骤5后暂停编辑翻译结果", 
                        value=False, 
                        interactive=True,
                        info="勾选后，步骤5完成时会暂停，允许您手动编辑翻译结果后再继续"
                    )
                    translate_btn = gr.Button("🚀 开始翻译", variant="primary", size="lg", scale=1, interactive=True)
                    status_text = gr.Textbox(label="处理状态", value="等待上传媒体...", interactive=False, lines=4)

            with gr.Column(scale=1):
                with gr.Group():
                    gr.Markdown("### 翻译结果")
                    with gr.Row():
                        with gr.Column(scale=1, elem_classes="video-container-wrapper"):
                            output_video = gr.Video(label=" ", height=300, format="mp4", sources=["upload"], visible=True, show_download_button=True)
                            output_fullscreen_btn = gr.Button("⛶ 页面全屏", size="sm", visible=False, elem_id="output_fullscreen_btn", variant="secondary")
                    output_audio = gr.Audio(label=" ", sources=["upload"], type="filepath", interactive=True, visible=False)
                    result_info = gr.Textbox(label="结果信息", value="翻译完成后将显示结果...", interactive=False, lines=3)

        # 获取模型状态格式化显示
        def get_model_status_display(status_text):
            """将模型状态文本转换为显示格式"""
            if status_text == "已加载":
                return "✅ 已加载"
            elif status_text == "加载失败":
                return "❌ 加载失败"
            elif status_text == "加载中...":
                return "⏳ 加载中..."
            else:  # "未加载"
                return "⏸️ 未加载"
        
        # 刷新模型状态（演示版：返回静态状态）
        def refresh_model_status():
            """演示版：返回静态模型状态"""
            return "⏸️ 演示模式", "⏸️ 演示模式", "⏸️ 演示模式", "⏸️ 演示模式", "⏸️ 演示模式"
        
        # 获取初始状态
        def get_initial_statuses():
            """获取初始模型状态"""
            initial_statuses = refresh_model_status()
            return initial_statuses

        refresh_btn = gr.Button("🔄 刷新状态", size="sm", variant="secondary")
        
        # 初始化状态
        initial_states = get_initial_statuses()
        with gr.Row():
            index_tts_status = gr.Textbox(label="IndexTTS2", value=initial_states[0], interactive=False, scale=1, lines=1, max_lines=1)
            whisper_status = gr.Textbox(label="Whisper", value=initial_states[1], interactive=False, scale=1, lines=1, max_lines=1)
            audio_sep_status = gr.Textbox(label="AudioSeparator", value=initial_states[2], interactive=False, scale=1, lines=1, max_lines=1)
            text_trans_status = gr.Textbox(label="TextTranslator", value=initial_states[3], interactive=False, scale=1, lines=1, max_lines=1)
            speaker_dia_status = gr.Textbox(label="SpeakerDiarizer", value=initial_states[4], interactive=False, scale=1, lines=1, max_lines=1)
        
        refresh_btn.click(fn=refresh_model_status, outputs=[index_tts_status, whisper_status, audio_sep_status, text_trans_status, speaker_dia_status])
        
        # 页面加载时自动刷新状态
        demo.load(fn=refresh_model_status, outputs=[index_tts_status, whisper_status, audio_sep_status, text_trans_status, speaker_dia_status])


        def convert_video_to_mp4(input_path: str) -> str:
            """
            将视频转换为浏览器兼容的 MP4 格式
            
            Args:
                input_path: 输入视频文件路径
                
            Returns:
                转换后的视频文件路径（如果转换失败，返回原路径）
            """
            try:
                # 检查输入文件是否存在
                if not os.path.exists(input_path):
                    logger.warning(f"输入文件不存在: {input_path}")
                    return input_path
                
                # 获取文件扩展名
                file_ext = Path(input_path).suffix.lower()
                
                # 如果已经是 mp4 格式，检查是否需要转换编码
                if file_ext == '.mp4':
                    # 使用 ffprobe 检查视频编码
                    try:
                        probe_cmd = [
                            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
                            '-show_entries', 'stream=codec_name', '-of', 'default=noprint_wrappers=1:nokey=1',
                            input_path
                        ]
                        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
                        codec = result.stdout.strip().lower()
                        
                        # 如果编码是浏览器兼容的（h264），直接返回
                        if codec in ['h264', 'avc1']:
                            logger.info(f"视频已使用兼容编码 {codec}，无需转换")
                            return input_path
                    except Exception as e:
                        logger.warning(f"无法检测视频编码: {e}，将进行转换")
                
                # 创建临时输出文件
                temp_dir = tempfile.gettempdir()
                output_filename = f"converted_{os.path.basename(input_path)}"
                output_path = os.path.join(temp_dir, output_filename)
                
                # 如果输出文件已存在，先删除
                if os.path.exists(output_path):
                    os.remove(output_path)
                
                logger.info(f"开始转换视频: {input_path} -> {output_path}")
                
                # 使用 ffmpeg 转换为浏览器兼容的 MP4 格式
                # 使用 h264 视频编码和 aac 音频编码，确保浏览器兼容性
                cmd = [
                    'ffmpeg', '-i', input_path,
                    '-c:v', 'libx264',           # 视频编码：H.264
                    '-preset', 'fast',           # 编码速度：快速
                    '-crf', '23',                # 质量：23（高质量）
                    '-c:a', 'aac',               # 音频编码：AAC
                    '-b:a', '128k',              # 音频比特率：128k
                    '-movflags', '+faststart',   # 优化网络播放
                    '-y',                        # 覆盖输出文件
                    output_path
                ]
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5分钟超时
                )
                
                if result.returncode == 0 and os.path.exists(output_path):
                    logger.info(f"视频转换成功: {output_path}")
                    return output_path
                else:
                    logger.error(f"视频转换失败: {result.stderr}")
                    # 转换失败时返回原文件
                    return input_path
                    
            except subprocess.TimeoutExpired:
                logger.error("视频转换超时")
                return input_path
            except FileNotFoundError:
                logger.error("ffmpeg 未安装或不在 PATH 中")
                return input_path
            except Exception as e:
                logger.error(f"视频转换出错: {e}")
                return input_path


        def on_media_upload(media, mode):
            """处理媒体文件上传（演示版：包含视频格式转换）"""
            if media is None:
                return (
                    "请上传媒体文件（视频或音频）...",
                    gr.update(value="中文", interactive=True),
                    gr.update(value="English", interactive=True),
                    gr.update(interactive=True),
                    "等待上传媒体...",
                    None,
                    gr.update(visible=False),
                    None  # 转换后的视频路径
                )
            
            try:
                # 获取文件路径
                file_path = media if isinstance(media, str) else (media.name if hasattr(media, 'name') else str(media))
                
                if not file_path or not os.path.exists(file_path):
                    return (
                        "❌ 文件路径无效",
                        gr.update(value="中文", interactive=True),
                        gr.update(value="English", interactive=True),
                        gr.update(interactive=True),
                        "❌ 文件上传失败",
                        None,
                        gr.update(visible=False),
                        None
                    )
                
                # 如果是视频模式，进行格式转换
                if mode == "视频":
                    logger.info(f"处理视频文件: {file_path}")
                    converted_path = convert_video_to_mp4(file_path)
                    
                    # 获取文件信息
                    file_size = os.path.getsize(converted_path) / (1024 * 1024)
                    file_name = os.path.basename(converted_path)
                    
                    if converted_path != file_path:
                        file_info_text = f"✅ 文件已上传（演示模式）\n📁 文件名: {file_name}\n📊 文件大小: {file_size:.2f} MB\n🔄 已转换为浏览器兼容格式"
                        status_msg = f"✅ 文件已上传\n📝 演示模式：纯前端界面，不会进行语言检测或翻译处理\n🔄 视频已转换为浏览器兼容格式\n💡 您可以手动选择源语言和目标语言"
                    else:
                        file_info_text = f"✅ 文件已上传（演示模式）\n📁 文件名: {file_name}\n📊 文件大小: {file_size:.2f} MB"
                        status_msg = "✅ 文件已上传\n📝 演示模式：纯前端界面，不会进行语言检测或翻译处理\n💡 您可以手动选择源语言和目标语言"
                    
                    return (
                        file_info_text,
                        gr.update(value="中文", interactive=True),
                        gr.update(value="English", interactive=True),
                        gr.update(interactive=True),
                        status_msg,
                        converted_path,
                        gr.update(visible=True),
                        converted_path  # 返回转换后的视频路径用于更新视频组件
                    )
                else:
                    # 音频模式
                    file_size = os.path.getsize(file_path) / (1024 * 1024)
                    file_name = os.path.basename(file_path)
                    file_info_text = f"✅ 文件已上传（演示模式）\n📁 文件名: {file_name}\n📊 文件大小: {file_size:.2f} MB"
                    status_msg = "✅ 文件已上传\n📝 演示模式：纯前端界面，不会进行语言检测或翻译处理\n💡 您可以手动选择源语言和目标语言"
                    
                    return (
                        file_info_text,
                        gr.update(value="中文", interactive=True),
                        gr.update(value="English", interactive=True),
                        gr.update(interactive=True),
                        status_msg,
                        file_path,
                        gr.update(visible=False),
                        None
                    )
                    
            except Exception as e:
                logger.error(f"处理媒体文件时出错: {e}")
                return (
                    f"❌ 处理文件时出错: {str(e)}",
                    gr.update(value="中文", interactive=True),
                    gr.update(value="English", interactive=True),
                    gr.update(interactive=True),
                    f"❌ 错误: {str(e)}",
                    None,
                    gr.update(visible=False),
                    None
                )

        def update_result_info(status):
            """更新结果信息"""
            if not status:
                return "翻译完成后将显示结果..."
            if "完成" in status or "成功" in status:
                return f"✅ {status}"
            if "失败" in status or "错误" in status:
                return f"❌ {status}"
            return f"⏳ {status}"

        def on_translate(media, src_lang, tgt_lang, mode, is_single_speaker, enable_edit):
            """演示版翻译函数：仅显示提示信息"""
            if media is None:
                return (
                    gr.update(value=None, visible=False, interactive=True, sources=["upload"]),
                    gr.update(value=None, visible=False, interactive=True, sources=["upload"]),
                    "请先上传媒体文件",
                    "翻译完成后将显示结果...",
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    gr.update(visible=False)
                )
            
            # 演示模式：显示提示信息
            demo_msg = "⚠️ 演示模式\n\n此界面仅用于演示UI布局和功能。\n实际翻译功能需要运行完整的系统。\n\n您可以上传视频文件到右侧结果区域进行预览。"
            if mode == "视频":
                return (
                    gr.update(value=None, visible=True, interactive=True, sources=["upload"]),
                    gr.update(value=None, visible=False, interactive=True, sources=["upload"]),
                    demo_msg,
                    "演示模式：请上传视频到右侧结果区域",
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    gr.update(visible=False)
                )
            else:
                return (
                    gr.update(value=None, visible=False, interactive=True, sources=["upload"]),
                    gr.update(value=None, visible=True, interactive=True, sources=["upload"]),
                    demo_msg,
                    "演示模式：请上传音频到右侧结果区域",
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    gr.update(visible=False)
                )

        translate_btn.click(
            fn=on_translate,
            inputs=[current_media, source_language, target_language, input_mode, single_speaker, enable_editing],
            outputs=[output_video, output_audio, status_text, result_info, source_language, target_language, translate_btn, output_fullscreen_btn]
        )

        def update_video_component(converted_path):
            """更新视频组件，使用转换后的视频路径"""
            if converted_path and os.path.exists(converted_path):
                return gr.update(value=converted_path)
            return gr.update()

        input_video.change(
            fn=on_media_upload,
            inputs=[input_video, input_mode],
            outputs=[file_info, source_language, target_language, translate_btn, status_text, current_media, input_fullscreen_btn, converted_video_path]
        ).then(
            fn=update_video_component,
            inputs=[converted_video_path],
            outputs=[input_video],
            js="""
            (video) => {
                if (video) {
                    const initFullscreen = () => {
                        if (typeof updateFullscreenButtonVisibility === 'function') {
                            updateFullscreenButtonVisibility();
                        }
                        if (typeof initFullscreenButtons === 'function') {
                            initFullscreenButtons();
                        }
                        if (typeof positionButtonOnVideo === 'function') {
                            positionButtonOnVideo('input_fullscreen_btn');
                        }
                    };
                    
                    initFullscreen();
                    setTimeout(initFullscreen, 100);
                    setTimeout(initFullscreen, 300);
                    setTimeout(initFullscreen, 500);
                    setTimeout(initFullscreen, 1000);
                    setTimeout(initFullscreen, 2000);
                }
                return video;
            }
            """
        )
        input_audio.change(
            fn=on_media_upload,
            inputs=[input_audio, input_mode],
            outputs=[file_info, source_language, target_language, translate_btn, status_text, current_media, input_fullscreen_btn, converted_video_path]
        )

        def on_mode_change(mode):
            """切换输入模式"""
            show_video = (mode == "视频")
            show_audio = (mode == "音频")
            return (
                gr.update(visible=show_video),
                gr.update(visible=show_audio),
                "请上传媒体文件（视频或音频）...",
                gr.update(value="中文", interactive=True),
                gr.update(value="English", interactive=True),
                gr.update(interactive=False),
                "等待上传媒体...",
                None,
                gr.update(visible=False)
            )
        input_mode.change(
            fn=on_mode_change,
            inputs=[input_mode],
            outputs=[input_video, input_audio, file_info, source_language, target_language, translate_btn, status_text, current_media, input_fullscreen_btn]
        )

        def on_mode_change_outputs(mode):
            """切换输出模式"""
            show_video = (mode == "视频")
            show_audio = (mode == "音频")
            return (
                gr.update(value=None, visible=show_video, interactive=True, sources=["upload"]),
                gr.update(value=None, visible=show_audio, interactive=True, sources=["upload"])
            )
        input_mode.change(
            fn=on_mode_change_outputs,
            inputs=[input_mode],
            outputs=[output_video, output_audio]
        )
        
        def process_output_video(video_path):
            """处理输出视频上传，进行格式转换"""
            if video_path is None:
                return None, gr.update(visible=False)
            
            try:
                if not os.path.exists(video_path):
                    logger.warning(f"输出视频文件不存在: {video_path}")
                    return None, gr.update(visible=False)
                
                # 转换视频格式
                converted_path = convert_video_to_mp4(video_path)
                logger.info(f"输出视频已转换: {converted_path}")
                return converted_path, gr.update(visible=True)
            except Exception as e:
                logger.error(f"处理输出视频时出错: {e}")
                return video_path, gr.update(visible=True)
        
        # 为输出视频组件添加格式转换和全屏按钮可见性控制
        output_video.change(
            fn=process_output_video,
            inputs=[output_video],
            outputs=[output_video, output_fullscreen_btn],
            js="""
            (video) => {
                if (video) {
                    const initFullscreen = () => {
                        if (typeof updateFullscreenButtonVisibility === 'function') {
                            updateFullscreenButtonVisibility();
                        }
                        if (typeof initFullscreenButtons === 'function') {
                            initFullscreenButtons();
                        }
                        if (typeof positionButtonOnVideo === 'function') {
                            positionButtonOnVideo('output_fullscreen_btn');
                        }
                    };
                    
                    initFullscreen();
                    setTimeout(initFullscreen, 100);
                    setTimeout(initFullscreen, 300);
                    setTimeout(initFullscreen, 500);
                    setTimeout(initFullscreen, 1000);
                    setTimeout(initFullscreen, 2000);
                }
                return [video, video ? true : false];
            }
            """
        )
        
        # 全屏按钮点击事件（使用JavaScript处理）
        def toggle_input_fullscreen():
            """触发输入视频全屏（实际功能由JavaScript处理）"""
            return None
        
        def toggle_output_fullscreen():
            """触发输出视频全屏（实际功能由JavaScript处理）"""
            return None
        
        input_fullscreen_btn.click(
            fn=toggle_input_fullscreen,
            inputs=[],
            outputs=[],
            js="""
            () => {
                console.log('Gradio输入全屏按钮被点击');
                try {
                    const btn = document.getElementById('input_fullscreen_btn');
                    if (!btn) {
                        console.error('未找到输入全屏按钮');
                        return [];
                    }
                    
                    // 查找视频元素 - 改进查找逻辑
                    let video = null;
                    let container = null;
                    
                    // 方法1: 从按钮所在的列查找
                    const column = btn.closest('.gradio-column');
                    if (column) {
                        video = column.querySelector('video');
                        if (video) {
                            // 查找包含video的Gradio视频组件容器
                            container = video.closest('[class*="video"]') || video.closest('.gradio-column') || video.parentElement;
                        }
                    }
                    
                    // 方法2: 如果方法1失败，查找第一个视频
                    if (!video) {
                        const allVideos = document.querySelectorAll('video');
                        if (allVideos.length > 0) {
                            // 找到第一个可见的视频
                            for (let v of allVideos) {
                                const rect = v.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    video = v;
                                    container = v.closest('[class*="video"]') || v.closest('.gradio-column') || v.parentElement;
                                    break;
                                }
                            }
                        }
                    }
                    
                    if (!video || !container) {
                        console.error('未找到视频元素或容器');
                        alert('未找到视频，请先上传视频');
                        return [];
                    }
                    
                    console.log('找到视频和容器:', video, container);
                    
                    // 检查是否已全屏
                    const isFullscreen = container.classList.contains('page-fullscreen-video');
                    
                    if (isFullscreen) {
                        // 退出全屏
                        console.log('退出全屏');
                        container.classList.remove('page-fullscreen-video');
                        document.body.classList.remove('page-fullscreen-active');
                        document.body.style.overflow = '';
                        document.documentElement.style.overflow = '';
                        btn.textContent = '⛶ 页面全屏';
                        
                        // 恢复按钮到视频容器内（而不是原来的父元素）
                        // 查找视频容器（video-container-wrapper或包含video的容器）
                        let videoContainer = null;
                        const video = container.querySelector('video');
                        if (video) {
                            // 查找包含video的容器
                            videoContainer = video.closest('.video-container-wrapper') || 
                                          video.closest('[class*="video"]') || 
                                          video.parentElement;
                        }
                        
                        // 如果找到了视频容器，将按钮移动到容器内
                        if (videoContainer && videoContainer !== btn.parentElement) {
                            videoContainer.appendChild(btn);
                            // 确保容器是相对定位
                            const containerStyle = getComputedStyle(videoContainer);
                            if (containerStyle.position === 'static') {
                                videoContainer.style.position = 'relative';
                            }
                        }
                        
                        // 恢复按钮样式为绝对定位（在视频容器内）
                        btn.style.position = 'absolute';
                        btn.style.top = '10px';
                        btn.style.left = '10px';
                        btn.style.zIndex = '10000';
                        btn.style.display = 'block';
                        btn.style.visibility = 'visible';
                        btn.style.opacity = '1';
                        btn.style.pointerEvents = 'auto';
                        btn.style.cursor = 'pointer';
                        
                        // 清除全屏相关的内联样式（保留基本样式，让CSS接管）
                        btn.style.background = '';
                        btn.style.color = '';
                        btn.style.border = '';
                        btn.style.padding = '';
                        btn.style.borderRadius = '';
                        btn.style.fontSize = '';
                        btn.style.fontWeight = '';
                        btn.style.boxShadow = '';
                        
                        // 移除ESC键监听
                        if (container._escapeHandler) {
                            document.removeEventListener('keydown', container._escapeHandler);
                            delete container._escapeHandler;
                        }
                        
                        // 延迟调用positionButtonOnVideo确保DOM已更新
                        setTimeout(() => {
                            if (typeof positionButtonOnVideo === 'function') {
                                positionButtonOnVideo(btn.id);
                            }
                        }, 100);
                    } else {
                        // 进入全屏
                        console.log('进入全屏');
                        
                        // 保存按钮的原始父元素和位置信息（在移动之前）
                        if (!container.dataset.originalBtnParent) {
                            container.dataset.originalBtnParent = JSON.stringify({
                                parentId: btn.parentElement ? btn.parentElement.id : '',
                                parentClass: btn.parentElement ? btn.parentElement.className : '',
                                nextSibling: btn.nextElementSibling ? btn.nextElementSibling.id || btn.nextElementSibling.className : null,
                                position: getComputedStyle(btn).position,
                                top: getComputedStyle(btn).top,
                                left: getComputedStyle(btn).left,
                                zIndex: getComputedStyle(btn).zIndex
                            });
                        }
                        
                        // 关键：将按钮移动到body下，确保不被隐藏
                        // 这样按钮就不会被 body.page-fullscreen-active > *:not(.page-fullscreen-video) 规则影响
                        if (btn.parentElement !== document.body) {
                            document.body.appendChild(btn);
                        }
                        
                        // 添加全屏样式
                        container.classList.add('page-fullscreen-video');
                        document.body.classList.add('page-fullscreen-active');
                        document.body.style.overflow = 'hidden';
                        document.documentElement.style.overflow = 'hidden';
                        btn.textContent = '✕ 退出全屏';
                        
                        // 设置按钮样式（确保在全屏时可见）
                        btn.style.position = 'fixed';
                        btn.style.top = '20px';
                        btn.style.left = '20px';
                        btn.style.zIndex = '1000000';
                        btn.style.display = 'block';
                        btn.style.visibility = 'visible';
                        btn.style.opacity = '1';
                        btn.style.pointerEvents = 'auto';
                        btn.style.cursor = 'pointer';
                        btn.style.background = 'rgba(0, 0, 0, 0.85)';
                        btn.style.color = 'white';
                        btn.style.border = '2px solid rgba(255, 255, 255, 0.9)';
                        btn.style.padding = '8px 16px';
                        btn.style.borderRadius = '4px';
                        btn.style.fontSize = '14px';
                        btn.style.fontWeight = 'bold';
                        btn.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.6)';
                        
                        // ESC键退出全屏
                        const handleEscape = (e) => {
                            if (e.key === 'Escape' && container.classList.contains('page-fullscreen-video')) {
                                container.classList.remove('page-fullscreen-video');
                                document.body.classList.remove('page-fullscreen-active');
                                document.body.style.overflow = '';
                                document.documentElement.style.overflow = '';
                                btn.textContent = '⛶ 页面全屏';
                                
                                // 恢复按钮位置（使用originalBtnParent中的数据）
                                if (container.dataset.originalBtnParent) {
                                    try {
                                        const originalData = JSON.parse(container.dataset.originalBtnParent);
                                        
                                        // 尝试找到原始父元素并恢复
                                        let originalParent = null;
                                        if (originalData.parentId) {
                                            originalParent = document.getElementById(originalData.parentId);
                                        } else if (originalData.parentClass) {
                                            const classes = originalData.parentClass.split(' ').filter(c => c);
                                            for (let cls of classes) {
                                                originalParent = document.querySelector('.' + cls);
                                                if (originalParent) break;
                                            }
                                        }
                                        
                                        if (originalParent && originalParent !== btn.parentElement) {
                                            if (originalData.nextSibling) {
                                                const nextSibling = originalParent.querySelector('#' + originalData.nextSibling) || 
                                                                  originalParent.querySelector('.' + originalData.nextSibling);
                                                if (nextSibling) {
                                                    originalParent.insertBefore(btn, nextSibling);
                                                } else {
                                                    originalParent.appendChild(btn);
                                                }
                                            } else {
                                                originalParent.appendChild(btn);
                                            }
                                        }
                                        
                                        btn.style.position = originalData.position || '';
                                        btn.style.top = originalData.top || '';
                                        btn.style.left = originalData.left || '';
                                        btn.style.zIndex = originalData.zIndex || '';
                                    } catch (e) {
                                        btn.style.position = '';
                                        btn.style.top = '';
                                        btn.style.left = '';
                                        btn.style.zIndex = '';
                                    }
                                } else {
                                    btn.style.position = '';
                                    btn.style.top = '';
                                    btn.style.left = '';
                                    btn.style.zIndex = '';
                                }
                                
                                // 清除按钮的内联样式
                                btn.style.display = '';
                                btn.style.visibility = '';
                                btn.style.opacity = '';
                                btn.style.background = '';
                                btn.style.color = '';
                                btn.style.border = '';
                                btn.style.padding = '';
                                btn.style.borderRadius = '';
                                btn.style.fontSize = '';
                                btn.style.fontWeight = '';
                                btn.style.boxShadow = '';
                                
                                document.removeEventListener('keydown', handleEscape);
                                delete container._escapeHandler;
                            }
                        };
                        // 将函数存储在容器对象的自定义属性上，而不是dataset（dataset只能存字符串）
                        container._escapeHandler = handleEscape;
                        document.addEventListener('keydown', handleEscape);
                    }
                } catch (e) {
                    console.error('全屏错误:', e);
                    alert('全屏功能出错: ' + e.message);
                }
                return [];
            }
            """
        )
        
        output_fullscreen_btn.click(
            fn=toggle_output_fullscreen,
            inputs=[],
            outputs=[],
            js="""
            () => {
                console.log('Gradio输出全屏按钮被点击');
                try {
                    const btn = document.getElementById('output_fullscreen_btn');
                    if (!btn) {
                        console.error('未找到输出全屏按钮');
                        return [];
                    }
                    
                    // 查找视频元素 - 改进查找逻辑
                    let video = null;
                    let container = null;
                    
                    // 方法1: 从按钮所在的列查找
                    const column = btn.closest('.gradio-column');
                    if (column) {
                        video = column.querySelector('video');
                        if (video) {
                            // 查找包含video的Gradio视频组件容器
                            container = video.closest('[class*="video"]') || video.closest('.gradio-column') || video.parentElement;
                        }
                    }
                    
                    // 方法2: 如果方法1失败，查找所有视频中的第二个（输出视频）
                    if (!video) {
                        const allVideos = document.querySelectorAll('video');
                        if (allVideos.length > 1) {
                            // 找到第二个可见的视频（输出视频）
                            for (let i = 1; i < allVideos.length; i++) {
                                const v = allVideos[i];
                                const rect = v.getBoundingClientRect();
                                if (rect.width > 0 && rect.height > 0) {
                                    video = v;
                                    container = v.closest('[class*="video"]') || v.closest('.gradio-column') || v.parentElement;
                                    break;
                                }
                            }
                        } else if (allVideos.length === 1) {
                            // 只有一个视频，使用它
                            video = allVideos[0];
                            container = video.closest('[class*="video"]') || video.closest('.gradio-column') || video.parentElement;
                        }
                    }
                    
                    if (!video || !container) {
                        console.error('未找到视频元素或容器');
                        alert('未找到视频，请先上传视频');
                        return [];
                    }
                    
                    console.log('找到视频和容器:', video, container);
                    
                    // 检查是否已全屏
                    const isFullscreen = container.classList.contains('page-fullscreen-video');
                    
                    if (isFullscreen) {
                        // 退出全屏
                        console.log('退出全屏');
                        container.classList.remove('page-fullscreen-video');
                        document.body.classList.remove('page-fullscreen-active');
                        document.body.style.overflow = '';
                        document.documentElement.style.overflow = '';
                        btn.textContent = '⛶ 页面全屏';
                        
                        // 恢复按钮到视频容器内（而不是原来的父元素）
                        // 查找视频容器（video-container-wrapper或包含video的容器）
                        let videoContainer = null;
                        const video = container.querySelector('video');
                        if (video) {
                            // 查找包含video的容器
                            videoContainer = video.closest('.video-container-wrapper') || 
                                          video.closest('[class*="video"]') || 
                                          video.parentElement;
                        }
                        
                        // 如果找到了视频容器，将按钮移动到容器内
                        if (videoContainer && videoContainer !== btn.parentElement) {
                            videoContainer.appendChild(btn);
                            // 确保容器是相对定位
                            const containerStyle = getComputedStyle(videoContainer);
                            if (containerStyle.position === 'static') {
                                videoContainer.style.position = 'relative';
                            }
                        }
                        
                        // 恢复按钮样式为绝对定位（在视频容器内）
                        btn.style.position = 'absolute';
                        btn.style.top = '10px';
                        btn.style.left = '10px';
                        btn.style.zIndex = '10000';
                        btn.style.display = 'block';
                        btn.style.visibility = 'visible';
                        btn.style.opacity = '1';
                        btn.style.pointerEvents = 'auto';
                        btn.style.cursor = 'pointer';
                        
                        // 清除全屏相关的内联样式（保留基本样式，让CSS接管）
                        btn.style.background = '';
                        btn.style.color = '';
                        btn.style.border = '';
                        btn.style.padding = '';
                        btn.style.borderRadius = '';
                        btn.style.fontSize = '';
                        btn.style.fontWeight = '';
                        btn.style.boxShadow = '';
                        
                        // 移除ESC键监听
                        if (container._escapeHandler) {
                            document.removeEventListener('keydown', container._escapeHandler);
                            delete container._escapeHandler;
                        }
                        
                        // 延迟调用positionButtonOnVideo确保DOM已更新
                        setTimeout(() => {
                            if (typeof positionButtonOnVideo === 'function') {
                                positionButtonOnVideo(btn.id);
                            }
                        }, 100);
                    } else {
                        // 进入全屏
                        console.log('进入全屏');
                        
                        // 保存按钮的原始父元素和位置信息（在移动之前）
                        if (!container.dataset.originalBtnParent) {
                            container.dataset.originalBtnParent = JSON.stringify({
                                parentId: btn.parentElement ? btn.parentElement.id : '',
                                parentClass: btn.parentElement ? btn.parentElement.className : '',
                                nextSibling: btn.nextElementSibling ? btn.nextElementSibling.id || btn.nextElementSibling.className : null,
                                position: getComputedStyle(btn).position,
                                top: getComputedStyle(btn).top,
                                left: getComputedStyle(btn).left,
                                zIndex: getComputedStyle(btn).zIndex
                            });
                        }
                        
                        // 关键：将按钮移动到body下，确保不被隐藏
                        // 这样按钮就不会被 body.page-fullscreen-active > *:not(.page-fullscreen-video) 规则影响
                        if (btn.parentElement !== document.body) {
                            document.body.appendChild(btn);
                        }
                        
                        // 添加全屏样式
                        container.classList.add('page-fullscreen-video');
                        document.body.classList.add('page-fullscreen-active');
                        document.body.style.overflow = 'hidden';
                        document.documentElement.style.overflow = 'hidden';
                        btn.textContent = '✕ 退出全屏';
                        
                        // 设置按钮样式（确保在全屏时可见）
                        btn.style.position = 'fixed';
                        btn.style.top = '20px';
                        btn.style.left = '20px';
                        btn.style.zIndex = '1000000';
                        btn.style.display = 'block';
                        btn.style.visibility = 'visible';
                        btn.style.opacity = '1';
                        btn.style.pointerEvents = 'auto';
                        btn.style.cursor = 'pointer';
                        btn.style.background = 'rgba(0, 0, 0, 0.85)';
                        btn.style.color = 'white';
                        btn.style.border = '2px solid rgba(255, 255, 255, 0.9)';
                        btn.style.padding = '8px 16px';
                        btn.style.borderRadius = '4px';
                        btn.style.fontSize = '14px';
                        btn.style.fontWeight = 'bold';
                        btn.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.6)';
                        
                        // ESC键退出全屏
                        const handleEscape = (e) => {
                            if (e.key === 'Escape' && container.classList.contains('page-fullscreen-video')) {
                                container.classList.remove('page-fullscreen-video');
                                document.body.classList.remove('page-fullscreen-active');
                                document.body.style.overflow = '';
                                document.documentElement.style.overflow = '';
                                btn.textContent = '⛶ 页面全屏';
                                
                                // 恢复按钮到视频容器内
                                let videoContainer = null;
                                const video = container.querySelector('video');
                                if (video) {
                                    videoContainer = video.closest('.video-container-wrapper') || 
                                                  video.closest('[class*="video"]') || 
                                                  video.parentElement;
                                }
                                
                                if (videoContainer && videoContainer !== btn.parentElement) {
                                    videoContainer.appendChild(btn);
                                    const containerStyle = getComputedStyle(videoContainer);
                                    if (containerStyle.position === 'static') {
                                        videoContainer.style.position = 'relative';
                                    }
                                }
                                
                                btn.style.position = 'absolute';
                                btn.style.top = '10px';
                                btn.style.left = '10px';
                                btn.style.zIndex = '10000';
                                btn.style.display = 'block';
                                btn.style.visibility = 'visible';
                                btn.style.opacity = '1';
                                btn.style.pointerEvents = 'auto';
                                btn.style.cursor = 'pointer';
                                btn.style.background = '';
                                btn.style.color = '';
                                btn.style.border = '';
                                btn.style.padding = '';
                                btn.style.borderRadius = '';
                                btn.style.fontSize = '';
                                btn.style.fontWeight = '';
                                btn.style.boxShadow = '';
                                
                                setTimeout(() => {
                                    if (typeof positionButtonOnVideo === 'function') {
                                        positionButtonOnVideo(btn.id);
                                    }
                                }, 100);
                                
                                document.removeEventListener('keydown', handleEscape);
                                delete container._escapeHandler;
                            }
                        };
                        // 将函数存储在容器对象的自定义属性上，而不是dataset（dataset只能存字符串）
                        container._escapeHandler = handleEscape;
                        document.addEventListener('keydown', handleEscape);
                    }
                } catch (e) {
                    console.error('全屏错误:', e);
                    alert('全屏功能出错: ' + e.message);
                }
                return [];
            }
            """
        )

    return demo


def main():
    print("🎬 启动音视频翻译 Web UI - 演示版...")
    print("⚠️  注意：此界面仅用于演示，不包含实际翻译功能")
    print(f"🌐 访问地址: http://0.0.0.0:7862")
    demo = create_interface()
    print("🌐 启动 Web 服务...")
    demo.launch(server_name="0.0.0.0", server_port=7862, share=False)


if __name__ == "__main__":
    main()
