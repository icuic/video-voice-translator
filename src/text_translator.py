"""
文本翻译模块
将English文本翻译成中文，保持语义完整性和对话逻辑
"""

import os
import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from .utils import validate_file_path, create_output_dir, safe_filename
from .output_manager import OutputManager, StepNumbers


class TextTranslator:
    """文本翻译器类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化文本翻译器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 翻译配置
        self.translation_config = config.get("translation", {})
        self.source_language = self.translation_config.get("source_language", "zh")
        self.target_language = self.translation_config.get("target_language", "zh")  # 修复：默认值改为zh
        self.translation_model = self.translation_config.get("model", "qwen-flash")
        
        # 重试策略配置
        self.retry_strategy = self.translation_config.get("retry_strategy", "adaptive")
        self.max_batch_size = self.translation_config.get("max_batch_size", 100)
        self.max_retries = self.translation_config.get("max_retries", 3)
        self.single_segment_retries = self.translation_config.get("single_segment_retries", 3)
        
        self.logger.info(f"翻译重试策略: {self.retry_strategy}")
        self.logger.info(f"最大批量大小: {self.max_batch_size}")
        self.logger.info(f"翻译模型版本: {self.translation_model}")
        
        # 初始化翻译引擎
        self._init_translation_engine()
    
    def _init_translation_engine(self):
        """初始化翻译引擎"""
        try:
            self.logger.info(f"使用 {self.translation_model} 大模型翻译引擎")
            try:
                from openai import OpenAI
                import os
                # 从环境变量读取API密钥
                api_key = os.getenv("DASHSCOPE_API_KEY")
                if not api_key:
                    raise ValueError(
                        "未设置DASHSCOPE_API_KEY环境变量。"
                        "请通过以下方式设置：\n"
                        "  export DASHSCOPE_API_KEY='your-api-key'\n"
                        "或在代码运行前设置环境变量。"
                        "获取API密钥请访问：https://dashscope.console.aliyun.com/"
                    )
                self.translator = OpenAI(
                    api_key=api_key,
                    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    timeout=300.0,  # 增加超时时间到5分钟，处理大批量翻译
                )
                self.logger.info(f"{self.translation_model}翻译引擎初始化成功")
            except Exception as e:
                self.logger.error(f"{self.translation_model}翻译引擎初始化失败: {e}")
                self.translator = None
                
        except Exception as e:
            self.logger.error(f"翻译引擎初始化失败: {e}")
            raise
    
    
    def translate_segments(self, segments: List[Dict[str, Any]], 
                          output_dir: Optional[str] = None,
                          output_manager: Optional[OutputManager] = None) -> Dict[str, Any]:
        """
        翻译多个音频段落 - 使用批量翻译提升质量
        
        Args:
            segments: 音频段落列表
            output_dir: 输出目录
            
        Returns:
            翻译结果字典
        """
        if not segments:
            return {
                "success": False,
                "error": "没有提供音频段落"
            }
        
        # 🚀 优化：检查源语言和目标语言是否相同
        if self.source_language == self.target_language:
            self.logger.info(f"源语言和目标语言相同({self.source_language})，跳过LLM翻译步骤")
            
            # 直接复制原始文本作为翻译结果
            translated_segments = []
            for segment in segments:
                translated_segment = {
                    **segment,
                    "original_text": segment.get("text", ""),
                    "translated_text": segment.get("text", ""),  # 直接使用原文
                    "translation_info": {
                        "method": "skip_translation",
                        "reason": "source_target_same",
                        "source_language": self.source_language,
                        "target_language": self.target_language
                    }
                }
                translated_segments.append(translated_segment)
            
            self.logger.info(f"✅ 跳过翻译完成: {len(translated_segments)} 个段落")
            return {
                "success": True,
                "translated_segments": translated_segments,
                "translation_info": {
                    "method": "skip_translation",
                    "reason": "源语言和目标语言相同，跳过翻译",
                    "segments_processed": len(segments),
                    "source_language": self.source_language,
                    "target_language": self.target_language
                }
            }
        
        self.logger.info(f"开始批量翻译 {len(segments)} 个音频段落")
        
        # 创建输出目录
        if output_dir:
            create_output_dir(output_dir)
        
        try:
            # 使用批量翻译方法
            if self.translator is not None:
                # 使用批量翻译
                result = self._batch_translate_with_qwen(segments, output_dir, output_manager)
            else:
                # 翻译引擎未初始化，返回错误
                return {
                    "success": False,
                    "error": f"翻译引擎未初始化，请检查配置和API密钥",
                    "translated_segments": []
                }
            
            self.logger.info(f"批量翻译完成: {result.get('translated_segments', 0)}/{len(segments)}")
            return result
            
        except Exception as e:
            self.logger.error(f"批量翻译失败: {e}")
            self.logger.error(f"错误类型: {type(e).__name__}")
            self.logger.error(f"错误详情: {str(e)}")
            import traceback
            self.logger.error(f"错误堆栈: {traceback.format_exc()}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "translated_segments": []
            }
    
    def translate_segments_with_output_manager(self, segments: List[Dict[str, Any]], 
                                             output_manager: OutputManager,
                                             progress_callback=None) -> Dict[str, Any]:
        """
        使用OutputManager翻译多个音频段落
        
        Args:
            segments: 音频段落列表
            output_manager: 输出管理器实例
            progress_callback: 进度回调函数，格式: (step_index, step_name, progress_pct, message, current_segment, total_segments)
            
        Returns:
            翻译结果字典
        """
        if not segments:
            return {
                "success": False,
                "error": "没有提供音频段落"
            }
        
        # 检查源语言和目标语言是否相同
        if self.source_language == self.target_language:
            self.logger.info(f"源语言和目标语言相同({self.source_language})，跳过LLM翻译步骤")
            output_manager.log(f"步骤5跳过: 源语言和目标语言相同({self.source_language})")
            
            # 直接复制原始文本作为翻译结果
            translated_segments = []
            for segment in segments:
                translated_segment = {
                    **segment,
                    "original_text": segment.get("text", ""),
                    "translated_text": segment.get("text", ""),  # 直接使用原文
                    "translation_info": {
                        "method": "skip_translation",
                        "reason": "source_target_same",
                        "source_language": self.source_language,
                        "target_language": self.target_language
                    }
                }
                translated_segments.append(translated_segment)
            
            # 保存翻译结果到OutputManager指定的路径
            translation_file = output_manager.get_file_path(StepNumbers.STEP_5, "translation")
            llm_interaction_file = output_manager.get_file_path(StepNumbers.STEP_5, "llm_interaction")
            
            # 保存翻译文本
            with open(translation_file, 'w', encoding='utf-8') as f:
                for i, segment in enumerate(translated_segments):
                    f.write(f"Segment {i+1} ({segment['start']:.3f}s - {segment['end']:.3f}s):\n")
                    f.write(f"原文: {segment['original_text']}\n")
                    f.write(f"译文: {segment['translated_text']}\n\n")
            
            # 保存LLM交互记录
            with open(llm_interaction_file, 'w', encoding='utf-8') as f:
                f.write("跳过翻译 - 源语言和目标语言相同\n")
                f.write(f"源语言: {self.source_language}\n")
                f.write(f"目标语言: {self.target_language}\n")
                f.write(f"处理段落数: {len(segments)}\n")
            
            output_manager.log(f"步骤5完成: 跳过翻译，{len(translated_segments)} 个段落")
            return {
                "success": True,
                "translated_segments": translated_segments,
                "translation_file": translation_file,
                "llm_interaction_file": llm_interaction_file,
                "translation_info": {
                    "method": "skip_translation",
                    "reason": "源语言和目标语言相同，跳过翻译",
                    "segments_processed": len(segments),
                    "source_language": self.source_language,
                    "target_language": self.target_language
                }
            }
        
        # 执行实际翻译
        output_manager.log(f"步骤5开始: 翻译 {len(segments)} 个段落")
        
        # 报告开始进度
        if progress_callback:
            progress_callback(5, "步骤5: 文本翻译", 0, f"开始翻译 {len(segments)} 个段落...", 0, len(segments))
        
        try:
            # 使用批量翻译
            result = self._batch_translate_with_qwen(segments, output_manager.task_dir, output_manager, progress_callback)
            
            if not result["success"]:
                output_manager.log(f"步骤5失败: {result.get('error', '未知错误')}")
                return result
            
            # 保存翻译结果到OutputManager指定的路径
            translation_file = output_manager.get_file_path(StepNumbers.STEP_5, "translation")
            llm_interaction_file = output_manager.get_file_path(StepNumbers.STEP_5, "llm_interaction")
            
            # 保存翻译文本
            with open(translation_file, 'w', encoding='utf-8') as f:
                for i, segment in enumerate(result["translated_segments"]):
                    f.write(f"Segment {i+1} ({segment['start']:.3f}s - {segment['end']:.3f}s):\n")
                    f.write(f"原文: {segment.get('original_text', segment.get('text', ''))}\n")
                    f.write(f"译文: {segment.get('translated_text', '')}\n\n")
            
            # LLM交互记录已在_batch_translate_with_qwen中生成，这里不需要重复生成
            
            # 更新结果
            result["translation_file"] = translation_file
            result["llm_interaction_file"] = llm_interaction_file
            
            output_manager.log(f"步骤5完成: 翻译完成，{len(result['translated_segments'])} 个段落")
            return result
            
        except Exception as e:
            self.logger.error(f"翻译失败: {e}")
            output_manager.log(f"步骤5失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "translated_segments": []
            }
    
    def _batch_translate_with_qwen(self, segments: List[Dict[str, Any]], 
                                  output_dir: Optional[str] = None, 
                                  output_manager: Optional[OutputManager] = None,
                                  progress_callback=None) -> Dict[str, Any]:
        """
        使用Qwen进行批量翻译
        
        根据配置选择重试策略：
        - simple: 简单重试策略（现有逻辑）
        - adaptive: 自适应降级重试策略（新逻辑）
        
        Args:
            segments: 音频段落列表
            output_dir: 输出目录
            output_manager: 输出管理器
            progress_callback: 进度回调函数
            
        Returns:
            翻译结果字典
        """
        if self.retry_strategy == "adaptive":
            return self._batch_translate_adaptive(segments, output_manager, progress_callback)
        else:
            return self._batch_translate_simple(segments, output_manager, progress_callback)
    
    def _batch_translate_simple(self, segments: List[Dict[str, Any]], output_manager: Optional[OutputManager] = None, progress_callback=None) -> Dict[str, Any]:
        """
        使用Qwen进行批量翻译（简单重试策略）
        
        这是原有的重试逻辑：
        - 固定批量大小处理所有段落
        - 失败时在解析阶段重试最多3次
        - 如果仍然失败，使用修复策略补全
        """
        try:
            # 分批处理，每批max_batch_size个段落
            batch_size = self.max_batch_size
            all_translated_segments = []
            total_batches = (len(segments) + batch_size - 1) // batch_size
            
            self.logger.info(f"开始分批翻译，总共 {len(segments)} 个段落，分成 {total_batches} 批处理")
            
            for batch_idx in range(0, len(segments), batch_size):
                batch_segments = segments[batch_idx:batch_idx + batch_size]
                batch_num = batch_idx // batch_size + 1
                
                self.logger.info(f"处理第 {batch_num}/{total_batches} 批，包含 {len(batch_segments)} 个段落")
                
                # 报告批次进度
                if progress_callback:
                    completed_segments = len(all_translated_segments)
                    progress_pct = (completed_segments / len(segments)) * 100 if len(segments) > 0 else 0
                    progress_callback(5, "步骤5: 文本翻译", progress_pct, f"翻译中 ({completed_segments}/{len(segments)})", completed_segments, len(segments))
                
                # 构建当前批次的翻译prompt
                prompt = self._create_batch_translation_prompt(batch_segments)
                
                self.logger.info(f"发送第 {batch_num} 批翻译请求到{self.model_version}...")
                messages = [{"role": "user", "content": prompt}]
                
                # 调用API
                completion = self.translator.chat.completions.create(
                    model=self.translation_model,
                    messages=messages,
                    stream=False,
                    temperature=0.1  # 稍微提高创造性，但保持一致性
                )
                
                # 获取翻译结果
                response_text = completion.choices[0].message.content.strip()
                self.logger.info(f"第 {batch_num} 批翻译成功，响应长度: {len(response_text)} 字符")
                
                # 记录LLM交互（仅记录第一批的完整交互）
                if batch_num == 1:
                    self._log_llm_interaction(
                        prompt, 
                        response_text, 
                        None, 
                        output_manager, 
                        batch_segments,
                        batch_num=batch_num,
                        attempt_num=1,
                        success=True
                    )
                
                # 解析当前批次的翻译结果（包含内部重试逻辑）
                batch_translated_segments = self._parse_batch_translation_result(response_text, batch_segments)
                all_translated_segments.extend(batch_translated_segments)
                
                # 清理内存
                import gc
                gc.collect()
            
            # 生成翻译报告
            translation_report = self._generate_batch_translation_report(segments, all_translated_segments)
            
            result = {
                "success": True,
                "total_segments": len(segments),
                "translated_count": len(all_translated_segments),
                "translated_segments": all_translated_segments,
                "translation_report": translation_report,
                "output_dir": None,
                "method": "batch_qwen"
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Qwen批量翻译失败: {e}")
            # 返回错误，不再回退到逐个翻译
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "translated_segments": []
            }
    
    def _batch_translate_adaptive(self, segments: List[Dict[str, Any]], output_manager: Optional[OutputManager] = None, progress_callback=None) -> Dict[str, Any]:
        """
        使用Qwen进行批量翻译（自适应降级重试策略）
        
        新的重试逻辑：
        - 每次尝试处理 min(剩余数量, MAX_BATCH_SIZE) 个段落
        - 失败时对当前批次进行二分降级
        - 降级到1个段落时，最多重试3次
        """
        all_translated_segments = []
        remaining_segments = segments.copy()
        batch_count = 0
        
        while remaining_segments:
            batch_count += 1
            batch_size = min(len(remaining_segments), self.max_batch_size)
            current_batch = remaining_segments[:batch_size]
            
            self.logger.info(f"批次 {batch_count}: 尝试翻译 {batch_size} 个段落")
            
            # 尝试翻译当前批次
            result = self._translate_single_batch(current_batch, output_manager, batch_count)
            
            if result['success']:
                # 成功：接受全部结果
                translated_count = len(result['translated_segments'])
                all_translated_segments.extend(result['translated_segments'])
                remaining_segments = remaining_segments[translated_count:]
                self.logger.info(f"✅ 批次 {batch_count} 成功: {translated_count} 个段落, 剩余 {len(remaining_segments)} 个")
                
                # 报告进度
                if progress_callback:
                    completed_segments = len(all_translated_segments)
                    progress_pct = (completed_segments / len(segments)) * 100 if len(segments) > 0 else 0
                    progress_callback(5, "步骤5: 文本翻译", progress_pct, f"翻译中 ({completed_segments}/{len(segments)})", completed_segments, len(segments))
            else:
                # 失败：使用降级策略
                self.logger.warning(f"❌ 批次 {batch_count} 失败，开始降级处理")
                degraded_result = self._translate_with_degradation(
                    current_batch, 
                    output_manager, 
                    batch_count
                )
                
                translated_count = len(degraded_result['translated_segments'])
                all_translated_segments.extend(degraded_result['translated_segments'])
                remaining_segments = remaining_segments[translated_count:]
                self.logger.info(f"✅ 降级完成: {translated_count} 个段落, 剩余 {len(remaining_segments)} 个")
                
                # 报告进度
                if progress_callback:
                    completed_segments = len(all_translated_segments)
                    progress_pct = (completed_segments / len(segments)) * 100 if len(segments) > 0 else 0
                    progress_callback(5, "步骤5: 文本翻译", progress_pct, f"翻译中 ({completed_segments}/{len(segments)})", completed_segments, len(segments))
        
        # 生成翻译报告
        translation_report = self._generate_batch_translation_report(segments, all_translated_segments)
        
        return {
            "success": True,
            "total_segments": len(segments),
            "translated_segments": len(all_translated_segments),
            "translated_segments": all_translated_segments,
            "translation_report": translation_report,
            "output_dir": None,
            "method": "batch_qwen_adaptive"
        }
    
    def _create_batch_translation_prompt(self, segments: List[Dict[str, Any]], is_retry: bool = False, attempt_num: int = 1) -> str:
        """
        创建批量翻译的prompt（强化版本）
        
        Args:
            segments: 音频段落列表
            is_retry: 是否为重试请求
            attempt_num: 重试次数
            
        Returns:
            批量翻译prompt
        """
        # 获取翻译配置
        source_lang = self.translation_config.get("source_language", "en")
        target_lang = self.translation_config.get("target_language", "zh")
        
        # 语言代码到显示名称的映射
        language_display_names = {
            "zh": "中文",
            "en": "英文"
        }
        
        # 获取源语言和目标语言的显示名称
        source_lang_display = language_display_names.get(source_lang, "英文")
        target_lang_display = language_display_names.get(target_lang, "中文")
        
        # 构建分段文本（带编号）
        segment_texts = []
        for i, segment in enumerate(segments, 1):
            text = segment.get("text", "").strip()
            if text:
                segment_texts.append(f"段落{i}: {text}")
        
        segments_text = "\n\n".join(segment_texts)
        
        # 构建基础提示词
        base_prompt = f"""请将以下{len(segments)}个{source_lang_display}段落翻译成{target_lang_display}，使用自然流畅的{target_lang_display}表达。

