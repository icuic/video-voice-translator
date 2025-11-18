#!/usr/bin/env python3
"""
通用媒体翻译脚本
可以翻译任何视频或音频文件
使用方法: python media_translation_cli.py <输入视频/音频路径> [选项]
"""

import sys
import os
import time
import logging
import argparse
import json
from typing import List, Dict, Any, Optional
from src.utils import load_config, detect_language, apply_language_settings
from src.output_manager import OutputManager, StepNumbers
from src.performance_stats import PerformanceStats
from src.pipeline.processing_context import ProcessingContext
from src.pipeline.step1_audio_extraction import Step1AudioExtraction
from src.pipeline.step2_audio_separation import Step2AudioSeparation
from src.pipeline.step3_multi_speaker import Step3MultiSpeaker
from src.pipeline.step4_speech_recognition import Step4SpeechRecognition
from src.pipeline.step5_text_translation import Step5TextTranslation
from src.pipeline.step6_reference_audio import Step6ReferenceAudio
from src.pipeline.step7_voice_cloning import Step7VoiceCloning
from src.pipeline.step8_audio_merging import Step8AudioMerging
from src.pipeline.step9_video_synthesis import Step9VideoSynthesis

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def translate_media(input_path, source_lang='auto', target_lang='auto', output_dir='data/outputs', voice_model='index-tts2', single_speaker=False, pause_after_step4=False, pause_after_step5=False, continue_from_step5=False, continue_from_step6=False, task_dir=None, webui_mode=False):
    """翻译任意视频或音频文件 - 使用新的步骤文件架构"""
    # 记录总开始时间
    total_start_time = time.time()
    
    print('🎬 开始媒体翻译流程')
    print('=' * 60)
    print(f'📹 输入文件: {input_path}')
    print(f'🌐 源语言: {source_lang}')
    print(f'🌐 目标语言: {target_lang}')
    print(f'🎤 音色克隆模型: {voice_model}')
    print(f'📁 输出目录: {output_dir}')
    print('=' * 60)
    
    # 检查输入文件
    if not os.path.exists(input_path):
        print(f'❌ 输入文件不存在: {input_path}')
        return {
            "success": False,
            "error": f"输入文件不存在: {input_path}",
            "task_dir": None
        }
    
    # 判断输入文件类型
    file_ext = os.path.splitext(input_path)[1].lower()
    is_audio = file_ext in ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg']
    is_video = file_ext in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']
    
    if not (is_audio or is_video):
        print(f'❌ 不支持的文件格式: {file_ext}')
        print('支持的格式: 视频(.mp4, .avi, .mov, .mkv, .wmv, .flv) 或 音频(.wav, .mp3, .m4a, .flac, .aac, .ogg)')
        return {
            "success": False,
            "error": f"不支持的文件格式: {file_ext}",
            "task_dir": None
        }
    
    # 语言自动检测
    if source_lang == 'auto' or target_lang == 'auto':
        print('🔍 检测输入语言...')
        detected_lang = detect_language(input_path)
        print(f'✅ 检测到语言: {detected_lang}')
        
        if source_lang == 'auto':
            source_lang = detected_lang
        if target_lang == 'auto':
            target_lang = 'en' if detected_lang == 'zh' else 'zh'
    
    # 加载配置并应用语言设置
    config = load_config()
    config = apply_language_settings(config, source_lang, target_lang, voice_model)
    
    # 创建OutputManager和PerformanceStats
    if task_dir and os.path.exists(task_dir) and (continue_from_step5 or continue_from_step6):
        # 从指定任务目录继续（步骤5或步骤6）
        output_manager = OutputManager(input_path, output_dir)
        output_manager.task_dir = task_dir
        print(f'📁 继续任务目录: {task_dir}')
    else:
        output_manager = OutputManager(input_path, output_dir)
        task_dir = output_manager.create_task_directory()
        print(f'📁 任务目录: {task_dir}')
    
    # 设置任务级日志（保存到任务目录）
    task_log_path = output_manager.setup_task_logging()
    print(f'📝 任务日志将保存到: {task_log_path}')
    
    # 初始化性能统计
    stats = output_manager.get_performance_stats()
    
    # 创建ProcessingContext
    context = ProcessingContext(
        input_path=input_path,
        source_lang=source_lang,
        target_lang=target_lang,
        voice_model=voice_model,
        single_speaker=single_speaker,
        output_dir=output_dir,
        config=config,
        output_manager=output_manager,
        stats=stats,
        pause_after_step4=pause_after_step4,
        pause_after_step5=pause_after_step5
    )
    
    try:
        # 如果从步骤5继续，需要先加载已编辑的分段结果
        if continue_from_step5:
            print('\n📝 从步骤5继续，加载已编辑的分段结果...')
            from src.segment_editor import load_segments, validate_segment_data, save_segments
            
            # 读取原始分段数据
            original_segments_file = os.path.join(task_dir, "04_segments_original.json")
            if not os.path.exists(original_segments_file):
                return {
                    "success": False,
                    "error": f"无法继续：原始分段文件不存在: {original_segments_file}",
                    "task_dir": output_manager.task_dir
                }
            
            original_segments = load_segments(original_segments_file)
            
            # 读取编辑后的分段文件
            segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
            if not os.path.exists(segments_json_file):
                return {
                    "success": False,
                    "error": f"无法继续：编辑后的分段文件不存在: {segments_json_file}",
                    "task_dir": output_manager.task_dir
                }
            
            edited_segments = load_segments(segments_json_file)
            
            # 收集所有单词用于验证
            all_words = []
            for seg in original_segments:
                all_words.extend(seg.get('words', []))
            
            # 验证编辑后的分段数据
            is_valid, error_msg = validate_segment_data(edited_segments, all_words)
            if not is_valid:
                print(f'⚠️  分段数据验证警告: {error_msg}')
                print('⚠️  继续执行，但建议检查分段数据')
            else:
                print(f'✅ 分段数据验证通过，共 {len(edited_segments)} 个分段')
        
        # 如果从步骤6继续，需要先加载已编辑的翻译结果
        if continue_from_step6:
            print('\n📝 从步骤6继续，加载已编辑的翻译结果...')
            from src.translation_editor import parse_translation_txt, validate_translation_data
            
            # 读取原始segments
            segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
            if not os.path.exists(segments_json_file):
                return {
                    "success": False,
                    "error": f"无法继续：原始segments文件不存在: {segments_json_file}",
                    "task_dir": output_manager.task_dir
                }
            
            with open(segments_json_file, 'r', encoding='utf-8') as f:
                original_segments = json.load(f)
            
            # 尝试读取编辑后的翻译文件
            translation_file = output_manager.get_file_path(StepNumbers.STEP_5, "translation")
            translated_segments_file = os.path.join(task_dir, "05_translated_segments.json")
            
            if os.path.exists(translated_segments_file):
                # 检查TXT文件是否比JSON文件更新
                needs_reparse = False
                if os.path.exists(translation_file):
                    txt_mtime = os.path.getmtime(translation_file)
                    json_mtime = os.path.getmtime(translated_segments_file)
                    if txt_mtime > json_mtime:
                        print(f'⚠️  TXT文件比JSON文件新（时间差: {txt_mtime - json_mtime:.1f}秒），将从TXT文件重新解析...')
                        needs_reparse = True
                
                # 如果TXT文件更新，或者JSON文件缺少必要字段，从TXT文件重新解析
                if not needs_reparse:
                    # 优先使用JSON文件
                    with open(translated_segments_file, 'r', encoding='utf-8') as f:
                        translated_segments = json.load(f)
                    print(f'✅ 从JSON文件加载翻译结果: {translated_segments_file}')
                    
                    # 检查JSON文件是否缺少必要的字段（如original_text）
                    if translated_segments and len(translated_segments) > 0:
                        first_segment = translated_segments[0]
                        if 'original_text' not in first_segment or not first_segment.get('original_text'):
                            print('⚠️  JSON文件缺少original_text字段，将从TXT文件重新解析...')
                            needs_reparse = True
                
                # 如果缺少必要字段或TXT文件更新，从TXT文件重新解析
                if needs_reparse:
                    if not os.path.exists(translation_file):
                        return {
                            "success": False,
                            "error": f"无法继续：需要从TXT文件重新解析，但TXT文件不存在: {translation_file}",
                            "task_dir": output_manager.task_dir
                        }
                    translated_segments = parse_translation_txt(translation_file, original_segments)
                    print(f'✅ 从TXT文件重新解析翻译结果: {translation_file}')
                    
                    # 重新保存JSON文件
                    from src.translation_editor import save_translation_files
                    save_translation_files(translated_segments, output_manager, original_segments)
                    print(f'✅ 已更新JSON文件: {translated_segments_file}')
            elif os.path.exists(translation_file):
                # 解析TXT文件
                translated_segments = parse_translation_txt(translation_file, original_segments)
                print(f'✅ 从TXT文件解析翻译结果: {translation_file}')
            else:
                return {
                    "success": False,
                    "error": f"无法继续：找不到翻译文件。请检查: {translation_file} 或 {translated_segments_file}",
                    "task_dir": output_manager.task_dir
                }
            
            # 验证翻译数据
            is_valid, error_msg = validate_translation_data(translated_segments, original_segments)
            if not is_valid:
                return {
                    "success": False,
                    "error": f"翻译数据验证失败: {error_msg}",
                    "task_dir": output_manager.task_dir
                }
            
            # 保存到context中供后续步骤使用
            context.translated_segments = translated_segments
            print(f'✅ 已加载 {len(translated_segments)} 个翻译片段')
        
        # 执行9个步骤
        steps = [
            ("步骤1: 音频提取", Step1AudioExtraction),
            ("步骤2: 音频分离", Step2AudioSeparation),
            ("步骤3: 多说话人处理", Step3MultiSpeaker),
            ("步骤4: 语音识别", Step4SpeechRecognition),
            ("步骤5: 文本翻译", Step5TextTranslation),
            ("步骤6: 参考音频提取", Step6ReferenceAudio),
            ("步骤7: 音色克隆", Step7VoiceCloning),
            ("步骤8: 音频合并", Step8AudioMerging),
            ("步骤9: 视频合成", Step9VideoSynthesis),
        ]
        
        # 如果从步骤5或步骤6继续，跳过前面的步骤
        if continue_from_step5:
            start_index = 4  # 从步骤5开始（索引4）
        elif continue_from_step6:
            start_index = 5  # 从步骤6开始（索引5）
        else:
            start_index = 0
        
        for i, (step_name, step_class) in enumerate(steps[start_index:], start=start_index):
            print(f'\n{step_name}...')
            step = step_class(context)
            result = step.run_with_stats(step_name)
            
            if not result.get("success", False):
                error_msg = result.get("error", "未知错误")
                print(f'❌ {step_name}失败: {error_msg}')
                return {
                    "success": False,
                    "error": f"{step_name}失败: {error_msg}",
                    "task_dir": output_manager.task_dir
                }
            
            # 检查是否跳过（某些步骤可能被跳过）
            if result.get("skipped", False):
                print(f'⏭️  {step_name}已跳过: {result.get("reason", "")}')
            
            # 步骤4完成后，如果设置了暂停，则暂停并等待用户编辑分段
            if i == 3 and pause_after_step4:  # 步骤4是索引3
                print('\n' + '=' * 60)
                print('⏸️  步骤4完成，已暂停以允许编辑分段')
                print('=' * 60)
                segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
                print(f'\n📝 分段文件位置: {segments_json_file}')
                
                if webui_mode:
                    # Web UI模式：直接返回，不等待输入
                    print('📝 Web UI模式：返回编辑状态')
                    return {
                        "success": True,
                        "task_dir": output_manager.task_dir,
                        "segments_file": segments_json_file,
                        "needs_segment_editing": True,
                        "final_video_path": None,
                        "total_time": time.time() - total_start_time
                    }
                
                # 命令行模式：等待用户输入
                print('\n⚠️  重要提示:')
                print('   - 可以修改分段的时间戳、文本、合并、拆分等')
                print('   - 系统会根据单词时间戳自动计算和验证')
                print('   - 修改完成后，使用以下命令继续:')
                print(f'     python media_translation_cli.py {input_path} --continue-from step5 --task-dir {task_dir}')
                print('\n   或者直接输入 continue 或 c 继续（如果已在同一会话中）:')
                
                while True:
                    user_input = input('\n请输入 continue 或 c 继续: ').strip().lower()
                    if user_input in ['continue', 'c']:
                        break
                    else:
                        print('❌ 无效输入，请输入 continue 或 c')
                
                print('\n📝 读取编辑后的分段文件...')
                from src.segment_editor import load_segments, validate_segment_data, save_segments
                
                # 读取原始分段数据
                original_segments_file = os.path.join(task_dir, "04_segments_original.json")
                if not os.path.exists(original_segments_file):
                    return {
                        "success": False,
                        "error": f"无法继续：原始分段文件不存在: {original_segments_file}",
                        "task_dir": output_manager.task_dir
                    }
                
                original_segments = load_segments(original_segments_file)
                
                try:
                    # 读取编辑后的分段文件
                    edited_segments = load_segments(segments_json_file)
                    print(f'✅ 成功加载 {len(edited_segments)} 个分段')
                    
                    # 收集所有单词用于验证
                    all_words = []
                    for seg in original_segments:
                        all_words.extend(seg.get('words', []))
                    
                    # 验证分段数据
                    is_valid, error_msg = validate_segment_data(edited_segments, all_words)
                    if not is_valid:
                        print(f'❌ 分段数据验证失败: {error_msg}')
                        return {
                            "success": False,
                            "error": f"分段数据验证失败: {error_msg}",
                            "task_dir": output_manager.task_dir
                        }
                    
                    # 规范化并保存分段数据
                    save_segments(edited_segments, output_manager, all_words)
                    print('✅ 分段文件验证通过，继续执行后续步骤...')
                    
                except Exception as e:
                    print(f'❌ 读取分段文件失败: {e}')
                    import traceback
                    traceback.print_exc()
                    return {
                        "success": False,
                        "error": f"读取分段文件失败: {str(e)}",
                        "task_dir": output_manager.task_dir
                    }
            
            # 步骤5完成后，如果设置了暂停，则暂停并等待用户编辑
            if i == 4 and pause_after_step5:  # 步骤5是索引4
                print('\n' + '=' * 60)
                print('⏸️  步骤5完成，已暂停以允许编辑翻译结果')
                print('=' * 60)
                translation_file = output_manager.get_file_path(StepNumbers.STEP_5, "translation")
                print(f'\n📝 翻译文件位置: {translation_file}')
                
                if webui_mode:
                    # Web UI模式：直接返回，不等待输入
                    print('📝 Web UI模式：返回编辑状态')
                    return {
                        "success": True,
                        "task_dir": output_manager.task_dir,
                        "translation_file": translation_file,
                        "needs_editing": True,
                        "final_video_path": None,
                        "total_time": time.time() - total_start_time
                    }
                
                # 命令行模式：等待用户输入
                print('\n⚠️  重要提示:')
                print('   - 只能修改译文，不要修改原文和时间戳')
                print('   - 原文和时间戳必须保持不变')
                print('   - 修改完成后，使用以下命令继续:')
                print(f'     python media_translation_cli.py {input_path} --continue-from step6 --task-dir {task_dir}')
                print('\n   或者直接输入 continue 或 c 继续（如果已在同一会话中）:')
                
                while True:
                    user_input = input('\n请输入 continue 或 c 继续: ').strip().lower()
                    if user_input in ['continue', 'c']:
                        break
                    else:
                        print('❌ 无效输入，请输入 continue 或 c')
                
                print('\n📝 读取编辑后的翻译文件...')
                from src.translation_editor import parse_translation_txt, validate_translation_data, save_translation_files
                
                # 读取原始segments
                segments_json_file = output_manager.get_file_path(StepNumbers.STEP_4, "segments_json")
                with open(segments_json_file, 'r', encoding='utf-8') as f:
                    original_segments = json.load(f)
                
                try:
                    # 解析编辑后的翻译文件
                    translated_segments = parse_translation_txt(translation_file, original_segments)
                    print(f'✅ 成功解析 {len(translated_segments)} 个翻译片段')
                    
                    # 验证翻译数据
                    is_valid, error_msg = validate_translation_data(translated_segments, original_segments)
                    if not is_valid:
                        print(f'❌ 翻译数据验证失败: {error_msg}')
                        return {
                            "success": False,
                            "error": f"翻译数据验证失败: {error_msg}",
                            "task_dir": output_manager.task_dir
                        }
                    
                    # 保存到JSON文件
                    save_translation_files(translated_segments, output_manager, original_segments)
                    
                    # 保存到context中供后续步骤使用
                    context.translated_segments = translated_segments
                    print('✅ 翻译文件验证通过，继续执行后续步骤...')
                    
                except Exception as e:
                    print(f'❌ 解析翻译文件失败: {e}')
                    import traceback
                    traceback.print_exc()
                    return {
                        "success": False,
                        "error": f"解析翻译文件失败: {str(e)}",
                        "task_dir": output_manager.task_dir
                    }
        
        # 计算总耗时
        total_time = time.time() - total_start_time
        
        # 获取最终输出路径
        final_video_path = None
        if context.is_video:
            final_video_path = output_manager.get_file_path(StepNumbers.STEP_9, "final_video")
        else:
            final_video_path = output_manager.get_file_path(StepNumbers.STEP_9, "final_video").replace('.mp4', '.wav')
        
        print('\n🎉 翻译完成!')
        print(f'\n📊 生成的文件:')
        if context.is_video:
            print(f'🎬 最终翻译视频: {final_video_path}')
        else:
            print(f'🎵 最终翻译音频: {final_video_path}')
        print(f'\n⏱️  总耗时: {total_time:.1f}秒 ({total_time/60:.1f}分钟)')
        
        # 保存性能统计
        output_manager.save_performance_stats()
        
        # 获取翻译文件路径（如果存在）
        translation_file = None
        try:
            translation_file_path = output_manager.get_file_path(StepNumbers.STEP_5, "translation")
            if os.path.exists(translation_file_path):
                translation_file = translation_file_path
        except Exception:
            # 如果获取失败，忽略错误，继续返回其他信息
            pass
        
        return {
            "success": True,
            "task_dir": output_manager.task_dir,
            "final_video_path": final_video_path,
            "total_time": total_time,
            "translation_file": translation_file
        }
        
    except Exception as e:
        print(f'❌ 翻译失败: {e}')
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "task_dir": output_manager.task_dir if 'output_manager' in locals() else None
        }


