#!/usr/bin/env python3
"""
音视频翻译 Web UI - 模型预加载版（媒体化入口）
"""

import os
import sys
import json
import time
import tempfile
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, "src"))

import gradio as gr
import argparse
import pandas as pd
from src.segment_webui_editor import (
    generate_segments_table_html,
    load_segments_for_editing,
    merge_selected_segments,
    split_segment_func,
    delete_selected_segments,
    add_new_segment,
    save_segments_and_continue as save_segments_editor,
    convert_table_to_segments,
    convert_dataframe_to_table_data,
    # Gradio 包装函数
    parse_segment_indices_from_input,
    load_segments_for_editing_wrapper,
    merge_segments_wrapper,
    split_segments_wrapper,
    show_split_dialog_wrapper,
    on_split_method_change,
    delete_segments_wrapper,
    add_segment_wrapper,
    apply_auto_split_wrapper
)

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 解析命令行参数
parser = argparse.ArgumentParser(
    description="Media Translation WebUI with Model Preloading",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
)
parser.add_argument("--verbose", action="store_true", default=False, help="Enable verbose mode")
parser.add_argument("--port", type=int, default=7861, help="Port to run the web UI on")
parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to run the web UI on")
parser.add_argument("--output-dir", type=str, default="data/outputs", help="Output directory for translated outputs")
parser.add_argument("--preload-models", action="store_true", default=True, help="Preload models on startup")
parser.add_argument("--async-preload", action="store_true", default=True, help="Use async model preloading")
cmd_args = parser.parse_args()

# 创建输出目录
os.makedirs(cmd_args.output_dir, exist_ok=True)
os.makedirs("data/temp", exist_ok=True)

# 支持的语言列表
LANGUAGES = {
    "中文": "zh",
    "English": "en"
}

# 全局模型预加载器
model_preloader = None

# 将预加载器设置为全局可访问
os.environ['VOICE_CLONE_PRELOADER_AVAILABLE'] = 'false'


def preload_models():
    """预加载所有模型"""
    global model_preloader
    logger.info("🚀 开始预加载模型...")
    try:
        from src.model_preloader import ModelPreloader
        model_preloader = ModelPreloader()
        success = model_preloader.preload_all_models(async_loading=cmd_args.async_preload)
        if success:
            logger.info("✅ 所有模型预加载完成！")
            os.environ['VOICE_CLONE_PRELOADER_AVAILABLE'] = 'true'
            with open('/tmp/voice_clone_preloader_available', 'w') as f:
                f.write('true')
            import sys as _sys
            _sys.modules['__main__'].model_preloader = model_preloader
        else:
            failed_models = model_preloader.get_failed_models()
            logger.warning(f"⚠️ 部分模型预加载失败: {failed_models}")
        return success
    except Exception as e:
        logger.error(f"❌ 模型预加载失败: {e}")
        return False


def translate_media_interface(
    input_media_path,
    source_language,
    target_language,
    input_mode,
    single_speaker=False,
    progress=None,
    enable_segment_editing=False,
    enable_editing=True
):
    """
    媒体（音视频）翻译接口函数
    返回: (final_video_path | None, final_audio_path | None, status_msg, task_dir | None, translation_file | None, segments_file | None)
    """
    if input_media_path is None:
        return None, None, "请先上传媒体文件", None, None, None
    try:
        if progress:
            progress(0.1, desc="开始处理...")
        timestamp = int(time.time())
        output_filename = f"translated_{timestamp}.mp4"
        output_path = os.path.join(cmd_args.output_dir, output_filename)
        from media_translation_cli import translate_media
        if progress:
            progress(0.1, desc="开始翻译...")
        source_code = LANGUAGES.get(source_language, source_language)
        target_code = LANGUAGES.get(target_language, target_language)
        
        # 如果启用分段编辑功能，需要在步骤4后暂停
        pause_after_step4 = enable_segment_editing
        # 如果启用翻译编辑功能，需要在步骤5后暂停
        pause_after_step5 = enable_editing
        
        result = translate_media(
            input_path=input_media_path,
            source_lang=source_code,
            target_lang=target_code,
            output_dir=cmd_args.output_dir,
            voice_model="index-tts2",
            single_speaker=single_speaker,
            pause_after_step4=pause_after_step4,
            pause_after_step5=pause_after_step5,
            webui_mode=True
        )
        
        # 检查是否因为暂停而返回（步骤4完成但未完成全部）
        if result and result.get("needs_segment_editing"):
            task_dir = result.get("task_dir")
            segments_file = result.get("segments_file")
            if task_dir and segments_file:
                return None, None, "步骤4完成，请编辑分段", task_dir, None, segments_file
        
        # 检查是否因为暂停而返回（步骤5完成但未完成全部）
        if result and result.get("needs_editing"):
            task_dir = result.get("task_dir")
            translation_file = result.get("translation_file")
            if task_dir and translation_file:
                return None, None, "步骤5完成，请编辑翻译结果", task_dir, translation_file, None
        import glob
        if result and result.get("success"):
            if progress:
                progress(1.0, desc="翻译完成!")
            task_dir = result.get("task_dir")
            translation_file = result.get("translation_file")
            final_video_path = result.get("final_video_path")
            final_audio_path = result.get("final_audio_path")
            total_time = result.get("total_time")
            time_text = f"耗时: {total_time:.1f}秒" if isinstance(total_time, (int, float)) else ""
            if input_mode == "视频":
                if final_video_path and os.path.exists(final_video_path):
                    return final_video_path, None, f"翻译完成！{time_text}", task_dir, translation_file, None
                if task_dir:
                    candidate = os.path.join(task_dir, "09_translated.mp4")
                    if os.path.exists(candidate):
                        return candidate, None, f"翻译完成！{time_text}", task_dir, translation_file, None
                    video_files = sorted(glob.glob(os.path.join(task_dir, "*.mp4")), key=os.path.getmtime, reverse=True)
                    if video_files:
                        return video_files[0], None, f"翻译完成！{time_text}", task_dir, translation_file, None
                input_filename = os.path.basename(input_media_path)
                base_name = os.path.splitext(input_filename)[0]
                expected_output_file = f"{base_name}_translated.mp4"
                expected_output_path = os.path.join(cmd_args.output_dir, expected_output_file)
                if os.path.exists(expected_output_path):
                    return expected_output_path, None, f"翻译完成！{time_text}", task_dir, translation_file, None
                return None, None, "翻译完成，但未找到生成的视频文件", task_dir, translation_file, None
            # 音频模式
            if final_audio_path and os.path.exists(final_audio_path):
                return None, final_audio_path, f"翻译完成！{time_text}", task_dir, translation_file, None
            def find_audio_in_dir(directory: str):
                if not directory or not os.path.isdir(directory):
                    return None
                p1 = os.path.join(directory, "09_translated.wav")
                if os.path.exists(p1):
                    return p1
                p2 = os.path.join(directory, "08_final_voice.wav")
                if os.path.exists(p2):
                    return p2
                wavs = sorted(glob.glob(os.path.join(directory, "*.wav")), key=os.path.getmtime, reverse=True)
                if wavs:
                    return wavs[0]
                return None
            audio_path = find_audio_in_dir(task_dir) if task_dir else None
            if audio_path and os.path.exists(audio_path):
                return None, audio_path, f"翻译完成！{time_text}", task_dir, translation_file, None
            try:
                subdirs = [os.path.join(cmd_args.output_dir, d) for d in os.listdir(cmd_args.output_dir)]
                subdirs = [d for d in subdirs if os.path.isdir(d)]
                subdirs.sort(key=os.path.getmtime, reverse=True)
                for d in subdirs:
                    audio_path = find_audio_in_dir(d)
                    if audio_path and os.path.exists(audio_path):
                        return None, audio_path, f"翻译完成！{time_text}", task_dir, translation_file, None
            except Exception:
                pass
                return None, None, "翻译完成，但未找到生成的音频文件", task_dir, translation_file, None
        else:
            return None, None, "翻译失败，请检查输入文件", None, None, None
    except Exception as e:
        logger.error(f"翻译过程中出错: {e}")
        return None, None, f"翻译失败：{str(e)}", None, None, None