**输出格式**：JSON数组，每个元素包含：
- id: 段落编号（从1开始）
- snippet: 原文前10个字符（用于验证对齐）
- translation: 翻译内容

**示例**：
[
  {{"id": 1, "snippet": "Hello, how", "translation": "你好，你好吗？"}},
  {{"id": 2, "snippet": "I am fine,", "translation": "我很好，谢谢。"}}
]

**严格要求**：
1. 必须返回{len(segments)}个翻译对象，不多不少
2. id 必须连续：1, 2, 3, ..., {len(segments)}
3. snippet 必须准确复制原文的前10个字符
4. 不要合并任何段落，不要跳过任何段落
5. 每个段落必须独立翻译

{segments_text}

"""
        
        # 如果是重试，添加重试说明
        if is_retry:
            retry_prompt = f"""{base_prompt}

**重试说明**（第{attempt_num}次重试）：
之前的翻译结果验证失败，请严格按照要求重新翻译。
必须返回{len(segments)}个翻译对象，每个对象包含正确的id、snippet和translation字段。

请仔细检查：
1. 是否每个段落都有对应的翻译对象
2. id是否连续：1, 2, 3, ..., {len(segments)}
3. snippet是否准确复制原文的前10个字符
4. 是否没有合并任何段落
5. 返回的JSON数组长度是否为{len(segments)}