def main():
    """主函数，解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='通用媒体翻译工具 - 支持多语言互译',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 自动检测语言并翻译
  python media_translation_cli.py input.mp4
  
  # 中文视频翻译成英文
  python media_translation_cli.py input.mp4 --source-lang zh --target-lang en
  
  # 英文视频翻译成中文
  python media_translation_cli.py input.mp4 --source-lang en --target-lang zh
  
  # 指定输出目录
  python media_translation_cli.py input.mp4 --output-dir my_output
  
  # 使用不同的音色克隆模型
  python media_translation_cli.py input.mp4 --voice-model xtts
  
  # 指定仅一人说话（跳过说话人分离）
  python media_translation_cli.py input.mp4 --single-speaker
  
  # 步骤4后暂停以编辑分段
  python media_translation_cli.py input.mp4 --pause-after step4
  
  # 从步骤5继续（使用编辑后的分段）
  python media_translation_cli.py input.mp4 --continue-from step5 --task-dir <task_dir>
        """
    )
    
    parser.add_argument('input_file', 
                       help='输入视频或音频文件路径')
    parser.add_argument('--source-lang', 
                       default='auto',
                       choices=['auto', 'zh', 'en'],
                       help='源语言 (默认: auto - 自动检测)')
    parser.add_argument('--target-lang', 
                       default='auto',
                       choices=['auto', 'zh', 'en'],
                       help='目标语言 (默认: auto - 自动选择)')
    parser.add_argument('--output-dir', 
                       default='data/outputs',
                       help='输出目录 (默认: data/outputs)')
    parser.add_argument('--voice-model', 
                       default='index-tts2',
                       choices=['index-tts2', 'xtts'],
                       help='音色克隆模型 (默认: index-tts2)')
    parser.add_argument('--single-speaker',
                       action='store_true',
                       default=False,
                       help='仅一人说话，跳过说话人分离步骤（对应WebUI中的"仅一人说话"选项）')
    parser.add_argument('--pause-after', 
                       choices=['step4', 'step5'],
                       help='在指定步骤完成后暂停，允许手动编辑文件（支持 step4 和 step5）')
    parser.add_argument('--continue-from',
                       choices=['step5', 'step6'],
                       help='从指定步骤继续执行（需要配合 --task-dir 使用）')
    parser.add_argument('--task-dir',
                       help='任务目录路径（用于 --continue-from 参数）')
    parser.add_argument('--verbose', '-v',
                       action='store_true',
                       help='显示详细日志')
    
    args = parser.parse_args()
    
    # 验证参数组合
    if args.continue_from and not args.task_dir:
        parser.error('使用 --continue-from 时必须指定 --task-dir')
    
    # 设置日志级别
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 执行翻译
    pause_after_step4 = args.pause_after == 'step4' if args.pause_after else False
    pause_after_step5 = args.pause_after == 'step5' if args.pause_after else False
    continue_from_step5 = args.continue_from == 'step5' if args.continue_from else False
    continue_from_step6 = args.continue_from == 'step6' if args.continue_from else False
    
    result = translate_media(
        args.input_file,
        args.source_lang,
        args.target_lang,
        args.output_dir,
        args.voice_model,
        args.single_speaker,
        pause_after_step4=pause_after_step4,
        pause_after_step5=pause_after_step5,
        continue_from_step5=continue_from_step5,
        continue_from_step6=continue_from_step6,
        task_dir=args.task_dir
    )
    
    return 0 if result.get("success", False) else 1

if __name__ == "__main__":
    sys.exit(main())