def create_interface():
    with gr.Blocks(
        title="音视频翻译系统 - 模型预加载版",
        theme=gr.themes.Soft(),
        css="""
        .gradio-container { max-width: 1200px !important; }
        .video-container { display: flex; gap: 20px; align-items: flex-start; }
        .video-item { flex: 1; }
        .model-status-box { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 10px; margin: 10px 0; font-family: 'Courier New', monospace; font-size: 12px; }
        .status-loading { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .status-success { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
        .status-error { background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }
        /* 分段表格复选框样式 - 强制显示 */
        .segment-checkbox-cell {
            text-align: center !important;
            padding: 8px !important;
            font-size: 0 !important;
            line-height: 0 !important;
            position: relative !important;
            min-width: 40px !important;
            width: auto !important;
        }
        /* 确保复选框单元格中的任何文本都被隐藏，但复选框本身可见 */
        .segment-checkbox-cell *:not(input[type="checkbox"]) {
            font-size: 0 !important;
            display: none !important;
        }
        .segment-checkbox-cell input[type="checkbox"],
        td.segment-checkbox-cell input[type="checkbox"],
        table td.segment-checkbox-cell input[type="checkbox"] {
            width: 20px !important;
            height: 20px !important;
            min-width: 20px !important;
            min-height: 20px !important;
            cursor: pointer !important;
            margin: 0 auto !important;
            display: block !important;
            position: relative !important;
            z-index: 100 !important;
            opacity: 1 !important;
            visibility: visible !important;
            -webkit-appearance: checkbox !important;
            appearance: checkbox !important;
            font-size: initial !important;
            background: transparent !important;
            border: 1px solid #666 !important;
            border-radius: 3px !important;
        }
        /* 隐藏selected_indices_sync Textbox（通过CSS隐藏，但保持visible=True以确保Gradio传递值） */
        #selected_indices_sync,
        #selected_indices_sync *,
        [id*="selected_indices_sync"] {
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            width: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            border: none !important;
            opacity: 0 !important;
            position: absolute !important;
            left: -9999px !important;
            overflow: hidden !important;
        }
        /* 确保复选框在选中状态下也可见 */
        .segment-checkbox-cell input[type="checkbox"]:checked {
            background-color: #4CAF50 !important;
            border-color: #4CAF50 !important;
        }
        /* 覆盖Gradio可能隐藏复选框的样式 */
        table td.segment-checkbox-cell,
        .gradio-dataframe td.segment-checkbox-cell {
            font-size: 0 !important;
        }
        table td.segment-checkbox-cell input[type="checkbox"],
        .gradio-dataframe td.segment-checkbox-cell input[type="checkbox"] {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
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
            
            console.log('[SegmentCheckbox] 复选框同步脚本开始加载...');
            
            // 同步复选框状态到Gradio State
            function syncCheckboxStates() {
                const container = document.getElementById('segment-checkboxes-container');
                if (!container) {
                        return;
                    }
                    
                const checkboxes = container.querySelectorAll('input[type="checkbox"]');
                const states = Array.from(checkboxes).map(cb => cb.checked);
                
                // 查找对应的Gradio State组件（通过查找包含segment_checkboxes_state的组件）
                // 由于State组件没有直接的DOM表示，我们通过触发一个自定义事件
                // 或者通过查找最近的gradio组件来更新
                console.log('[SegmentCheckbox] 当前复选框状态:', states);
                    
                // 触发自定义事件，让Gradio能够捕获
                const event = new CustomEvent('segmentCheckboxChange', {
                    detail: { states: states },
                    bubbles: true
                });
                container.dispatchEvent(event);
            }
            
            // 监听复选框变化
            function setupCheckboxListeners() {
                const container = document.getElementById('segment-checkboxes-container');
                if (!container) {
                    setTimeout(setupCheckboxListeners, 500);
                        return;
                    }
                    
                // 为所有复选框添加change事件监听
                const checkboxes = container.querySelectorAll('input[type="checkbox"]');
                checkboxes.forEach((checkbox, index) => {
                    checkbox.addEventListener('change', function() {
                        console.log(`[SegmentCheckbox] 复选框 ${index} 状态改变: ${this.checked}`);
                        syncCheckboxStates();
                        });
                });
                        
                console.log(`[SegmentCheckbox] ✅ 已为 ${checkboxes.length} 个复选框添加监听器`);
            }
            
            // 监听容器变化（当复选框HTML更新时）
            function observeCheckboxContainer() {
                const observer = new MutationObserver((mutations) => {
                    let shouldUpdate = false;
                    mutations.forEach((mutation) => {
                        if (mutation.type === 'childList') {
                                        shouldUpdate = true;
                        }
                    });
                    
                    if (shouldUpdate) {
                        console.log('[SegmentCheckbox] 检测到复选框容器变化，重新设置监听器...');
                        setTimeout(setupCheckboxListeners, 100);
                    }
                });
                
                const container = document.getElementById('segment-checkboxes-container');
                if (container) {
                    observer.observe(container, {
                    childList: true,
                        subtree: true
                });
                console.log('[SegmentCheckbox] MutationObserver已启动');
                } else {
                    setTimeout(observeCheckboxContainer, 500);
                }
            }
            
            // 初始化
            function initialize() {
                console.log('[SegmentCheckbox] 开始初始化...');
                setupCheckboxListeners();
                observeCheckboxContainer();
                console.log('[SegmentCheckbox] 初始化完成');
            }
            
            // 开始初始化
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', initialize);
            } else {
                initialize();
            }
            
            // 也监听load事件
            window.addEventListener('load', () => {
                setTimeout(initialize, 500);
            });
            
            // 定期检查并设置监听器（防止复选框被重新渲染）
            setInterval(() => {
                const container = document.getElementById('segment-checkboxes-container');
                if (container) {
                    const checkboxes = container.querySelectorAll('input[type="checkbox"]');
                    checkboxes.forEach((checkbox) => {
                        if (!checkbox.hasAttribute('data-listener-attached')) {
                            checkbox.setAttribute('data-listener-attached', 'true');
                            checkbox.addEventListener('change', syncCheckboxStates);
                                }
                            });
                        }
            }, 1000);
            
            // 同步复选框容器与表格的滚动
            function syncScroll() {
                const container = document.getElementById('segment-checkboxes-container');
                if (!container) return;
                
                // 查找表格容器
                const labels = document.querySelectorAll('label');
                let tableContainer = null;
                labels.forEach(label => {
                    if (label.textContent.includes('分段列表')) {
                        let parent = label.parentElement;
                        while (parent && parent !== document.body) {
                            if (parent.querySelector('.gradio-dataframe')) {
                                tableContainer = parent.querySelector('.gradio-dataframe');
                                break;
                            }
                            parent = parent.parentElement;
                        }
                    }
                });
                
                if (tableContainer) {
                    const table = tableContainer.querySelector('table');
                    if (table) {
                        // 同步滚动
                        tableContainer.addEventListener('scroll', function() {
                            container.scrollTop = tableContainer.scrollTop;
                        });
                
                        // 确保复选框容器的高度与表格一致
                        const observer = new MutationObserver(() => {
                            if (tableContainer.scrollHeight > 0) {
                                container.style.height = tableContainer.scrollHeight + 'px';
            }
                        });
                        observer.observe(tableContainer, { childList: true, subtree: true, attributes: true });
                    }
                }
            }
            
            // 初始化滚动同步
            setTimeout(syncScroll, 1000);
            setInterval(syncScroll, 2000);
        })();
        </script>
        ''')
        
        # 注意：复选框状态通过HTML中的JavaScript同步，Python端在操作时从State读取

        with gr.Row():
            with gr.Column(scale=1):
                with gr.Group():
                    gr.Markdown("### 上传文件")
                    input_mode = gr.Radio(choices=["视频", "音频"], value="视频", label="输入类型")
                    input_video = gr.Video(label=" ", height=300, format="mp4", visible=True)
                    input_audio = gr.Audio(label=" ", sources=["upload"], type="filepath", interactive=True, visible=False)
                    file_info = gr.Textbox(label="文件信息", value="请上传媒体文件（视频或音频）...", interactive=False, lines=3)
                    current_media = gr.State(value=None)

            with gr.Column(scale=1):
                with gr.Group():
                    gr.Markdown("### 翻译设置")
                    with gr.Row():
                        source_language = gr.Dropdown(choices=list(LANGUAGES.keys()), value="中文", label="源语言", interactive=False)
                        target_language = gr.Dropdown(choices=list(LANGUAGES.keys()), value="English", label="目标语言", interactive=False)
                    single_speaker = gr.Checkbox(label="仅一人说话", value=True, interactive=True)
                    enable_segment_editing = gr.Checkbox(
                        label="步骤4后暂停编辑分段（勾选后，步骤4完成时会暂停，允许您手动调整分段后再继续）", 
                        value=True, 
                        interactive=True
                    )
                    enable_editing = gr.Checkbox(
                        label="步骤5后暂停编辑翻译结果（勾选后，步骤5完成时会暂停，允许您手动编辑翻译结果后再继续）", 
                        value=True, 
                        interactive=True
                    )
                    translate_btn = gr.Button("🚀 开始翻译", variant="primary", size="lg", scale=1, interactive=False)
                    status_text = gr.Textbox(label="处理状态", value="等待上传媒体...", interactive=False, lines=4)

            with gr.Column(scale=1):
                with gr.Group():
                    gr.Markdown("### 翻译结果")
                    output_video = gr.Video(label=" ", height=300, format="mp4", visible=True)
                    output_audio = gr.Audio(label=" ", type="filepath", interactive=False, visible=False)
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
        
        # 刷新模型状态
        def refresh_model_status():
            """从预加载器获取真实的模型状态"""
            global model_preloader
            if model_preloader is None:
                # 如果预加载器不存在，尝试获取
                try:
                    from src.model_preloader import ModelPreloader
                    model_preloader = ModelPreloader.get_instance()
                except Exception as e:
                    logger.error(f"无法获取模型预加载器: {e}")
                    return "⏸️ 未初始化", "⏸️ 未初始化", "⏸️ 未初始化", "⏸️ 未初始化", "⏸️ 未初始化"
            
            # 获取模型状态
            statuses = model_preloader.get_model_statuses()
            
            index_tts = get_model_status_display(statuses.get("IndexTTS2", {}).get("status", "未加载"))
            whisper = get_model_status_display(statuses.get("Whisper", {}).get("status", "未加载"))
            audio_sep = get_model_status_display(statuses.get("AudioSeparator", {}).get("status", "未加载"))
            text_trans = get_model_status_display(statuses.get("TextTranslator", {}).get("status", "未加载"))
            speaker_dia = get_model_status_display(statuses.get("SpeakerDiarizer", {}).get("status", "未加载"))
            
            return index_tts, whisper, audio_sep, text_trans, speaker_dia
        
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

        def detect_and_set_language(file_path: str):
            if not file_path or not os.path.exists(file_path):
                return (
                    gr.update(value="中文", interactive=False),
                    gr.update(value="English", interactive=False),
                    "文件不存在，请重新上传"
                )
            from src.utils import detect_language
            detected_lang_code = detect_language(file_path)
            source_lang_name = "中文" if detected_lang_code == "zh" else "English"
            target_lang_name = "English" if detected_lang_code == "zh" else "中文"
            status_msg = f"✅ 语言检测完成\n源语言: {source_lang_name}\n目标语言: {target_lang_name}\n可以开始翻译"
            return (
                gr.update(value=source_lang_name, interactive=True),
                gr.update(value=target_lang_name, interactive=True),
                status_msg
            )

        VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi"}
        AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg"}

        def on_media_upload(media, mode):
            if media is None:
                return (
                    "请上传媒体文件（视频或音频）...",
                    gr.update(value="中文", interactive=False),
                    gr.update(value="English", interactive=False),
                    gr.update(interactive=False),
                    "等待上传媒体...",
                    None
                )
            file_path = media if isinstance(media, str) else media.name
            ext = Path(file_path).suffix.lower()
            if mode == "视频" and ext not in VIDEO_EXTS:
                return (
                    f"❌ 不支持的视频格式: {ext}",
                    gr.update(value="中文", interactive=False),
                    gr.update(value="English", interactive=False),
                    gr.update(interactive=False),
                    "请更换为受支持的视频格式",
                    None
                )
            if mode == "音频" and ext not in AUDIO_EXTS:
                return (
                    f"❌ 不支持的音频格式: {ext}",
                    gr.update(value="中文", interactive=False),
                    gr.update(value="English", interactive=False),
                    gr.update(interactive=False),
                    "请更换为受支持的音频格式",
                    None
                )
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            file_name = os.path.basename(file_path)
            file_info_text = f"📁 文件名: {file_name}\n📊 文件大小: {file_size:.2f} MB\n✅ 文件已上传，可以开始翻译"
            source_update, target_update, status_text_val = detect_and_set_language(file_path)
            return (file_info_text, source_update, target_update, gr.update(interactive=True), status_text_val, file_path)

        def update_result_info(status):
            if not status:
                return "翻译完成后将显示结果..."
            if "完成" in status or "成功" in status:
                return f"✅ {status}"
            if "失败" in status or "错误" in status:
                return f"❌ {status}"
            return f"⏳ {status}"

        def disable_controls_before_translate(media, src_lang, tgt_lang, mode):
            if media is None:
                return (
                    gr.update(value=None, visible=(mode == "视频")),
                    gr.update(value=None, visible=(mode == "音频")),
                    "请先上传媒体文件",
                    "翻译完成后将显示结果...",
                    gr.update(interactive=False),
                    gr.update(interactive=False),
                    gr.update(interactive=False)
                )
            return (
                gr.update(value=None, visible=False),
                gr.update(value=None, visible=False),
                "⏳ 正在翻译，请稍候...",
                "⏳ 正在处理中...\n📝 翻译进行中，请勿关闭页面",
                gr.update(interactive=False),
                gr.update(interactive=False),
                gr.update(interactive=False)
            )

        # 翻译编辑区域（初始隐藏）
        with gr.Group(visible=False) as translation_edit_group:
            gr.Markdown("### 📝 编辑翻译结果")
            gr.Markdown("**提示**: 只能修改译文，原文和时间戳不可修改")
            
            # 使用Accordion显示每个段
            translation_segments_accordion = gr.Accordion(
                label="翻译片段",
                open=False,
                visible=False
            )
            
            # 存储所有段的编辑组件
            translation_segments_components = gr.State(value=[])
            
            # 翻译文本编辑器
            translation_editor = gr.Textbox(
                label="翻译文本",
                value="",
                lines=20,
                interactive=True,
                visible=True,
                placeholder="请等待步骤5完成..."
            )
            
            save_and_continue_btn = gr.Button("💾 保存并继续", variant="primary", size="lg")
            edit_status = gr.Textbox(label="编辑状态", value="", interactive=False, lines=2)
        
        
        # 分段编辑区域（初始隐藏）
        with gr.Group(visible=False) as segment_edit_group:
            gr.Markdown("### 📝 编辑分段")
            gr.Markdown("**提示**: 可以直接在表格中编辑时间戳和文本，或使用下方按钮进行操作")
            
            # 原始媒体播放器
            segment_media_player = gr.Audio(label="原始音频", type="filepath", visible=False)
            segment_video_player = gr.Video(label="原始视频", visible=False)
            
            # 表格数据State（维护表格的实际数据，因为HTML表格是只读的）
            segments_table_data_state = gr.State(value=[])  # 存储表格数据（字典列表）
            
            # 选中的分段索引State（复选框列和其他列一样处理）
            selected_segment_indices = gr.State(value=[])  # 存储选中的行索引列表
            
            # 分段表格显示（使用Gradio Dataframe，支持直接编辑）
            segments_table_dataframe = gr.Dataframe(
                label="分段列表（可直接编辑时间戳和文本）",
                headers=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"],
                datatype=["number", "number", "number", "str", "str"],
                interactive=True,
                wrap=True,
                visible=True
            )
            
            # 操作区域
            with gr.Row():
                with gr.Column(scale=1):
                    merge_segments_input = gr.Textbox(
                        label="合并分段（输入分段编号，用逗号分隔，如：12,13）",
                        placeholder="例如：12,13",
                        value="",
                        interactive=True
                    )
                    merge_segments_btn = gr.Button("🔗 合并分段", variant="primary")
                
                with gr.Column(scale=1):
                    apply_auto_split_btn = gr.Button("⚡ 应用拆分（检测换行符）", variant="secondary")
                
                with gr.Column(scale=1):
                    delete_segments_input = gr.Textbox(
                        label="删除分段（输入分段编号，用逗号分隔，如：12,13）",
                        placeholder="例如：12,13",
                        value="",
                        interactive=True
                    )
                delete_segment_btn = gr.Button("🗑️ 删除分段", variant="secondary")
                
                with gr.Column(scale=1):
                    add_segment_btn = gr.Button("➕ 添加分段", variant="secondary")
            
            # 拆分分段对话框
            with gr.Group(visible=False) as split_dialog:
                gr.Markdown("### 拆分分段")
                split_method = gr.Radio(
                    choices=["按时间点拆分", "按文本位置拆分"],
                    value="按时间点拆分",
                    label="拆分方式"
                )
                split_text_display = gr.HTML(
                    value="",
                    label="分段文本内容（点击文本选择拆分位置）",
                    visible=False
                )
                split_time_input = gr.Number(
                    label="拆分时间点（秒）",
                    value=0.0,
                    visible=True
                )
                split_text_position_input = gr.Textbox(
                    label="拆分文本（输入要查找的文本片段）",
                    value="",
                    placeholder="输入文本片段，系统会在该文本之后拆分",
                    visible=False,
                    lines=2
                )
                split_confirm_btn = gr.Button("确认拆分", variant="primary")
                split_cancel_btn = gr.Button("取消", variant="secondary")
            
            # 添加分段对话框
            with gr.Group(visible=False) as add_dialog:
                gr.Markdown("### 添加新分段")
                add_start_time = gr.Number(label="开始时间（秒）", value=0.0)
                add_end_time = gr.Number(label="结束时间（秒）", value=0.0)
                add_text = gr.Textbox(label="文本内容", lines=3)
                add_confirm_btn = gr.Button("确认添加", variant="primary")
                add_cancel_btn = gr.Button("取消", variant="secondary")
            
            # 分段JSON编辑器（高级用户，默认折叠）
            with gr.Accordion("高级选项：JSON编辑器", open=False):
                segments_json_editor = gr.Textbox(
                    label="分段数据（JSON格式）",
                    value="",
                    lines=20,
                    interactive=True,
                    visible=True,
                    placeholder="请等待步骤4完成..."
                )
            
            # 当前选中的分段索引（State）
            selected_segment_indices = gr.State(value=[])
            segments_data = gr.State(value=[])  # 存储完整的segments数据
            
            save_segments_and_continue_btn = gr.Button("💾 保存并继续", variant="primary", size="lg")
            segment_edit_status = gr.Textbox(label="编辑状态", value="", interactive=False, lines=2)
        
        # 保存任务目录和文件路径的状态
        task_dir_state = gr.State(value=None)
        translation_file_state = gr.State(value=None)
        segments_file_state = gr.State(value=None)
        
        def load_translation_for_editing(task_dir_val, translation_file_val):
            """加载翻译文件用于编辑"""
            # 如果参数为 None，说明不需要编辑，直接静默返回（这是正常情况，不需要记录警告）
            if not task_dir_val or not translation_file_val:
                return (
                    gr.update(value="", visible=False),
                    gr.update(visible=False),
                    ""
                )
            
            import time
            start_time = time.time()
            logger.info(f"[load_translation_for_editing] 开始加载翻译文件，task_dir: {task_dir_val}, translation_file: {translation_file_val}")
            
            # 检查翻译文件是否存在
            if not os.path.exists(translation_file_val):
                error_msg = f"❌ 翻译文件不存在: {translation_file_val}"
                logger.error(f"[load_translation_for_editing] {error_msg}")
                return (
                    gr.update(value="", visible=False),
                    gr.update(visible=False),
                    error_msg
                )
            
            try:
                # 读取翻译文件和原始segments
                from src.output_manager import OutputManager, StepNumbers
                import json
                import re
                
                # 步骤1: 读取翻译文件
                step1_start = time.time()
                try:
                    with open(translation_file_val, 'r', encoding='utf-8') as f:
                        translation_content = f.read()
                    step1_time = time.time() - step1_start
                    logger.info(f"[load_translation_for_editing] 步骤1-读取翻译文件完成，耗时: {step1_time:.3f}秒，文件大小: {len(translation_content)} 字符")
                except Exception as e:
                    error_msg = f"❌ 读取翻译文件失败: {str(e)}"
                    logger.error(f"[load_translation_for_editing] {error_msg}", exc_info=True)
                    return (
                        gr.update(value="", visible=False),
                        gr.update(visible=False),
                        error_msg
                    )
                
                # 步骤2: 读取原始segments（可选，用于验证）
                step2_start = time.time()
                output_manager = OutputManager("", cmd_args.output_dir)
                output_manager.task_dir = task_dir_val
                segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
                
                if not os.path.exists(segments_json_file):
                    # 如果找不到原始segments，直接使用简单文本编辑器
                    step2_time = time.time() - step2_start
                    logger.warning(f"[load_translation_for_editing] 步骤2-未找到原始segments文件: {segments_json_file}，耗时: {step2_time:.3f}秒，使用简单编辑器")
                    return (
                        gr.update(value=translation_content, visible=True),
                        gr.update(visible=True),
                        "⚠️ 未找到原始segments，使用简单编辑器\n✅ 翻译文件已加载，请只修改译文部分，不要修改原文和时间戳"
                    )
                
                try:
                    with open(segments_json_file, 'r', encoding='utf-8') as f:
                        original_segments = json.load(f)
                    step2_time = time.time() - step2_start
                    logger.info(f"[load_translation_for_editing] 步骤2-读取原始segments完成，耗时: {step2_time:.3f}秒，分段数量: {len(original_segments)}")
                except Exception as e:
                    logger.warning(f"[load_translation_for_editing] 读取原始segments失败: {e}，使用简单编辑器")
                    return (
                        gr.update(value=translation_content, visible=True),
                        gr.update(visible=True),
                        "⚠️ 读取原始segments失败，使用简单编辑器\n✅ 翻译文件已加载，请只修改译文部分，不要修改原文和时间戳"
                    )
                
                # 步骤3: 解析翻译文件
                step3_start = time.time()
                pattern = r'Segment\s+(\d+)\s+\(([\d.]+)s\s+-\s+([\d.]+)s\):\s*\n原文:\s*(.+?)\s*\n译文:\s*(.+?)(?=\n\n|$)'
                matches = re.findall(pattern, translation_content, re.DOTALL)
                step3_time = time.time() - step3_start
                logger.info(f"[load_translation_for_editing] 步骤3-解析翻译文件完成，耗时: {step3_time:.3f}秒，匹配到 {len(matches)} 个片段，原始分段数: {len(original_segments)}")
                
                if len(matches) != len(original_segments):
                    # 如果解析失败，使用简单文本编辑器
                    warning_msg = f"⚠️ 解析结果不匹配（匹配到 {len(matches)} 个片段，原始分段 {len(original_segments)} 个），使用简单编辑器\n✅ 翻译文件已加载，请只修改译文部分，不要修改原文和时间戳"
                    logger.warning(f"[load_translation_for_editing] {warning_msg}")
                    return (
                        gr.update(value=translation_content, visible=True),
                        gr.update(visible=True),
                        warning_msg
                    )
                
                # 步骤4: 构建显示内容（虽然最终使用简单编辑器，但保留解析逻辑用于验证）
                step4_start = time.time()
                # 注意：由于Gradio的限制，我们使用简单文本编辑器
                # 但解析成功说明格式正确，可以给用户更好的提示
                step4_time = time.time() - step4_start
                logger.info(f"[load_translation_for_editing] 步骤4-构建显示内容完成，耗时: {step4_time:.3f}秒")
                
                total_time = time.time() - start_time
                success_msg = f"✅ 翻译文件已加载，共 {len(matches)} 个片段\n⚠️ 请只修改译文部分，不要修改原文和时间戳"
                logger.info(f"[load_translation_for_editing] 全部加载完成，总耗时: {total_time:.3f}秒")
                
                return (
                    gr.update(value=translation_content, visible=True),
                    gr.update(visible=True),
                    success_msg
                )
            except Exception as e:
                error_msg = f"❌ 加载翻译文件失败: {str(e)}"
                logger.error(f"[load_translation_for_editing] {error_msg}", exc_info=True)
                import traceback
                traceback.print_exc()
                
                # 即使出错，也尝试显示翻译文件的原始内容
                try:
                    with open(translation_file_val, 'r', encoding='utf-8') as f:
                        translation_content = f.read()
                    return (
                        gr.update(value=translation_content, visible=True),
                        gr.update(visible=True),
                        f"{error_msg}\n⚠️ 已显示原始文件内容，请检查文件格式"
                    )
                except:
                    return (
                        gr.update(value="", visible=False),
                        gr.update(visible=False),
                        error_msg
                    )
        
        def save_and_continue(edited_text, task_dir_val, translation_file_val, media, src_lang, tgt_lang, mode, is_single_speaker):
            """保存编辑后的翻译并继续执行"""
            if not task_dir_val or not translation_file_val:
                return (
                    gr.update(visible=False),
                    gr.update(value=""),
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    "❌ 无法继续：缺少任务目录或翻译文件路径",
                    "❌ 无法继续：缺少任务目录或翻译文件路径"
                )
            
            try:
                from src.translation_editor import parse_translation_txt, validate_translation_data, save_translation_files
                from src.output_manager import OutputManager, StepNumbers
                import json
                
                # 读取原始segments
                output_manager = OutputManager(media, cmd_args.output_dir)
                output_manager.task_dir = task_dir_val
                segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
                
                if not os.path.exists(segments_json_file):
                    return (
                        gr.update(visible=False),
                        gr.update(value=""),
                        gr.update(value=None, visible=False),
                        gr.update(value=None, visible=False),
                        f"❌ 无法继续：原始segments文件不存在: {segments_json_file}",
                        f"❌ 无法继续：原始segments文件不存在: {segments_json_file}"
                    )
                
                with open(segments_json_file, 'r', encoding='utf-8') as f:
                    original_segments = json.load(f)
                
                # 保存编辑后的文本到文件
                with open(translation_file_val, 'w', encoding='utf-8') as f:
                    f.write(edited_text)
                
                # 解析并验证
                translated_segments = parse_translation_txt(translation_file_val, original_segments)
                is_valid, error_msg = validate_translation_data(translated_segments, original_segments)
                
                if not is_valid:
                    return (
                        gr.update(visible=True),
                        gr.update(value=f"❌ 验证失败: {error_msg}"),
                        gr.update(value=None, visible=False),
                        gr.update(value=None, visible=False),
                        f"❌ 验证失败: {error_msg}",
                        f"❌ 验证失败: {error_msg}"
                    )
                
                # 保存到JSON
                save_translation_files(translated_segments, output_manager, original_segments)
                
                # 继续执行步骤6-9
                from media_translation_cli import translate_media
                source_code = LANGUAGES.get(src_lang, src_lang)
                target_code = LANGUAGES.get(tgt_lang, tgt_lang)
                
                result = translate_media(
                    input_path=media,
                    source_lang=source_code,
                    target_lang=target_code,
                    output_dir=cmd_args.output_dir,
                    voice_model="index-tts2",
                    single_speaker=is_single_speaker,
                    continue_from_step6=True,
                    task_dir=task_dir_val,
                    webui_mode=True
                )
                
                if result and result.get("success"):
                    final_video_path = result.get("final_video_path")
                    total_time = result.get("total_time")
                    time_text = f"耗时: {total_time:.1f}秒" if isinstance(total_time, (int, float)) else ""
                    
                    # 查找输出文件（如果路径不正确）
                    task_dir_val = result.get("task_dir")
                    import glob
                    
                    if mode == "视频":
                        # 视频模式：如果 final_video_path 不存在或文件不存在，尝试查找
                        if not final_video_path or not os.path.exists(final_video_path):
                            if task_dir_val:
                                video_files = sorted(glob.glob(os.path.join(task_dir_val, "*.mp4")), key=os.path.getmtime, reverse=True)
                                if video_files:
                                    final_video_path = video_files[0]
                        
                        if final_video_path and os.path.exists(final_video_path):
                            return (
                                gr.update(visible=False),
                                gr.update(value=""),
                                gr.update(value=final_video_path, visible=True),
                                gr.update(value=None, visible=False),
                                f"✅ 翻译完成！{time_text}",
                                f"✅ 翻译完成！{time_text}"
                            )
                        else:
                            return (
                                gr.update(visible=False),
                                gr.update(value=""),
                                gr.update(value=None, visible=False),
                                gr.update(value=None, visible=False),
                                "✅ 翻译完成，但未找到输出文件",
                                "✅ 翻译完成，但未找到输出文件"
                            )
                    else:
                        # 音频模式：对于音频模式，final_video_path 实际包含音频文件路径
                        final_audio_path = final_video_path  # translate_media 返回的 final_video_path 对于音频模式实际是音频文件
                        
                        # 如果 final_audio_path 不存在或文件不存在，使用回退逻辑查找
                        if not final_audio_path or not os.path.exists(final_audio_path):
                            if task_dir_val:
                                # 优先查找 09_translated*.wav 格式的文件
                                translated_files = sorted(glob.glob(os.path.join(task_dir_val, "09_translated*.wav")), key=os.path.getmtime, reverse=True)
                                if translated_files:
                                    final_audio_path = translated_files[0]
                                else:
                                    # 其次查找 08_final_voice.wav
                                    final_voice_path = os.path.join(task_dir_val, "08_final_voice.wav")
                                    if os.path.exists(final_voice_path):
                                        final_audio_path = final_voice_path
                                    else:
                                        # 最后查找所有 .wav 文件
                                        audio_files = sorted(glob.glob(os.path.join(task_dir_val, "*.wav")), key=os.path.getmtime, reverse=True)
                                        if audio_files:
                                            final_audio_path = audio_files[0]
                        
                        if final_audio_path and os.path.exists(final_audio_path):
                            return (
                                gr.update(visible=False),
                                gr.update(value=""),
                                gr.update(value=None, visible=False),
                                gr.update(value=final_audio_path, visible=True),
                                f"✅ 翻译完成！{time_text}",
                                f"✅ 翻译完成！{time_text}"
                            )
                        else:
                            return (
                                gr.update(visible=False),
                                gr.update(value=""),
                                gr.update(value=None, visible=False),
                                gr.update(value=None, visible=False),
                                "✅ 翻译完成，但未找到输出文件",
                                "✅ 翻译完成，但未找到输出文件"
                            )
                else:
                    error_msg = result.get("error", "未知错误") if result else "翻译失败"
                    return (
                        gr.update(visible=True),
                        gr.update(value=f"❌ 继续执行失败: {error_msg}"),
                        gr.update(value=None, visible=False),
                        gr.update(value=None, visible=False),
                        f"❌ 继续执行失败: {error_msg}",
                        f"❌ 继续执行失败: {error_msg}"
                    )
                    
            except Exception as e:
                logger.error(f"保存并继续失败: {e}")
                import traceback
                traceback.print_exc()
                return (
                    gr.update(visible=True),
                    gr.update(value=f"❌ 保存并继续失败: {str(e)}"),
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    f"❌ 保存并继续失败: {str(e)}",
                    f"❌ 保存并继续失败: {str(e)}"
                )
        
        
        def load_segments_for_editing_old(task_dir_val, segments_file_val, media_path, mode):
            """加载分段文件用于编辑"""
            if not task_dir_val or not segments_file_val:
                return (
                    [],
                    "",
                    [],
                    gr.update(visible=False),
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    "无法加载分段文件"
                )
            
            try:
                from src.output_manager import OutputManager, StepNumbers
                from src.segment_editor import load_segments
                import json
                import shutil
                
                # 读取分段文件
                segments = load_segments(segments_file_val)
                
                # 保存原始segments文件（用于后续恢复和验证）
                output_manager = OutputManager(media_path, cmd_args.output_dir)
                output_manager.task_dir = task_dir_val
                original_segments_file = os.path.join(task_dir_val, "04_segments_original.json")
                if not os.path.exists(original_segments_file):
                    shutil.copy2(segments_file_val, original_segments_file)
                    logger.info(f"已保存原始分段文件: {original_segments_file}")
                
                # 转换为表格数据格式
                table_data = []
                checkbox_states = []  # 复选框状态列表
                for i, seg in enumerate(segments):
                    start_time = seg.get('start', 0.0)
                    end_time = seg.get('end', 0.0)
                    text = seg.get('text', '').strip()
                    speaker_id = seg.get('speaker_id', '')
                    
                    table_data.append({
                        'index': i,
                        'seq_num': i + 1,
                        'start_time': round(start_time, 3),
                        'end_time': round(end_time, 3),
                        'text': text,
                        'speaker': speaker_id if speaker_id else ''
                    })
                    checkbox_states.append(False)  # 初始状态为未选中
                
                # 生成包含复选框列的完整HTML表格
                def generate_segments_table_html(table_data_list, checkbox_states_list):
                    """生成包含复选框列的完整HTML表格"""
                    html = '''
                    <style>
                    .segments-table-container {
                        overflow-x: auto;
                        max-height: 600px;
                        overflow-y: auto;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                    }
                    .segments-table {
                        width: 100%;
                        border-collapse: collapse;
                        font-size: 14px;
                        background-color: white;
                    }
                    .segments-table thead {
                        background-color: #f5f5f5;
                        position: sticky;
                        top: 0;
                        z-index: 10;
                    }
                    .segments-table th {
                        padding: 12px 8px;
                        text-align: left;
                        border: 1px solid #ddd;
                        font-weight: 600;
                        white-space: nowrap;
                    }
                    .segments-table th:first-child {
                        text-align: center;
                        width: 60px;
                    }
                    .segments-table td {
                        padding: 10px 8px;
                        border: 1px solid #ddd;
                        vertical-align: top;
                    }
                    .segments-table td:first-child {
                        text-align: center;
                    }
                    .segments-table td.editable {
                        cursor: text;
                        min-width: 100px;
                    }
                    .segments-table td.editable:hover {
                        background-color: #f9f9f9;
                    }
                    .segments-table td.editable:focus {
                        background-color: #fffacd;
                        outline: 2px solid #4CAF50;
                    }
                    .segments-table input[type="checkbox"] {
                        width: 20px;
                        height: 20px;
                        cursor: pointer;
                        margin: 0;
                    }
                    .segments-table tbody tr:hover {
                        background-color: #f5f5f5;
                    }
                    </style>
                    <div class="segments-table-container">
                        <table class="segments-table">
                            <thead>
                                <tr>
                                    <th>选择</th>
                                    <th>序号</th>
                                    <th>开始时间(秒)</th>
                                    <th>结束时间(秒)</th>
                                    <th>文本内容</th>
                                    <th>说话人</th>
                                </tr>
                            </thead>
                            <tbody>'''
                    
                    for i, row in enumerate(table_data_list):
                        checked = "checked" if i < len(checkbox_states_list) and checkbox_states_list[i] else ""
                        html += f'''
                                <tr data-row-index="{i}">
                                    <td>
                                        <input type="checkbox" class="segment-checkbox" data-index="{i}" {checked}>
                                    </td>
                                    <td>{row['seq_num']}</td>
                                    <td class="editable" contenteditable="true" data-col="start_time" data-row="{i}">{row['start_time']}</td>
                                    <td class="editable" contenteditable="true" data-col="end_time" data-row="{i}">{row['end_time']}</td>
                                    <td class="editable" contenteditable="true" data-col="text" data-row="{i}">{row['text']}</td>
                                    <td class="editable" contenteditable="true" data-col="speaker" data-row="{i}">{row['speaker']}</td>
                                </tr>'''
                    
                    html += '''
                            </tbody>
                        </table>
                    </div>
                    <script>
                    (function() {
                        // 同步复选框状态到Gradio State（selected_segment_indices）
                        function syncCheckboxStates() {
                            const checkboxes = document.querySelectorAll('.segment-checkbox');
                            const selectedIndices = [];
                            checkboxes.forEach((cb, index) => {
                                if (cb.checked) {
                                    selectedIndices.push(index);
                                }
                            });
                            
                            // 通过Gradio的API更新State
                            // 注意：这里需要通过Gradio的JavaScript API来更新State
                            // 由于Gradio的限制，我们通过自定义事件通知Python端
                            const event = new CustomEvent('segmentIndicesChanged', {
                                detail: { indices: selectedIndices },
                                bubbles: true
                            });
                            document.dispatchEvent(event);
                        }
                        
                        // 监听复选框变化
                        document.addEventListener('change', function(e) {
                            if (e.target.classList.contains('segment-checkbox')) {
                                syncCheckboxStates();
                            }
                        });
                        
                        // 监听单元格编辑
                        document.addEventListener('blur', function(e) {
                            if (e.target.classList.contains('editable')) {
                                const event = new CustomEvent('segmentCellChanged', {
                                    detail: {
                                        row: parseInt(e.target.dataset.row),
                                        col: e.target.dataset.col,
                                        value: e.target.textContent.trim()
                                    },
                                    bubbles: true
                                });
                                document.dispatchEvent(event);
                            }
                        }, true);
                        
                        // 初始化时同步一次
                        setTimeout(syncCheckboxStates, 500);
                    })();
                    </script>'''
                    
                    return html
                
                # 生成HTML表格
                table_html = generate_segments_table_html(table_data, checkbox_states)
                
                # 转换为JSON字符串显示（高级选项）
                segments_json = json.dumps(segments, ensure_ascii=False, indent=2)
                
                # 优先使用提取的音频文件
                audio_file = output_manager.get_file_path(StepNumbers.STEP_1, "audio")
                if not os.path.exists(audio_file):
                    audio_file = media_path if mode == "音频" else None
                
                video_file = media_path if mode == "视频" else None
                
                return (
                    table_html,  # HTML表格
                    checkbox_states,  # 复选框状态
                    table_data,  # 表格数据State
                    segments_json,  # JSON数据
                    segments,  # 完整segments数据（用于State）
                    gr.update(visible=True),  # 保存按钮可见
                    gr.update(value=audio_file, visible=(mode == "音频" and audio_file)),  # 音频播放器
                    gr.update(value=video_file, visible=(mode == "视频" and video_file)),  # 视频播放器
                    f"✅ 分段文件已加载，共 {len(segments)} 个片段"
                )
            except Exception as e:
                logger.error(f"加载分段文件失败: {e}")
                import traceback
                traceback.print_exc()
                return (
                    "<div style='padding: 20px; text-align: center; color: #f00;'>❌ 加载分段文件失败</div>",
                    [],
                    [],
                    "",
                    [],
                    gr.update(visible=False),
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    f"❌ 加载分段文件失败: {str(e)}"
                )
        
        def convert_table_to_segments(table_data_list, original_segments):
            """将表格数据（字典列表）转换为segments格式"""
            if not table_data_list or not original_segments:
                return []
            
            new_segments = []
            for i, row in enumerate(table_data_list):
                if not isinstance(row, dict):
                    continue
                
                # 读取实际数据
                seq_num = row.get('seq_num', i + 1)
                start_time = row.get('start_time', 0.0)
                end_time = row.get('end_time', 0.0)
                text = row.get('text', '')
                speaker_id = row.get('speaker', '')
                
                # 从原始segments中获取对应的单词列表
                original_idx = int(seq_num) - 1
                if 0 <= original_idx < len(original_segments):
                    original_seg = original_segments[original_idx]
                    words = original_seg.get('words', [])
                    
                    # 根据新时间范围过滤单词
                    filtered_words = []
                    for word in words:
                        word_start = word.get('start', 0)
                        word_end = word.get('end', 0)
                        if word_start >= float(start_time) and word_end <= float(end_time):
                            filtered_words.append(word)
                    
                    # 如果过滤后没有单词，尝试从时间范围查找
                    if not filtered_words:
                        from src.segment_editor import find_words_in_time_range
                        all_words = []
                        for seg in original_segments:
                            all_words.extend(seg.get('words', []))
                        filtered_words = find_words_in_time_range(all_words, float(start_time), float(end_time))
                else:
                    # 新添加的分段，需要从所有单词中查找
                    all_words = []
                    for seg in original_segments:
                        all_words.extend(seg.get('words', []))
                    from src.segment_editor import find_words_in_time_range
                    filtered_words = find_words_in_time_range(all_words, float(start_time), float(end_time))
                
                # 构建新分段
                new_seg = {
                    'id': i,
                    'start': float(start_time),
                    'end': float(end_time),
                    'text': str(text).strip(),
                    'words': filtered_words,
                }
                
                # 保留speaker_id
                if speaker_id and str(speaker_id).strip():
                    new_seg['speaker_id'] = str(speaker_id).strip()
                elif original_idx < len(original_segments) and 'speaker_id' in original_segments[original_idx]:
                    new_seg['speaker_id'] = original_segments[original_idx]['speaker_id']
                
                new_segments.append(new_seg)
            
            return new_segments
        
        # 统一的HTML表格生成函数（供所有操作函数使用）
        def generate_segments_table_html(table_data_list, checkbox_states_list):
            """生成包含复选框列的完整HTML表格"""
            html = '''
            <style>
            .segments-table-container {
                overflow-x: auto;
                max-height: 600px;
                overflow-y: auto;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            .segments-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
                background-color: white;
            }
            .segments-table thead {
                background-color: #f5f5f5;
                position: sticky;
                top: 0;
                z-index: 10;
            }
            .segments-table th {
                padding: 12px 8px;
                text-align: left;
                border: 1px solid #ddd;
                font-weight: 600;
                white-space: nowrap;
            }
            .segments-table th:first-child {
                text-align: center;
                width: 60px;
            }
            .segments-table td {
                padding: 10px 8px;
                border: 1px solid #ddd;
                vertical-align: top;
            }
            .segments-table td:first-child {
                text-align: center;
            }
            .segments-table td.editable {
                cursor: text;
                min-width: 100px;
            }
            .segments-table td.editable:hover {
                background-color: #f9f9f9;
            }
            .segments-table td.editable:focus {
                background-color: #fffacd;
                outline: 2px solid #4CAF50;
            }
            .segments-table input[type="checkbox"] {
                width: 20px;
                height: 20px;
                cursor: pointer;
                margin: 0;
            }
            .segments-table tbody tr:hover {
                background-color: #f5f5f5;
            }
            </style>
            <div class="segments-table-container">
                <table class="segments-table">
                    <thead>
                        <tr>
                            <th>选择</th>
                            <th>序号</th>
                            <th>开始时间(秒)</th>
                            <th>结束时间(秒)</th>
                            <th>文本内容</th>
                            <th>说话人</th>
                        </tr>
                    </thead>
                    <tbody>'''
            
            for i, row in enumerate(table_data_list):
                checked = "checked" if i < len(checkbox_states_list) and checkbox_states_list[i] else ""
                html += f'''
                        <tr data-row-index="{i}">
                            <td>
                                <input type="checkbox" class="segment-checkbox" data-index="{i}" {checked}>
                            </td>
                            <td>{row['seq_num']}</td>
                            <td class="editable" contenteditable="true" data-col="start_time" data-row="{i}">{row['start_time']}</td>
                            <td class="editable" contenteditable="true" data-col="end_time" data-row="{i}">{row['end_time']}</td>
                            <td class="editable" contenteditable="true" data-col="text" data-row="{i}">{row['text']}</td>
                            <td class="editable" contenteditable="true" data-col="speaker" data-row="{i}">{row['speaker']}</td>
                        </tr>'''
            
            html += '''
                    </tbody>
                </table>
            </div>
            <script>
            (function() {
                // 同步复选框状态到隐藏的State
                function syncCheckboxStates() {
                    const checkboxes = document.querySelectorAll('.segment-checkbox');
                    const states = Array.from(checkboxes).map(cb => cb.checked);
                    const event = new CustomEvent('segmentCheckboxStatesChanged', {
                        detail: { states: states },
                        bubbles: true
                    });
                    document.dispatchEvent(event);
                }
                
                // 监听复选框变化
                document.addEventListener('change', function(e) {
                    if (e.target.classList.contains('segment-checkbox')) {
                        syncCheckboxStates();
                    }
                });
                
                // 监听单元格编辑
                document.addEventListener('blur', function(e) {
                    if (e.target.classList.contains('editable')) {
                        const event = new CustomEvent('segmentCellChanged', {
                            detail: {
                                row: parseInt(e.target.dataset.row),
                                col: e.target.dataset.col,
                                value: e.target.textContent.trim()
                            },
                            bubbles: true
                        });
                        document.dispatchEvent(event);
                    }
                }, true);
                
                setTimeout(syncCheckboxStates, 500);
            })();
            </script>'''
            
            return html
        
        # 注意：以下本地函数已删除，改用从src.segment_webui_editor导入的函数
        # 这些函数是旧版本，使用复选框，现在已改用输入框和Dataframe
        # - merge_selected_segments (已删除，使用导入的函数)
        # - split_segment_func (已删除，使用导入的函数)
        # - delete_selected_segments (已删除，使用导入的函数)
        # - add_new_segment (已删除，使用导入的函数)
        
        def save_segments_and_continue_from_table(table_data, segments_data_state, task_dir_val, segments_file_val, media, src_lang, tgt_lang, mode, is_single_speaker, enable_editing):
            """从表格数据保存编辑后的分段并继续执行"""
            if not task_dir_val or not segments_file_val:
                return (
                    gr.update(visible=True),  # segment_edit_group
                    gr.update(value="❌ 无法继续：缺少任务目录或分段文件路径"),  # segment_edit_status
                    gr.update(value=None, visible=False),  # output_video
                    gr.update(value=None, visible=False),  # output_audio
                    "❌ 无法继续：缺少任务目录或分段文件路径",  # status_text
                    "❌ 无法继续：缺少任务目录或分段文件路径",  # result_info
                    None,  # task_dir_state
                    None,  # translation_file_state
                    gr.update(visible=False),  # translation_edit_group
                    gr.update(visible=True)  # segment_edit_group (重复)
                )
            
            try:
                from src.segment_editor import load_segments, validate_segment_data, save_segments
                from src.output_manager import OutputManager, StepNumbers
                
                # 读取原始分段数据
                output_manager = OutputManager(media, cmd_args.output_dir)
                output_manager.task_dir = task_dir_val
                original_segments_file = os.path.join(task_dir_val, "04_segments_original.json")
                
                if not os.path.exists(original_segments_file):
                    return (
                        gr.update(visible=True),  # segment_edit_group
                        gr.update(value=f"❌ 无法继续：原始分段文件不存在: {original_segments_file}"),  # segment_edit_status
                        gr.update(value=None, visible=False),  # output_video
                        gr.update(value=None, visible=False),  # output_audio
                        f"❌ 无法继续：原始分段文件不存在: {original_segments_file}",  # status_text
                        f"❌ 无法继续：原始分段文件不存在: {original_segments_file}",  # result_info
                        None,  # task_dir_state
                        None,  # translation_file_state
                        gr.update(visible=False),  # translation_edit_group
                        gr.update(visible=True)  # segment_edit_group (重复)
                    )
                
                original_segments = load_segments(original_segments_file)
                
                # 记录接收到的table_data
                logger.info(f"[save_segments_and_continue_from_table] 接收到table_data，行数: {len(table_data) if table_data else 0}")
                if table_data and len(table_data) > 0:
                    logger.info(f"[save_segments_and_continue_from_table] 第一行table_data: {table_data[0]}")
                    logger.info(f"[save_segments_and_continue_from_table] 第一行文本内容: '{table_data[0].get('text', 'N/A')}'")
                
                # 自动检测并拆分包含换行符的分段
                from src.segment_webui_editor import auto_split_segments_by_newlines
                table_data, split_count = auto_split_segments_by_newlines(table_data, original_segments)
                auto_split_msg = ""
                if split_count > 0:
                    auto_split_msg = f"\n✅ 自动检测到换行符，已拆分 {split_count} 个分段"
                    logger.info(f"[save_segments_and_continue_from_table] 自动拆分了 {split_count} 个分段")
                
                # 将表格数据转换为segments格式
                edited_segments = convert_table_to_segments(table_data, original_segments)
                
                # 记录转换后的segments
                logger.info(f"[save_segments_and_continue_from_table] 转换后的segments行数: {len(edited_segments) if edited_segments else 0}")
                if edited_segments and len(edited_segments) > 0:
                    logger.info(f"[save_segments_and_continue_from_table] 第一个segment文本: '{edited_segments[0].get('text', 'N/A')}'")
                
                if not edited_segments:
                    return (
                        gr.update(visible=True),  # segment_edit_group
                        gr.update(value="❌ 分段数据为空"),  # segment_edit_status
                        gr.update(value=None, visible=False),  # output_video
                        gr.update(value=None, visible=False),  # output_audio
                        "❌ 分段数据为空",  # status_text
                        "❌ 分段数据为空",  # result_info
                        None,  # task_dir_state
                        None,  # translation_file_state
                        gr.update(visible=False),  # translation_edit_group
                        gr.update(visible=True)  # segment_edit_group (重复)
                    )
                
                # 收集所有单词用于验证
                all_words = []
                for seg in original_segments:
                    all_words.extend(seg.get('words', []))
                
                # 验证分段数据
                is_valid, error_msg = validate_segment_data(edited_segments, all_words)
                if not is_valid:
                    return (
                        gr.update(visible=True),  # segment_edit_group
                        gr.update(value=f"❌ 验证失败: {error_msg}"),  # segment_edit_status
                        gr.update(value=None, visible=False),  # output_video
                        gr.update(value=None, visible=False),  # output_audio
                        f"❌ 验证失败: {error_msg}",  # status_text
                        f"❌ 验证失败: {error_msg}",  # result_info
                        None,  # task_dir_state
                        None,  # translation_file_state
                        gr.update(visible=False),  # translation_edit_group
                        gr.update(visible=True)  # segment_edit_group (重复)
                    )
                
                # 保存分段文件
                save_segments(edited_segments, output_manager, all_words)
                
                # 继续执行步骤5-9
                from media_translation_cli import translate_media
                source_code = LANGUAGES.get(src_lang, src_lang)
                target_code = LANGUAGES.get(tgt_lang, tgt_lang)
                
                result = translate_media(
                    input_path=media,
                    source_lang=source_code,
                    target_lang=target_code,
                    output_dir=cmd_args.output_dir,
                    voice_model="index-tts2",
                    single_speaker=is_single_speaker,
                    continue_from_step5=True,
                    task_dir=task_dir_val,
                    pause_after_step5=enable_editing,
                    webui_mode=True
                )
                
                # 使用统一的处理函数处理结果
                return _handle_translation_result(result, mode, task_dir_val)
                    
            except Exception as e:
                logger.error(f"保存并继续失败: {e}")
                import traceback
                traceback.print_exc()
                return (
                    gr.update(visible=True),  # segment_edit_group
                    gr.update(value=f"❌ 保存并继续失败: {str(e)}"),  # segment_edit_status
                    gr.update(value=None, visible=False),  # output_video
                    gr.update(value=None, visible=False),  # output_audio
                    f"❌ 保存并继续失败: {str(e)}",  # status_text
                    f"❌ 保存并继续失败: {str(e)}",  # result_info
                    None,  # task_dir_state
                    None,  # translation_file_state
                    gr.update(visible=False),  # translation_edit_group
                    gr.update(visible=True)  # segment_edit_group (重复)
                )
        
        def save_segments_and_continue(edited_json, task_dir_val, segments_file_val, media, src_lang, tgt_lang, mode, is_single_speaker, enable_editing):
            """保存编辑后的分段并继续执行（从JSON编辑器）"""
            if not task_dir_val or not segments_file_val:
                return (
                    gr.update(visible=False),
                    gr.update(value=""),
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    "❌ 无法继续：缺少任务目录或分段文件路径",
                    "❌ 无法继续：缺少任务目录或分段文件路径"
                )
            
            try:
                from src.segment_editor import load_segments, validate_segment_data, save_segments
                from src.output_manager import OutputManager, StepNumbers
                import json
                
                # 解析编辑后的JSON
                try:
                    edited_segments = json.loads(edited_json)
                except json.JSONDecodeError as e:
                    return (
                        gr.update(visible=True),
                        gr.update(value=f"❌ JSON格式错误: {str(e)}"),
                        gr.update(value=None, visible=False),
                        gr.update(value=None, visible=False),
                        f"❌ JSON格式错误: {str(e)}",
                        f"❌ JSON格式错误: {str(e)}"
                    )
                
                # 继续执行步骤5-9
                from media_translation_cli import translate_media
                source_code = LANGUAGES.get(src_lang, src_lang)
                target_code = LANGUAGES.get(tgt_lang, tgt_lang)
                
                result = translate_media(
                    input_path=media,
                    source_lang=source_code,
                    target_lang=target_code,
                    output_dir=cmd_args.output_dir,
                    voice_model="index-tts2",
                    single_speaker=is_single_speaker,
                    continue_from_step5=True,
                    task_dir=task_dir_val,
                    pause_after_step5=enable_editing,
                    webui_mode=True
                )
                
                # 检查是否因为暂停而返回（步骤5完成但未完成全部）
                if result and result.get("needs_editing"):
                    task_dir = result.get("task_dir")
                    translation_file = result.get("translation_file")
                    if task_dir and translation_file:
                        return (
                            gr.update(visible=False),
                            gr.update(value="步骤5完成，请编辑翻译结果"),
                            gr.update(value=None, visible=False),
                            gr.update(value=None, visible=False),
                            "步骤5完成，请编辑翻译结果",
                            "步骤5完成，请编辑翻译结果"
                )
                
                if result and result.get("success"):
                    final_video_path = result.get("final_video_path")
                    final_audio_path = result.get("final_audio_path")
                    total_time = result.get("total_time")
                    time_text = f"耗时: {total_time:.1f}秒" if isinstance(total_time, (int, float)) else ""
                    
                    # 查找输出文件
                    task_dir_val = result.get("task_dir")
                    if not final_video_path and not final_audio_path and task_dir_val:
                        import glob
                        if mode == "视频":
                            video_files = sorted(glob.glob(os.path.join(task_dir_val, "*.mp4")), key=os.path.getmtime, reverse=True)
                            if video_files:
                                final_video_path = video_files[0]
                        else:
                            audio_files = sorted(glob.glob(os.path.join(task_dir_val, "*.wav")), key=os.path.getmtime, reverse=True)
                            if audio_files:
                                final_audio_path = audio_files[0]
                    
                    if mode == "视频":
                        if final_video_path and os.path.exists(final_video_path):
                            return (
                                gr.update(visible=False),
                                gr.update(value=""),
                                gr.update(value=final_video_path, visible=True),
                                gr.update(value=None, visible=False),
                                f"✅ 翻译完成！{time_text}",
                                f"✅ 翻译完成！{time_text}"
                            )
                        else:
                            return (
                                gr.update(visible=False),
                                gr.update(value=""),
                                gr.update(value=None, visible=False),
                                gr.update(value=None, visible=False),
                                "✅ 翻译完成，但未找到输出文件",
                                "✅ 翻译完成，但未找到输出文件"
                            )
                    else:
                        if final_audio_path and os.path.exists(final_audio_path):
                            return (
                                gr.update(visible=False),
                                gr.update(value=""),
                                gr.update(value=None, visible=False),
                                gr.update(value=final_audio_path, visible=True),
                                f"✅ 翻译完成！{time_text}",
                                f"✅ 翻译完成！{time_text}"
                            )
                        else:
                            return (
                                gr.update(visible=False),
                                gr.update(value=""),
                                gr.update(value=None, visible=False),
                                gr.update(value=None, visible=False),
                                "✅ 翻译完成，但未找到输出文件",
                                "✅ 翻译完成，但未找到输出文件"
                            )
                else:
                    error_msg = result.get("error", "未知错误") if result else "翻译失败"
                    return (
                        gr.update(visible=True),
                        gr.update(value=f"❌ 继续执行失败: {error_msg}"),
                        gr.update(value=None, visible=False),
                        gr.update(value=None, visible=False),
                        f"❌ 继续执行失败: {error_msg}",
                        f"❌ 继续执行失败: {error_msg}"
                    )
                    
            except Exception as e:
                logger.error(f"保存并继续失败: {e}")
                import traceback
                traceback.print_exc()
                return (
                    gr.update(visible=True),
                    gr.update(value=f"❌ 保存并继续失败: {str(e)}"),
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    f"❌ 保存并继续失败: {str(e)}",
                    f"❌ 保存并继续失败: {str(e)}"
                )
        
        def on_translate(media, src_lang, tgt_lang, mode, is_single_speaker, enable_segment_edit, enable_edit):
            logger.info(f"[on_translate] 开始翻译，media: {media}, mode: {mode}, enable_segment_edit: {enable_segment_edit}, enable_edit: {enable_edit}")
            
            if media is None:
                logger.warning("[on_translate] 媒体文件为空")
                return (
                    None,
                    None,
                    "请先上传媒体文件",
                    "翻译完成后将显示结果...",
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    None,
                    None,
                    None,
                    gr.update(visible=False),
                    gr.update(visible=False)
                )
            
            video_path, audio_path, status_msg, task_dir_val, translation_file_val, segments_file_val = translate_media_interface(
                media, src_lang, tgt_lang, mode, is_single_speaker, enable_segment_editing=enable_segment_edit, enable_editing=enable_edit
            )
            
            logger.info(f"[on_translate] translate_media_interface 返回: task_dir={task_dir_val}, translation_file={translation_file_val}, segments_file={segments_file_val}, status={status_msg}")
            
            # 如果返回了task_dir和segments_file，说明需要编辑分段
            if task_dir_val and segments_file_val:
                logger.info(f"[on_translate] 需要编辑分段，显示分段编辑界面")
                # 显示分段编辑界面
                return (
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    status_msg,
                    "步骤4完成，请编辑分段",
                    gr.update(interactive=False),
                    gr.update(interactive=False),
                    gr.update(interactive=False),
                    task_dir_val,
                    translation_file_val,
                    segments_file_val,
                    gr.update(visible=False),
                    gr.update(visible=True)
                )
            
            # 如果返回了task_dir和translation_file，且status_msg明确表示需要编辑，才显示翻译编辑界面
            if task_dir_val and translation_file_val and ("步骤5完成" in status_msg or "请编辑翻译结果" in status_msg):
                logger.info(f"[on_translate] 需要编辑翻译，显示翻译编辑界面，translation_file: {translation_file_val}")
                # 显示翻译编辑界面
                return (
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    status_msg,
                    "步骤5完成，请编辑翻译结果",
                    gr.update(interactive=False),
                    gr.update(interactive=False),
                    gr.update(interactive=False),
                    task_dir_val,
                    translation_file_val,
                    None,
                    gr.update(visible=True),
                    gr.update(visible=False)
                )
            
            # 正常完成
            if mode == "视频":
                result_info = update_result_info(status_msg)
                return (
                    gr.update(value=video_path, visible=bool(video_path)),
                    gr.update(value=None, visible=False),
                    status_msg,
                    result_info,
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    gr.update(interactive=True),
                    None,
                    None,
                    None,
                    gr.update(visible=False),
                    gr.update(visible=False)
                )
            info_text = update_result_info(status_msg) if audio_path else "❌ 未找到音频产物\n📝 请查看任务目录"
            return (
                gr.update(value=None, visible=False),
                gr.update(value=audio_path, visible=bool(audio_path)),
                status_msg,
                info_text,
                gr.update(interactive=True),
                gr.update(interactive=True),
                gr.update(interactive=True),
                None,
                None,
                None,
                gr.update(visible=False),
                gr.update(visible=False)
            )

        translate_btn.click(
            fn=disable_controls_before_translate,
            inputs=[current_media, source_language, target_language, input_mode],
            outputs=[output_video, output_audio, status_text, result_info, source_language, target_language, translate_btn]
        ).then(
            fn=on_translate,
            inputs=[current_media, source_language, target_language, input_mode, single_speaker, enable_segment_editing, enable_editing],
            outputs=[output_video, output_audio, status_text, result_info, source_language, target_language, translate_btn, task_dir_state, translation_file_state, segments_file_state, translation_edit_group, segment_edit_group]
        ).then(
            fn=lambda task_dir, segments_file, media, mode: load_segments_for_editing_wrapper(task_dir, segments_file, media, mode, cmd_args.output_dir) if (task_dir and segments_file) else (
                pd.DataFrame(columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"]),
                [],
                "",
                [],
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(visible=False),
                ""
            ),
            inputs=[task_dir_state, segments_file_state, current_media, input_mode],
            outputs=[segments_table_dataframe, segments_table_data_state, segments_json_editor, segments_data, save_segments_and_continue_btn, segment_media_player, segment_video_player, segment_edit_status]
        ).then(
            fn=load_translation_for_editing,
            inputs=[task_dir_state, translation_file_state],
            outputs=[translation_editor, save_and_continue_btn, edit_status]
        )
        
        # 保存并继续按钮
        save_and_continue_btn.click(
            fn=save_and_continue,
            inputs=[translation_editor, task_dir_state, translation_file_state, current_media, source_language, target_language, input_mode, single_speaker],
            outputs=[translation_edit_group, edit_status, output_video, output_audio, status_text, result_info]
        )
        
        # 统一的保存分段并继续函数（支持表格和JSON两种方式）
        def unified_save_segments_and_continue(
            dataframe_data, segments_json_editor, segments_data_state, 
            task_dir_val, segments_file_val, media, src_lang, tgt_lang, mode, is_single_speaker, enable_editing
        ):
            """统一的保存函数，优先使用表格数据，如果表格为空则使用JSON编辑器"""
            # 将Dataframe数据转换为table_data格式
            table_data = None
            # 检查数据是否有效（处理pandas DataFrame的情况）
            has_data = False
            if dataframe_data is not None:
                # 如果是pandas DataFrame，使用.empty属性
                if isinstance(dataframe_data, pd.DataFrame):
                    has_data = not dataframe_data.empty
                    if has_data:
                        # 将DataFrame转换为列表的列表格式
                        # 确保列顺序正确：序号, 开始时间(秒), 结束时间(秒), 文本内容, 说话人
                        expected_columns = ["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"]
                        if list(dataframe_data.columns) == expected_columns:
                            # 列顺序正确，直接转换
                            dataframe_data = dataframe_data.values.tolist()
                        else:
                            # 列顺序不对，按预期顺序重新排列
                            logger.warning(f"[unified_save_segments_and_continue] DataFrame列顺序不匹配，当前: {list(dataframe_data.columns)}，预期: {expected_columns}")
                            dataframe_data = dataframe_data[expected_columns].values.tolist()
                        logger.info(f"[unified_save_segments_and_continue] DataFrame转换为列表，行数: {len(dataframe_data)}")
                        if len(dataframe_data) > 0:
                            logger.info(f"[unified_save_segments_and_continue] 第一行数据: {dataframe_data[0]}")
                # 如果是列表，检查长度
                elif isinstance(dataframe_data, list):
                    has_data = len(dataframe_data) > 0
                # 其他类型，尝试转换为列表
                else:
                    try:
                        dataframe_data = list(dataframe_data)
                        has_data = len(dataframe_data) > 0
                    except (TypeError, ValueError):
                        has_data = False
            
            if has_data:
                # 检查是否是Dataframe格式（列表的列表）还是table_data格式（字典列表）
                try:
                    if isinstance(dataframe_data[0], list):
                        # Dataframe格式，需要转换
                        logger.info(f"[unified_save_segments_and_continue] 转换Dataframe数据，行数: {len(dataframe_data)}")
                        if len(dataframe_data) > 0:
                            logger.info(f"[unified_save_segments_and_continue] 第一行数据示例: {dataframe_data[0]}")
                        table_data = convert_dataframe_to_table_data(dataframe_data)
                        logger.info(f"[unified_save_segments_and_continue] 转换后的table_data行数: {len(table_data) if table_data else 0}")
                        if table_data and len(table_data) > 0:
                            logger.info(f"[unified_save_segments_and_continue] 第一行table_data示例: {table_data[0]}")
                    elif isinstance(dataframe_data[0], dict):
                        # 已经是table_data格式
                        logger.info(f"[unified_save_segments_and_continue] 数据已经是table_data格式，行数: {len(dataframe_data)}")
                        table_data = dataframe_data
                except (IndexError, TypeError) as e:
                    logger.warning(f"转换表格数据时出错: {e}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    table_data = None
            
            # 优先使用表格数据（如果表格有数据）
            if table_data and len(table_data) > 0:
                return save_segments_and_continue_from_table(
                    table_data, segments_data_state, task_dir_val, segments_file_val, 
                    media, src_lang, tgt_lang, mode, is_single_speaker, enable_editing
                )
            # 否则使用JSON编辑器
            elif segments_json_editor and segments_json_editor.strip():
                return save_segments_and_continue(
                    segments_json_editor, task_dir_val, segments_file_val, 
                    media, src_lang, tgt_lang, mode, is_single_speaker, enable_editing
                )
            else:
                return (
                    gr.update(visible=True),
                    gr.update(value="❌ 请先编辑分段数据"),
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    "❌ 请先编辑分段数据",
                    "❌ 请先编辑分段数据"
                )
        
        def _handle_translation_result(result, mode, task_dir_val):
            """处理翻译结果"""
            # 检查是否因为暂停而返回（步骤5完成但未完成全部）
            if result and result.get("needs_editing"):
                task_dir = result.get("task_dir")
                translation_file = result.get("translation_file")
                if task_dir and translation_file:
                    logger.info(f"[_handle_translation_result] 步骤5完成，需要编辑翻译，task_dir: {task_dir}, translation_file: {translation_file}")
                    return (
                        gr.update(visible=False),  # segment_edit_group
                        gr.update(value="步骤5完成，请编辑翻译结果"),  # segment_edit_status
                        gr.update(value=None, visible=False),  # output_video
                        gr.update(value=None, visible=False),  # output_audio
                        "步骤5完成，请编辑翻译结果",  # status_text
                        "步骤5完成，请编辑翻译结果",  # result_info
                        task_dir,  # task_dir_state
                        translation_file,  # translation_file_state
                        gr.update(visible=True),  # translation_edit_group
                        gr.update(visible=False)  # segment_edit_group (重复，但保持一致性)
                    )
            
            if result and result.get("success"):
                final_video_path = result.get("final_video_path")
                final_audio_path = result.get("final_audio_path")
                total_time = result.get("total_time")
                time_text = f"耗时: {total_time:.1f}秒" if isinstance(total_time, (int, float)) else ""
                
                # 查找输出文件
                task_dir_val = result.get("task_dir")
                if not final_video_path and not final_audio_path and task_dir_val:
                    import glob
                    if mode == "视频":
                        video_files = sorted(glob.glob(os.path.join(task_dir_val, "*.mp4")), key=os.path.getmtime, reverse=True)
                        if video_files:
                            final_video_path = video_files[0]
                    else:
                        audio_files = sorted(glob.glob(os.path.join(task_dir_val, "*.wav")), key=os.path.getmtime, reverse=True)
                        if audio_files:
                            final_audio_path = audio_files[0]
                
                if mode == "视频":
                    if final_video_path and os.path.exists(final_video_path):
                        return (
                            gr.update(visible=False),  # segment_edit_group
                            gr.update(value=""),  # segment_edit_status
                            gr.update(value=final_video_path, visible=True),  # output_video
                            gr.update(value=None, visible=False),  # output_audio
                            f"✅ 翻译完成！{time_text}",  # status_text
                            f"✅ 翻译完成！{time_text}",  # result_info
                            None,  # task_dir_state
                            None,  # translation_file_state
                            gr.update(visible=False),  # translation_edit_group
                            gr.update(visible=False)  # segment_edit_group (重复)
                        )
                else:
                    if final_audio_path and os.path.exists(final_audio_path):
                        return (
                            gr.update(visible=False),  # segment_edit_group
                            gr.update(value=""),  # segment_edit_status
                            gr.update(value=None, visible=False),  # output_video
                            gr.update(value=final_audio_path, visible=True),  # output_audio
                            f"✅ 翻译完成！{time_text}",  # status_text
                            f"✅ 翻译完成！{time_text}",  # result_info
                            None,  # task_dir_state
                            None,  # translation_file_state
                            gr.update(visible=False),  # translation_edit_group
                            gr.update(visible=False)  # segment_edit_group (重复)
                        )
            else:
                error_msg = result.get("error", "未知错误") if result else "翻译失败"
                return (
                    gr.update(visible=True),  # segment_edit_group
                    gr.update(value=f"❌ 继续执行失败: {error_msg}"),  # segment_edit_status
                    gr.update(value=None, visible=False),  # output_video
                    gr.update(value=None, visible=False),  # output_audio
                    f"❌ 继续执行失败: {error_msg}",  # status_text
                    f"❌ 继续执行失败: {error_msg}",  # result_info
                    None,  # task_dir_state
                    None,  # translation_file_state
                    gr.update(visible=False),  # translation_edit_group
                    gr.update(visible=True)  # segment_edit_group (重复)
                )
        
        # 保存分段并继续按钮（统一处理表格和JSON两种方式）
        save_segments_and_continue_btn.click(
            fn=unified_save_segments_and_continue,
            inputs=[
                segments_table_dataframe, segments_json_editor, segments_data,
                task_dir_state, segments_file_state, current_media, 
                source_language, target_language, input_mode, single_speaker, enable_editing
            ],
            outputs=[segment_edit_group, segment_edit_status, output_video, output_audio, status_text, result_info, task_dir_state, translation_file_state, translation_edit_group, segment_edit_group]
        ).then(
            fn=load_translation_for_editing,
            inputs=[task_dir_state, translation_file_state],
            outputs=[translation_editor, save_and_continue_btn, edit_status]
        )
        
        # 分段表格选择事件（更新选中索引）- 使用change事件代替select
        def update_selected_indices(table_data, evt: gr.SelectData):
            """当用户选择表格行时更新选中索引"""
            if evt and hasattr(evt, 'index'):
                return [evt.index]
            return []
        
        # 操作函数的包装器（已移动到 src.segment_webui_editor）
        # 使用导入的函数：parse_segment_indices_from_input, merge_segments_wrapper, split_segments_wrapper, show_split_dialog_wrapper, on_split_method_change
        
        # 合并分段按钮（使用输入框输入分段编号）
        merge_segments_btn.click(
            fn=merge_segments_wrapper,
            inputs=[segments_table_dataframe, merge_segments_input],
            outputs=[segments_table_dataframe, segments_table_data_state, merge_segments_input, segment_edit_status]
        )
        
        # 删除分段按钮（使用输入框输入分段编号）
        delete_segment_btn.click(
            fn=delete_segments_wrapper,
            inputs=[segments_table_dataframe, delete_segments_input],
            outputs=[segments_table_dataframe, segments_table_data_state, delete_segments_input, segment_edit_status]
        )
        
        # 添加分段按钮（显示对话框）
        add_segment_btn.click(
            fn=lambda: gr.update(visible=True),
            outputs=[add_dialog]
        )
        
        # 应用拆分按钮（检测换行符并自动拆分）
        apply_auto_split_btn.click(
            fn=apply_auto_split_wrapper,
            inputs=[segments_table_dataframe, segments_data],
            outputs=[segments_table_dataframe, segments_table_data_state, segment_edit_status]
        )
        
        # 添加确认按钮（使用Dataframe）
        add_confirm_btn.click(
            fn=add_segment_wrapper,
            inputs=[segments_table_dataframe, add_start_time, add_end_time, add_text, segments_data],
            outputs=[segments_table_dataframe, segments_table_data_state, segment_edit_status]
        ).then(
            fn=lambda: (gr.update(value=0.0), gr.update(value=0.0), gr.update(value="")),
            outputs=[add_start_time, add_end_time, add_text]
        ).then(
            fn=lambda: gr.update(visible=False),
            outputs=[add_dialog]
        )
        
        # 添加取消按钮
        add_cancel_btn.click(
            fn=lambda: gr.update(visible=False),
            outputs=[add_dialog]
        )

        input_video.change(
            fn=on_media_upload,
            inputs=[input_video, input_mode],
            outputs=[file_info, source_language, target_language, translate_btn, status_text, current_media]
        )
        input_audio.change(
            fn=on_media_upload,
            inputs=[input_audio, input_mode],
            outputs=[file_info, source_language, target_language, translate_btn, status_text, current_media]
        )

        def on_mode_change(mode):
            show_video = (mode == "视频")
            show_audio = (mode == "音频")
            return (
                gr.update(visible=show_video),
                gr.update(visible=show_audio),
                "请上传媒体文件（视频或音频）...",
                gr.update(value="中文", interactive=False),
                gr.update(value="English", interactive=False),
                gr.update(interactive=False),
                "等待上传媒体...",
                None
            )
        input_mode.change(
            fn=on_mode_change,
            inputs=[input_mode],
            outputs=[input_video, input_audio, file_info, source_language, target_language, translate_btn, status_text, current_media]
        )

        def on_mode_change_outputs(mode):
            show_video = (mode == "视频")
            show_audio = (mode == "音频")
            return (
                gr.update(value=None, visible=show_video),
                gr.update(value=None, visible=show_audio)
            )
        input_mode.change(
            fn=on_mode_change_outputs,
            inputs=[input_mode],
            outputs=[output_video, output_audio]
        )

    return demo


def background_preload():
    if cmd_args.preload_models:
        print("🚀 开始后台预加载模型...")
        preload_success = preload_models()
        if preload_success:
            print("✅ 所有模型预加载完成！系统已就绪")
        else:
            failed_models = model_preloader.get_failed_models() if model_preloader else []
            print(f"⚠️ 部分模型预加载失败: {failed_models}，但系统仍可运行")
    else:
        print("⚠️ 跳过模型预加载（首次使用可能较慢）")


def main():
    print("🎬 启动音视频翻译 Web UI - 模型预加载版...")
    print(f"📁 输出目录: {cmd_args.output_dir}")
    print(f"🌐 访问地址: http://{cmd_args.host}:{cmd_args.port}")
    demo = create_interface()
    if cmd_args.preload_models:
        preload_thread = threading.Thread(target=background_preload, daemon=True)
        preload_thread.start()
        print("🚀 模型预加载已在后台启动...")
    print("🌐 启动 Web 服务...")
    demo.launch(server_name=cmd_args.host, server_port=cmd_args.port, share=False, debug=cmd_args.verbose)


if __name__ == "__main__":
    main()