请重新翻译："""
            return retry_prompt
        
        return base_prompt
    
    def _log_llm_interaction(self, request: str, response: str, output_dir: Optional[str], output_manager: Optional[OutputManager] = None, segments: List[Dict[str, Any]] = None, current_audio_file: str = None, batch_num: int = 1, attempt_num: int = 1, success: bool = True, failure_reason: str = None):
        """
        记录与LLM的完整交互内容（请求+响应）
        
        Args:
            request: 发送给LLM的请求内容
            response: LLM返回的响应内容
            output_dir: 输出目录
            segments: 音频段落列表，用于推断原始文件名
            batch_num: 批次号
            attempt_num: 尝试次数
            success: 是否成功
            failure_reason: 失败原因
        """
        try:
            import time
            
            # 确定输出路径
            if output_manager:
                # 使用OutputManager生成路径
                log_file_path = output_manager.get_file_path(step=StepNumbers.STEP_5, file_type='llm_interaction')
            elif output_dir:
                log_file_path = os.path.join(output_dir, "05_llm_interaction.txt")
            else:
                self.logger.warning("无法确定输出路径，跳过LLM交互记录")
                return
            
            # 构建日志内容
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            segment_count = len(segments) if segments else 0
            
            log_content = f"""{'='*80}
=== 批次 {batch_num} - 尝试 {attempt_num} ({segment_count} 个段落) ===
时间: {timestamp}

【请求】
{request}

【响应】
{response[:2000]}{'...(已截断)' if len(response) > 2000 else ''}

"""
            
            if success:
                log_content += "【成功】✅ 批次翻译成功\n"
            else:
                log_content += f"【失败原因】❌ {failure_reason}\n"
            
            log_content += f"\n{'='*80}\n\n"
            
            # 追加写入日志文件
            with open(log_file_path, 'a', encoding='utf-8') as f:
                f.write(log_content)
            
            self.logger.info(f"LLM交互记录已追加: {log_file_path}")
            
        except Exception as e:
            self.logger.error(f"记录LLM交互失败: {e}")
    
    def _parse_batch_translation_result(self, response_text: str, 
                                       original_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        解析批量翻译结果（带重试机制）
        
        Args:
            response_text: LLM响应文本
            original_segments: 原始段落列表
            
        Returns:
            翻译后的段落列表
        """
        return self._parse_batch_translation_result_with_retry(response_text, original_segments, max_retries=3)
    
    def _parse_batch_translation_result_with_retry(self, response_text: str, 
                                                  original_segments: List[Dict[str, Any]], 
                                                  max_retries: int = 3) -> List[Dict[str, Any]]:
        """
        解析批量翻译结果，支持重试机制
        
        Args:
            response_text: LLM响应文本
            original_segments: 原始段落列表
            max_retries: 最大重试次数
            
        Returns:
            翻译后的段落列表
        """
        expected_count = len(original_segments)
        current_response = response_text
        
        for attempt in range(max_retries + 1):
            try:
                import re
                import json
                
                # 提取JSON数组部分
                json_match = re.search(r'\[.*\]', current_response, re.DOTALL)
                if json_match:
                    json_text = json_match.group(0)
                    try:
                        translation_results = json.loads(json_text)
                    except json.JSONDecodeError as e:
                        # JSON解析失败，尝试修复格式问题
                        self.logger.warning(f"JSON解析失败，尝试修复格式问题: {e}")
                        translation_results = self._extract_translation_results(current_response)
                else:
                    raise ValueError("无法从响应中提取JSON数组")
                
                # 验证数组长度
                actual_count = len(translation_results)
                if actual_count == expected_count:
                    self.logger.info(f"翻译结果数量匹配：{actual_count}/{expected_count}")
                    return self._build_translated_segments(translation_results, original_segments)
                else:
                    self.logger.warning(f"翻译结果数量不匹配：{actual_count}/{expected_count}，尝试{attempt + 1}/{max_retries + 1}")
                    
                    if attempt < max_retries:
                        # 重新请求翻译
                        self.logger.info(f"重新请求翻译，第{attempt + 2}次尝试...")
                        current_response = self._retry_translation(original_segments, attempt + 1)
                    else:
                        # 最后一次尝试失败，使用修复策略
                        self.logger.error(f"重试{max_retries}次后仍然不匹配，使用修复策略")
                        return self._fix_translation_mismatch(translation_results, original_segments)
                        
            except Exception as e:
                self.logger.error(f"解析翻译结果失败（尝试{attempt + 1}）：{e}")
                if attempt < max_retries:
                    current_response = self._retry_translation(original_segments, attempt + 1)
                else:
                    return self._fallback_translation(original_segments)
        
        return self._fallback_translation(original_segments)
    
    def _extract_translation_results(self, response_text: str) -> List[str]:
        """
        从LLM响应中提取翻译结果（处理JSON解析失败的情况）
        
        Args:
            response_text: LLM响应文本
            
        Returns:
            翻译结果列表
        """
        import re
        import json
        
        try:
            # 方法1：尝试匹配多个独立的JSON数组 (优先处理)
            json_arrays = re.findall(r'\[.*?\]', response_text, re.DOTALL)
            if json_arrays:
                results = []
                for array_text in json_arrays:
                    try:
                        array_result = json.loads(array_text)
                        if isinstance(array_result, list):
                            results.extend(array_result)
                        else:
                            results.append(array_result)
                    except json.JSONDecodeError:
                        continue
                
                if results:
                    return results
            
            # 方法2：尝试匹配单个JSON数组
            json_match = re.search(r'\[.*?\]', response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
                try:
                    result = json.loads(json_text)
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    pass
            
            # 方法3：尝试从文本中提取引号内容
            quoted_texts = re.findall(r'"([^"]*)"', response_text)
            if quoted_texts:
                return quoted_texts
            
            self.logger.warning("无法从响应中提取翻译结果")
            return []
            
        except Exception as e:
            self.logger.error(f"提取翻译结果失败: {e}")
            return []
    
    def _retry_translation(self, segments: List[Dict[str, Any]], attempt_num: int) -> str:
        """重新请求翻译"""
        try:
            retry_prompt = self._create_batch_translation_prompt(segments, is_retry=True, attempt_num=attempt_num)
            
            # 使用正确的 translator 属性
            messages = [{"role": "user", "content": retry_prompt}]
            
            completion = self.translator.chat.completions.create(
                model=self.translation_model,
                messages=messages,
                stream=False,
                temperature=0.1
            )
            
            response = completion.choices[0].message.content.strip()
            
            # 记录重试交互
            self._log_llm_interaction(retry_prompt, response, None, None, segments, retry_num=attempt_num)
            
            return response
        except Exception as e:
            self.logger.error(f"重试翻译失败：{e}")
            raise
    
    def _build_translated_segments(self, translation_results: List[str], original_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建翻译后的段落列表"""
        translated_segments = []
        for i, segment in enumerate(original_segments):
            translated_text = translation_results[i] if i < len(translation_results) else segment.get("text", "")
            
            translated_segment = {
                **segment,
                "original_text": segment.get("text", ""),
                "translated_text": translated_text,
                "translation_info": {
                    "method": "batch_qwen",
                    "segment_id": i + 1
                },
                "start_time": segment.get("start", 0.0),
                "end_time": segment.get("end", 0.0),
                "duration": segment.get("end", 0.0) - segment.get("start", 0.0)
            }
            translated_segments.append(translated_segment)
        
        return translated_segments
    
    def _fix_translation_mismatch(self, translation_results: List[str], original_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """修复翻译结果数量不匹配"""
        expected_count = len(original_segments)
        actual_count = len(translation_results)
        
        if actual_count < expected_count:
            # 翻译结果不足，为缺失的分段使用原文
            missing_count = expected_count - actual_count
            self.logger.warning(f"翻译结果不足{missing_count}个，为最后{missing_count}个分段使用原文")
            
            # 补充缺失的翻译结果
            for i in range(missing_count):
                segment_index = expected_count - missing_count + i
                original_text = original_segments[segment_index].get("text", "")
                translation_results.append(original_text)
        
        elif actual_count > expected_count:
            # 翻译结果过多，截取前面的结果
            self.logger.warning(f"翻译结果过多{actual_count - expected_count}个，截取前{expected_count}个")
            translation_results = translation_results[:expected_count]
        
        return self._build_translated_segments(translation_results, original_segments)
    
    def _fallback_translation(self, original_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """回退翻译策略"""
        self.logger.warning("使用回退翻译策略：所有分段使用原文")
        translated_segments = []
        for i, segment in enumerate(original_segments):
            translated_segment = {
                **segment,
                "original_text": segment.get("text", ""),
                "translated_text": segment.get("text", ""),
                "translation_info": {
                    "method": "fallback",
                    "segment_id": i + 1
                },
                "start_time": segment.get("start", 0.0),
                "end_time": segment.get("end", 0.0),
                "duration": segment.get("end", 0.0) - segment.get("start", 0.0)
            }
            translated_segments.append(translated_segment)
        
        return translated_segments
    
    
    def _generate_batch_translation_report(self, original_segments: List[Dict[str, Any]], 
                                         translated_segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        生成批量翻译报告
        
        Args:
            original_segments: 原始段落列表
            translated_segments: 翻译后段落列表
            
        Returns:
            翻译报告
        """
        total_segments = len(original_segments)
        successful_translations = len(translated_segments)
        
        # 计算文本长度统计
        original_lengths = [len(seg.get("text", "")) for seg in original_segments]
        translated_lengths = [len(seg.get("translated_text", "")) for seg in translated_segments]
        
        report = {
            "total_segments": total_segments,
            "successful_translations": successful_translations,
            "success_rate": successful_translations / total_segments if total_segments > 0 else 0,
            "average_original_length": sum(original_lengths) / len(original_lengths) if original_lengths else 0,
            "average_translated_length": sum(translated_lengths) / len(translated_lengths) if translated_lengths else 0,
            "translation_model": self.translation_model,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "method": "batch"
        }
        
        return report
    
    
    
    
    
    
    
    def _save_translation_result(self, segment: Dict[str, Any], output_dir: str, index: int):
        """保存翻译结果到文件"""
        try:
            # 创建翻译结果文件
            result_file = os.path.join(output_dir, f"translation_{index:02d}.json")
            
            result_data = {
                "segment_id": index,
                "original_text": segment.get("original_text", ""),
                "translated_text": segment.get("translated_text", ""),
                "start_time": segment.get("start_time", 0),
                "end_time": segment.get("end_time", 0),
                "duration": segment.get("duration", 0),
                "translation_info": segment.get("translation_info", {})
            }
            
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"翻译结果已保存: {result_file}")
            
        except Exception as e:
            self.logger.error(f"保存翻译结果失败: {e}")
    
    def _translate_single_batch(self, segments, output_manager, batch_num):
        """
        翻译单个批次（不含重试，仅验证结果）
        
        Returns:
            Dict: {
                'success': bool,
                'translated_segments': List[Dict],
                'batch_size': int
            }
        """
        try:
            # 创建翻译prompt
            prompt = self._create_batch_translation_prompt(segments, is_retry=False, attempt_num=0)
            
            # 调用LLM
            messages = [{"role": "user", "content": prompt}]
            completion = self.translator.chat.completions.create(
                model=self.translation_model,
                messages=messages,
                stream=False,
                temperature=0.1
            )
            
            response_text = completion.choices[0].message.content.strip()
            
            # 解析结果（简化版，不含重试）
            result = self._parse_translation_response(response_text, segments)
            
            # 验证结果数量
            if len(result) == len(segments):
                # 记录成功的LLM交互
                if output_manager:
                    self._log_llm_interaction(
                        prompt, 
                        response_text, 
                        None, 
                        output_manager, 
                        segments,
                        batch_num=batch_num,
                        attempt_num=1,
                        success=True
                    )
                return {
                    'success': True,
                    'translated_segments': result,
                    'batch_size': len(segments)
                }
            else:
                failure_reason = f"结果数量不匹配: 返回 {len(result)} 个，期望 {len(segments)} 个"
                self.logger.warning(failure_reason)
                # 记录失败的LLM交互
                if output_manager:
                    self._log_llm_interaction(
                        prompt, 
                        response_text, 
                        None, 
                        output_manager, 
                        segments,
                        batch_num=batch_num,
                        attempt_num=1,
                        success=False,
                        failure_reason=failure_reason
                    )
                # 对于单批次翻译，如果数量不匹配，返回失败
                # 让调用方决定是否进行降级重试
                return {
                    'success': False,
                    'translated_segments': [],
                    'batch_size': 0
                }
            
        except Exception as e:
            self.logger.error(f"批次翻译失败: {e}")
            return {
                'success': False,
                'translated_segments': [],
                'batch_size': 0
            }
    
    def _translate_with_degradation(self, segments, output_manager, batch_num):
        """
        使用降级策略翻译（N → N/2 → N/4 → ... → 1）
        
        Returns:
            Dict: {
                'translated_segments': List[Dict],
                'final_batch_size': int
            }
        """
        N = len(segments)
        current_size = N
        degradation_attempt = 0
        max_degradation_attempts = 10  # 防止无限循环
        
        while current_size >= 1 and degradation_attempt < max_degradation_attempts:
            degradation_attempt += 1
            sub_batch = segments[:current_size]
            
            self.logger.info(f"降级尝试 {degradation_attempt}: 从 {len(segments)} 降级到 {current_size} 个段落")
            
            try:
                # 创建重试prompt
                prompt = self._create_batch_translation_prompt(
                    sub_batch, 
                    is_retry=True, 
                    attempt_num=degradation_attempt
                )
                
                # 调用LLM
                messages = [{"role": "user", "content": prompt}]
                completion = self.translator.chat.completions.create(
                    model=self.translation_model,
                    messages=messages,
                    stream=False,
                    temperature=0.1
                )
                
                response_text = completion.choices[0].message.content.strip()
                
                # 解析结果
                result = self._parse_translation_response(response_text, sub_batch)
                
                # 验证结果数量
                if len(result) == len(sub_batch):
                    # 记录成功的LLM交互
                    if output_manager:
                        self._log_llm_interaction(
                            prompt, 
                            response_text, 
                            None, 
                            output_manager, 
                            sub_batch,
                            batch_num=batch_num,
                            attempt_num=degradation_attempt + 1,
                            success=True
                        )
                    self.logger.info(f"✅ 降级成功: 批量 {current_size}")
                    return {
                        'translated_segments': result,
                        'final_batch_size': current_size
                    }
                else:
                    failure_reason = f"结果数量不匹配: 返回 {len(result)} 个，期望 {len(sub_batch)} 个"
                    self.logger.warning(f"❌ 批量 {current_size} 结果不匹配: {len(result)}/{len(sub_batch)}")
                    # 记录失败的LLM交互
                    if output_manager:
                        self._log_llm_interaction(
                            prompt, 
                            response_text, 
                            None, 
                            output_manager, 
                            sub_batch,
                            batch_num=batch_num,
                            attempt_num=degradation_attempt + 1,
                            success=False,
                            failure_reason=failure_reason
                        )
                    # 继续降级
                    current_size = current_size // 2 if current_size > 1 else 1
                    
            except Exception as e:
                self.logger.error(f"降级翻译异常: {e}")
                current_size = current_size // 2 if current_size > 1 else 1
        
        # 如果达到最大重试次数，使用单段落重试
        if degradation_attempt >= max_degradation_attempts:
            self.logger.warning(f"达到最大降级尝试次数 ({max_degradation_attempts})，切换到单段落重试")
            return self._translate_single_segment_with_retry(segments[0], output_manager)
        
        # 降到1个段落，使用特殊重试逻辑
        self.logger.warning("降级到单个段落，使用特殊重试")
        return self._translate_single_segment_with_retry(segments[0], output_manager)
    
    def _translate_single_segment_with_retry(self, segment, output_manager):
        """
        翻译单个段落，最多重试single_segment_retries次
        
        Returns:
            Dict: {
                'translated_segments': List[Dict],
                'final_batch_size': 1
            }
        """
        max_retries = self.single_segment_retries
        
        for attempt in range(max_retries):
            try:
                self.logger.info(f"单段落翻译尝试 {attempt + 1}/{max_retries}")
                
                # 创建单段落翻译prompt
                prompt = self._create_batch_translation_prompt(
                    [segment], 
                    is_retry=True, 
                    attempt_num=attempt + 1
                )
                
                # 调用LLM
                messages = [{"role": "user", "content": prompt}]
                completion = self.translator.chat.completions.create(
                    model=self.translation_model,
                    messages=messages,
                    stream=False,
                    temperature=0.1
                )
                
                response_text = completion.choices[0].message.content.strip()
                
                
                # 解析结果
                result = self._parse_translation_response(response_text, [segment])
                
                if len(result) == 1:
                    # 记录成功的LLM交互
                    if output_manager:
                        self._log_llm_interaction(
                            prompt, 
                            response_text, 
                            None, 
                            output_manager, 
                            [segment],
                            batch_num=999,  # 特殊批次号表示单段落重试
                            attempt_num=attempt + 1,
                            success=True
                        )
                    self.logger.info(f"✅ 单段落翻译成功")
                    return {
                        'translated_segments': result,
                        'final_batch_size': 1
                    }
                else:
                    # 记录失败的LLM交互
                    failure_reason = f"单段落翻译结果数量不匹配: 返回 {len(result)} 个，期望 1 个"
                    if output_manager:
                        self._log_llm_interaction(
                            prompt, 
                            response_text, 
                            None, 
                            output_manager, 
                            [segment],
                            batch_num=999,  # 特殊批次号表示单段落重试
                            attempt_num=attempt + 1,
                            success=False,
                            failure_reason=failure_reason
                        )
            except Exception as e:
                self.logger.error(f"单段落翻译尝试 {attempt + 1} 失败: {e}")
        
        # 全部失败，使用原文
        self.logger.error(f"段落 {segment.get('segment_id', '?')} 翻译彻底失败，使用原文")
        fallback_segment = {
            **segment,
            "original_text": segment.get("text", ""),
            "translated_text": segment.get("text", ""),
            "translation_info": {
                "method": "fallback",
                "reason": "single_segment_retry_failed",
                "attempts": max_retries
            }
        }
        
        return {
            'translated_segments': [fallback_segment],
            'final_batch_size': 1
        }
    
    def _snippet_matches(self, llm_snippet: str, original_snippet: str) -> bool:
        """
        验证 LLM 返回的原文摘要是否与实际原文匹配
        
        使用宽松匹配规则：
        - 忽略大小写
        - 忽略标点符号
        - 允许部分匹配（至少50%字符相同，或者LLM snippet是原文的前缀）
        """
        import re
        
        # 移除标点和空格，转小写
        def normalize(text):
            text = re.sub(r'[^\w]', '', text)
            return text.lower()
        
        llm_norm = normalize(llm_snippet)
        orig_norm = normalize(original_snippet)
        
        if not llm_norm or not orig_norm:
            return False
        
        # 如果LLM snippet是原文的前缀，直接通过
        if orig_norm.startswith(llm_norm):
            return True
        
        # 计算相似度
        min_len = min(len(llm_norm), len(orig_norm))
        max_len = max(len(llm_norm), len(orig_norm))
        
        if max_len == 0:
            return False
        
        # 计算匹配字符数
        matches = sum(1 for i in range(min_len) if llm_norm[i] == orig_norm[i])
        similarity = matches / max_len
        
        # 降低阈值到50%，或者如果LLM snippet明显更短，使用更宽松的阈值
        if len(llm_norm) < len(orig_norm) * 0.8:  # LLM snippet明显更短
            return similarity >= 0.5
        else:
            return similarity >= 0.6
    
    def _parse_translation_response(self, response_text, original_segments):
        """
        解析翻译响应（增强版，带内容验证）
        
        Returns:
            List[Dict]: 翻译结果列表，只包含LLM实际返回且验证通过的结果
        """
        try:
            import re
            import json
            
            # 提取JSON数组
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if not json_match:
                self.logger.error("无法从响应中提取JSON数组")
                return []
            
            json_text = json_match.group(0)
            translation_results = json.loads(json_text)
            
            if not isinstance(translation_results, list):
                self.logger.error("解析结果不是数组")
                return []
            
            # 验证并构建翻译结果
            translated_segments = []
            validation_errors = []
            
            for i, result in enumerate(translation_results):
                # 基本结构验证
                if not isinstance(result, dict):
                    validation_errors.append(f"索引{i}: 不是对象")
                    continue
                
                if 'id' not in result or 'snippet' not in result or 'translation' not in result:
                    validation_errors.append(f"索引{i}: 缺少必需字段")
                    continue
                
                result_id = result['id']
                result_snippet = result['snippet']
                result_translation = result['translation']
                
                # ID 验证：必须连续
                expected_id = i + 1
                if result_id != expected_id:
                    validation_errors.append(
                        f"ID不连续: 期望{expected_id}，实际{result_id}"
                    )
                    continue
                
                # 原文摘要验证
                if result_id <= len(original_segments):
                    original_text = original_segments[result_id - 1].get("text", "").strip()
                    original_snippet = original_text[:10]  # 使用前10个字符
                    
                    # 计算相似度（简单字符匹配）
                    # 允许 LLM 返回更长的 snippet，只要前10个字符匹配即可
                    llm_snippet_truncated = result_snippet[:10]
                    if not self._snippet_matches(llm_snippet_truncated, original_snippet):
                        validation_errors.append(
                            f"ID {result_id}: 原文摘要不匹配\n"
                            f"  期望: {original_snippet[:30]}...\n"
                            f"  实际: {result_snippet[:30]}...\n"
                            f"  截断后: {llm_snippet_truncated[:30]}..."
                        )
                        continue
                    
                    # 验证通过，构建结果
                    translated_segments.append({
                        **original_segments[result_id - 1],
                        'translated_text': result_translation
                    })
                else:
                    validation_errors.append(f"ID {result_id} 超出范围")
            
            # 记录验证错误
            if validation_errors:
                self.logger.warning(
                    f"翻译验证发现 {len(validation_errors)} 个错误:\n" +
                    "\n".join(validation_errors)
                )
            
            # 如果验证通过的数量与原始段落数量一致，返回结果
            if len(translated_segments) == len(original_segments):
                self.logger.info(f"✅ 翻译验证通过: {len(translated_segments)} 个段落")
                return translated_segments
            else:
                self.logger.error(
                    f"❌ 翻译验证失败: 通过 {len(translated_segments)} 个，"
                    f"期望 {len(original_segments)} 个"
                )
                return []
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON解析失败: {e}")
            return []
        except Exception as e:
            self.logger.error(f"解析翻译结果失败: {e}")
            return []

