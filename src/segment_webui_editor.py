"""
分段编辑 WebUI 模块
提供分段编辑的UI组件和相关功能
"""

import os
import json
import logging
import html
from typing import Dict, Any, List, Tuple, Optional
import gradio as gr
from .segment_editor import load_segments, validate_segment_data, save_segments, split_segment, find_words_in_time_range, rebuild_text_from_words
from .output_manager import OutputManager, StepNumbers

logger = logging.getLogger(__name__)


def generate_segments_table_html(table_data_list: List[Dict[str, Any]], selected_indices: List[int] = None) -> str:
    """
    生成HTML表格（不包含复选框列）
    
    Args:
        table_data_list: 表格数据（字典列表）
        selected_indices: 选中的行索引列表（可选，已废弃，保留以兼容旧代码）
    
    Returns:
        HTML字符串
    """
    if selected_indices is None:
        selected_indices = []
    
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
    .segments-table td {
        padding: 10px 8px;
        border: 1px solid #ddd;
        vertical-align: top;
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
        checked = "checked" if i in selected_indices else ""
        html += f'''
                <tr data-row-index="{i}">
                    <td style="text-align: center;">
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
        <!-- 隐藏的input用于存储选中索引，供Python端解析 -->
        <input type="hidden" id="selected_indices_hidden" value="[]" data-selected-indices="">
    </div>
    <script>
    (function() {
        console.log('[SegmentEditor] JavaScript同步脚本开始加载...');
        
        // 同步复选框状态到Gradio State（通过隐藏的Textbox）
        function syncCheckboxStates() {
            const checkboxes = document.querySelectorAll('.segment-checkbox');
            const selectedIndices = [];
            checkboxes.forEach((cb, index) => {
                // 使用data-index属性而不是索引，因为索引可能不准确
                const dataIndex = cb.getAttribute('data-index');
                if (cb.checked && dataIndex !== null) {
                    selectedIndices.push(parseInt(dataIndex));
                }
            });
            
            console.log('[SegmentEditor] 当前选中的索引:', selectedIndices);
            
            // 方法1: 更新HTML表格中的隐藏input（最可靠，始终在DOM中）
            const hiddenInput = document.getElementById('selected_indices_hidden');
            if (hiddenInput) {
                const jsonValue = JSON.stringify(selectedIndices);
                hiddenInput.value = jsonValue;
                hiddenInput.setAttribute('data-selected-indices', jsonValue);
                console.log('[SegmentEditor] ✅ 已更新隐藏input值:', jsonValue);
            } else {
                console.warn('[SegmentEditor] 未找到隐藏input #selected_indices_hidden');
            }
            
            // 方法2: 通过隐藏的Textbox更新State（Gradio限制的变通方法，备用方案）
            // 优先通过elem_id查找selected_indices_sync（最可靠）
            let syncInput = null;
            const elemById = document.getElementById('selected_indices_sync');
            if (elemById) {
                syncInput = elemById.querySelector('textarea, input[type="text"]');
                if (syncInput) {
                    console.log('[SegmentEditor] ✅ 找到同步Textbox (通过elem_id)');
                } else {
                    // 尝试直接使用elemById作为input
                    if (elemById.tagName === 'TEXTAREA' || elemById.tagName === 'INPUT') {
                        syncInput = elemById;
                        console.log('[SegmentEditor] ✅ 找到同步Textbox (ID元素本身就是input)');
                    }
                }
            }
            
            // 如果通过elem_id找不到，尝试查找所有隐藏的input，且值为JSON数组格式
            if (!syncInput) {
                const allInputs = Array.from(document.querySelectorAll('textarea, input[type="text"]'));
                for (const input of allInputs) {
                    const parent = input.closest('.gradio-textbox, .gradio-component');
                    if (parent) {
                        const parentStyle = window.getComputedStyle(parent);
                        const isHidden = parentStyle.display === 'none' || 
                                        parentStyle.visibility === 'hidden' ||
                                        parent.style.display === 'none';
                        
                        if (isHidden) {
                            // 检查值是否为JSON数组格式（包括空数组[]）
                            const value = input.value.trim();
                            if (value === '[]' || (value.startsWith('[') && value.endsWith(']'))) {
                                syncInput = input;
                                console.log('[SegmentEditor] 找到同步Textbox (方法1)');
                                break;
                            }
                        }
                    }
                }
            }
            
            // 方法3: 如果找不到，尝试查找所有隐藏的textarea，使用第一个
            if (!syncInput) {
                const allInputs = Array.from(document.querySelectorAll('textarea, input[type="text"]'));
                const hiddenInputs = allInputs.filter(input => {
                    const parent = input.closest('.gradio-textbox, .gradio-component');
                    if (!parent) return false;
                    const style = window.getComputedStyle(parent);
                    return style.display === 'none' || style.visibility === 'hidden';
                });
                if (hiddenInputs.length > 0) {
                    // 优先选择值为[]或JSON数组格式的
                    const jsonInputs = hiddenInputs.filter(input => {
                        const value = input.value.trim();
                        return value === '[]' || (value.startsWith('[') && value.endsWith(']'));
                    });
                    syncInput = jsonInputs.length > 0 ? jsonInputs[0] : hiddenInputs[0];
                    console.log('[SegmentEditor] 找到同步Textbox (方法2)');
                }
            }
            
            if (syncInput) {
                const jsonValue = JSON.stringify(selectedIndices);
                const oldValue = syncInput.value;
                syncInput.value = jsonValue;
                console.log('[SegmentEditor] 更新同步Textbox值:', {
                    oldValue: oldValue,
                    newValue: jsonValue
                });
                
                // 触发多个事件以确保Gradio捕获到变化
                syncInput.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                syncInput.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                syncInput.dispatchEvent(new Event('blur', { bubbles: true, cancelable: true }));
                
                // 尝试触发原生事件处理器
                if (syncInput.oninput) {
                    try {
                        syncInput.oninput(new Event('input', { bubbles: true }));
                    } catch (e) {
                        // 忽略错误
                    }
                }
                if (syncInput.onchange) {
                    try {
                        syncInput.onchange(new Event('change', { bubbles: true }));
                    } catch (e) {
                        // 忽略错误
                    }
                }
                
                // 尝试触发Gradio的内部更新
                try {
                    const gradioComponent = syncInput.closest('.gradio-component');
                    if (gradioComponent) {
                        gradioComponent.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
                        gradioComponent.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
                    }
                } catch (e) {
                    // 忽略错误
                }
                
                // 尝试直接调用Gradio的更新方法
                try {
                    const gradioApp = window.__gradio_mode__ || window.gradio;
                    if (gradioApp && gradioApp.update) {
                        gradioApp.update();
                    }
                } catch (e) {
                    // 忽略错误
                }
            } else {
                console.warn('[SegmentEditor] 未找到同步Textbox，选中状态可能无法同步');
                console.log('[SegmentEditor] 调试信息: 总共找到', allInputs.length, '个输入框');
            }
            
            // 也触发自定义事件作为备用
            const event = new CustomEvent('segmentIndicesChanged', {
                detail: { indices: selectedIndices },
                bubbles: true
            });
            document.dispatchEvent(event);
            console.log('[SegmentEditor] 已触发自定义事件 segmentIndicesChanged');
        }
        
        // 监听复选框变化
        document.addEventListener('change', function(e) {
            if (e.target.classList.contains('segment-checkbox')) {
                console.log('[SegmentEditor] 复选框状态改变:', e.target.getAttribute('data-index'), '->', e.target.checked);
                syncCheckboxStates();
            }
        }, true);
        
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
        
        // 初始化时同步一次（延迟执行，确保DOM已加载）
        setTimeout(function() {
            console.log('[SegmentEditor] 初始化同步复选框状态...');
            syncCheckboxStates();
        }, 500);
        
        // 定期同步（防止状态丢失）
        setInterval(function() {
            syncCheckboxStates();
        }, 2000);
        
        console.log('[SegmentEditor] JavaScript同步脚本加载完成');
    })();
    </script>'''
    
    return html


def parse_html_table_data(html_content: str) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    从HTML表格中解析数据（通过JavaScript提取）
    由于Gradio的限制，实际数据通过State维护，这里返回占位符
    
    Args:
        html_content: HTML内容
    
    Returns:
        (table_data, selected_indices) 元组
    """
    # 注意：实际数据从State读取，这里主要用于兼容性
    return [], []


def auto_split_segments_by_newlines(table_data: List[Dict[str, Any]], original_segments: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    自动检测文本中的换行符并拆分分段（支持多个换行符，递归处理）
    
    Args:
        table_data: 表格数据
        original_segments: 原始segments数据（用于获取words）
    
    Returns:
        (拆分后的表格数据, 拆分的分段数量)
    """
    if not table_data:
        return table_data, 0
    
    # 收集所有单词
    all_words = []
    if original_segments:
        for seg in original_segments:
            all_words.extend(seg.get('words', []))
    
    def split_segment_by_newline(row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        递归拆分单个分段（处理多个换行符）
        
        Returns:
            拆分后的分段列表
        """
        text = str(row.get('text', '')).strip()
        
        # 检测换行符（支持 \n, \r\n, \r）
        if '\n' not in text and '\r' not in text:
            # 没有换行符，直接返回
            return [{
                'index': 0,  # 临时值，后续会重新编号
                'seq_num': 0,  # 临时值，后续会重新编号
                'start_time': row.get('start_time', 0.0),
                'end_time': row.get('end_time', 0.0),
                'text': text,
                'speaker': str(row.get('speaker', '') or '')
            }]
        
        # 找到第一个连续换行符序列（合并连续的换行符为一个拆分点）
        import re
        # 匹配连续的换行符（\r\n, \n, \r 的任意组合）
        pattern = r'[\r\n]+'
        match = re.search(pattern, text)
        
        if not match:
            # 没有换行符，直接返回
            return [{
                'index': 0,
                'seq_num': 0,
                'start_time': row.get('start_time', 0.0),
                'end_time': row.get('end_time', 0.0),
                'text': text,
                'speaker': str(row.get('speaker', '') or '')
            }]
        
        newline_start_pos = match.start()  # 连续换行符序列的开始位置
        newline_end_pos = match.end()      # 连续换行符序列的结束位置（跳过所有连续换行符）
        
        if newline_start_pos <= 0 or newline_end_pos >= len(text):
            # 换行符在开头或结尾，只删除换行符，不拆分
            return [{
                'index': 0,
                'seq_num': 0,
                'start_time': row.get('start_time', 0.0),
                'end_time': row.get('end_time', 0.0),
                'text': text.replace('\n', '').replace('\r', '').strip(),
                'speaker': str(row.get('speaker', '') or '')
            }]
        
        # 使用连续换行符序列的结束位置作为拆分点（跳过所有连续换行符）
        newline_pos = newline_end_pos
        
        # 换行符在中间，可以拆分
        start_time = float(row.get('start_time', 0.0))
        end_time = float(row.get('end_time', 0.0))
        speaker_id = str(row.get('speaker', '') or '')
        
        # 根据时间范围查找 words
        words = find_words_in_time_range(all_words, start_time, end_time)
        
        if not words:
            # 没有words，无法精确拆分，保留原分段（删除换行符）
            logger.warning(f"[自动拆分] 分段 {row.get('seq_num', '?')} 没有words，无法拆分，保留原分段")
            return [{
                'index': 0,
                'seq_num': 0,
                'start_time': row.get('start_time', 0.0),
                'end_time': row.get('end_time', 0.0),
                'text': text.replace('\n', '').replace('\r', '').strip(),
                'speaker': speaker_id
            }]
        
        # 构建临时分段对象用于拆分
        temp_segment = {
            'start': start_time,
            'end': end_time,
            'text': text,  # 包含换行符的原始文本
            'words': words,
        }
        if speaker_id and speaker_id.strip():
            temp_segment['speaker_id'] = speaker_id.strip()
        
        try:
            # 使用文本位置拆分（换行符位置）
            seg_first, seg_second = split_segment(
                temp_segment, 
                split_text_position=newline_pos
            )
            
            # 删除换行符，清理文本
            first_text = seg_first.get('text', '').replace('\n', '').replace('\r', '').strip()
            second_text = seg_second.get('text', '').replace('\n', '').replace('\r', '').strip()
            
            if not first_text or not second_text:
                # 如果拆分后文本为空，保留原分段（删除换行符）
                logger.warning(f"[自动拆分] 分段 {row.get('seq_num', '?')} 拆分后文本为空，保留原分段")
                return [{
                    'index': 0,
                    'seq_num': 0,
                    'start_time': row.get('start_time', 0.0),
                    'end_time': row.get('end_time', 0.0),
                    'text': text.replace('\n', '').replace('\r', '').strip(),
                    'speaker': speaker_id
                }]
            
            # 创建第一个分段
            first_seg = {
                'index': 0,
                'seq_num': 0,
                'start_time': round(seg_first['start'], 3),
                'end_time': round(seg_first['end'], 3),
                'text': first_text,
                'speaker': str(seg_first.get('speaker_id', '') or '')
            }
            
            # 创建第二个分段
            second_seg = {
                'index': 0,
                'seq_num': 0,
                'start_time': round(seg_second['start'], 3),
                'end_time': round(seg_second['end'], 3),
                'text': second_text,
                'speaker': str(seg_second.get('speaker_id', '') or '')
            }
            
            logger.info(f"[自动拆分] 分段 {row.get('seq_num', '?')} 在位置 {newline_pos} 处拆分（已跳过连续换行符）")
            
            # 递归处理第二个分段（可能还有更多换行符）
            second_seg_list = split_segment_by_newline(second_seg)
            
            # 返回第一个分段和递归拆分后的第二个分段列表
            return [first_seg] + second_seg_list
            
        except Exception as e:
            # 拆分失败，保留原分段（删除换行符）
            logger.warning(f"[自动拆分] 分段 {row.get('seq_num', '?')} 拆分失败: {e}，保留原分段")
            return [{
                'index': 0,
                'seq_num': 0,
                'start_time': row.get('start_time', 0.0),
                'end_time': row.get('end_time', 0.0),
                'text': text.replace('\n', '').replace('\r', '').strip(),
                'speaker': speaker_id
            }]
    
    # 处理所有分段
    new_table_data = []
    split_count = 0
    
    for row in table_data:
        split_segments = split_segment_by_newline(row)
        if len(split_segments) > 1:
            split_count += len(split_segments) - 1  # 记录拆分次数
        new_table_data.extend(split_segments)
    
    # 重新编号
    for i in range(len(new_table_data)):
        new_table_data[i]['seq_num'] = i + 1
        new_table_data[i]['index'] = i
    
    return new_table_data, split_count


def apply_auto_split_wrapper(dataframe_data, segments_data: List[Dict[str, Any]]) -> Tuple[Any, List[Dict[str, Any]], str]:
    """
    应用自动拆分包装函数（适配 Gradio 接口）
    检测所有分段中的换行符并批量应用拆分
    
    Args:
        dataframe_data: Gradio Dataframe 返回的数据（可能是 pandas DataFrame 或列表）
        segments_data: 原始segments数据
    
    Returns:
        (new_dataframe_data, new_table_data, status_msg)
    """
    logger.info(f"[应用拆分] ========== 开始应用自动拆分 ==========")
    
    # 处理pandas DataFrame
    import pandas as pd
    if dataframe_data is not None:
        if isinstance(dataframe_data, pd.DataFrame):
            dataframe_list = dataframe_data.values.tolist()
            logger.info(f"[应用拆分] DataFrame转换为列表，长度: {len(dataframe_list)}")
        elif isinstance(dataframe_data, list):
            dataframe_list = dataframe_data
            logger.info(f"[应用拆分] 已经是列表格式，长度: {len(dataframe_list)}")
        else:
            logger.warning(f"[应用拆分] 未知的数据格式: {type(dataframe_data)}")
            dataframe_list = []
    else:
        dataframe_list = []
    
    if not dataframe_list:
        return dataframe_data, [], "❌ 没有分段数据"
    
    # 从Dataframe转换为表格数据
    table_data = convert_dataframe_to_table_data(dataframe_list) if dataframe_list else []
    
    if not table_data:
        return dataframe_data, [], "❌ 表格数据为空"
    
    # 检测是否有换行符
    has_newlines = False
    for row in table_data:
        text = str(row.get('text', '')).strip()
        if '\n' in text or '\r' in text:
            has_newlines = True
            break
    
    if not has_newlines:
        return dataframe_data, table_data, "ℹ️ 未检测到换行符，无需拆分"
    
    # 应用自动拆分
    try:
        new_table_data, split_count = auto_split_segments_by_newlines(table_data, segments_data)
        
        if split_count > 0:
            # 转换为Dataframe格式
            new_dataframe_data = convert_table_data_to_dataframe(new_table_data)
            # 如果原始输入是pandas DataFrame，则转换为DataFrame返回
            if isinstance(dataframe_data, pd.DataFrame):
                new_df = pd.DataFrame(new_dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
                status_msg = f"✅ 已拆分 {split_count} 个分段"
                logger.info(f"[应用拆分] 拆分完成，共拆分 {split_count} 个分段")
                return new_df, new_table_data, status_msg
            else:
                status_msg = f"✅ 已拆分 {split_count} 个分段"
                logger.info(f"[应用拆分] 拆分完成，共拆分 {split_count} 个分段")
                return new_dataframe_data, new_table_data, status_msg
        else:
            return dataframe_data, table_data, "ℹ️ 未检测到可拆分的换行符"
    except Exception as e:
        logger.error(f"[应用拆分] 拆分失败: {e}", exc_info=True)
        return dataframe_data, table_data, f"❌ 拆分失败: {str(e)}"


# 全局变量：用于防抖机制，记录最近处理的单元格
_last_processed_cell = None
_last_processed_time = 0
_processing_lock = False

def auto_split_on_cell_change(dataframe_data, segments_data: List[Dict[str, Any]]) -> Tuple[Any, List[Dict[str, Any]], str]:
    """
    单元格改变时自动拆分（方案B）
    当用户编辑包含换行符的单元格并失去焦点时，自动拆分该分段
    
    Args:
        dataframe_data: Gradio Dataframe 返回的数据（可能是 pandas DataFrame 或列表）
        segments_data: 原始segments数据
    
    Returns:
        (new_dataframe_data, new_table_data, status_msg)
    """
    global _last_processed_cell, _last_processed_time, _processing_lock
    
    # 防抖机制：如果正在处理或最近刚处理过，跳过
    import time
    current_time = time.time()
    if _processing_lock or (current_time - _last_processed_time < 0.5):
        return dataframe_data, [], ""
    
    logger.info(f"[自动拆分-单元格改变] ========== 检测单元格变化 ==========")
    
    # 处理pandas DataFrame
    import pandas as pd
    if dataframe_data is not None:
        if isinstance(dataframe_data, pd.DataFrame):
            dataframe_list = dataframe_data.values.tolist()
        elif isinstance(dataframe_data, list):
            dataframe_list = dataframe_data
        else:
            logger.warning(f"[自动拆分-单元格改变] 未知的数据格式: {type(dataframe_data)}")
            dataframe_list = []
    else:
        dataframe_list = []
    
    if not dataframe_list:
        return dataframe_data, [], ""
    
    # 从Dataframe转换为表格数据
    table_data = convert_dataframe_to_table_data(dataframe_list) if dataframe_list else []
    
    if not table_data:
        return dataframe_data, [], ""
    
    # 检测是否有换行符（只检测文本内容列）
    has_newlines = False
    changed_row_index = -1
    changed_row_text = ""
    
    for i, row in enumerate(table_data):
        text = str(row.get('text', '')).strip()
        if '\n' in text or '\r' in text:
            # 检查是否与上次处理的是同一个单元格（防抖）
            cell_key = f"{i}:{text[:50]}"  # 使用行索引和文本前50个字符作为唯一标识
            if cell_key == _last_processed_cell:
                logger.info(f"[自动拆分-单元格改变] 跳过重复处理的分段 {i+1}")
                return dataframe_data, table_data, ""
            
            has_newlines = True
            changed_row_index = i
            changed_row_text = text
            logger.info(f"[自动拆分-单元格改变] 检测到分段 {i+1} 包含换行符")
            break
    
    if not has_newlines:
        # 没有换行符，不进行拆分，静默返回
        return dataframe_data, table_data, ""
    
    # 设置处理锁，防止循环触发
    _processing_lock = True
    try:
        # 只处理包含换行符的分段
        changed_row = table_data[changed_row_index]
        split_segments, split_count = auto_split_segments_by_newlines([changed_row], segments_data)
        
        if split_count > 0 and len(split_segments) > 1:
            # 替换原分段为拆分后的分段
            new_table_data = table_data.copy()
            # 删除原分段
            new_table_data.pop(changed_row_index)
            # 插入拆分后的分段
            for j, seg in enumerate(split_segments):
                new_table_data.insert(changed_row_index + j, seg)
            
            # 重新编号
            for i in range(len(new_table_data)):
                new_table_data[i]['seq_num'] = i + 1
                new_table_data[i]['index'] = i
            
            # 转换为Dataframe格式
            new_dataframe_data = convert_table_data_to_dataframe(new_table_data)
            # 如果原始输入是pandas DataFrame，则转换为DataFrame返回
            if isinstance(dataframe_data, pd.DataFrame):
                new_df = pd.DataFrame(new_dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
                status_msg = f"✅ 自动拆分分段 {changed_row_index + 1}，拆分为 {len(split_segments)} 个分段"
                logger.info(f"[自动拆分-单元格改变] 拆分完成，分段 {changed_row_index + 1} 拆分为 {len(split_segments)} 个分段")
                
                # 更新防抖记录
                _last_processed_cell = None  # 拆分后清除，因为分段已经改变
                _last_processed_time = current_time
                
                return new_df, new_table_data, status_msg
            else:
                status_msg = f"✅ 自动拆分分段 {changed_row_index + 1}，拆分为 {len(split_segments)} 个分段"
                logger.info(f"[自动拆分-单元格改变] 拆分完成，分段 {changed_row_index + 1} 拆分为 {len(split_segments)} 个分段")
                
                # 更新防抖记录
                _last_processed_cell = None
                _last_processed_time = current_time
                
                return new_dataframe_data, new_table_data, status_msg
        else:
            # 拆分失败或没有拆分，删除换行符避免重复尝试
            logger.warning(f"[自动拆分-单元格改变] 分段 {changed_row_index + 1} 拆分失败，删除换行符")
            
            # 删除换行符并更新表格
            new_table_data = table_data.copy()
            new_table_data[changed_row_index]['text'] = changed_row_text.replace('\n', '').replace('\r', '').strip()
            
            # 转换为Dataframe格式
            new_dataframe_data = convert_table_data_to_dataframe(new_table_data)
            if isinstance(dataframe_data, pd.DataFrame):
                new_df = pd.DataFrame(new_dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
                
                # 更新防抖记录
                cell_key = f"{changed_row_index}:{new_table_data[changed_row_index]['text'][:50]}"
                _last_processed_cell = cell_key
                _last_processed_time = current_time
                
                return new_df, new_table_data, ""
            else:
                # 更新防抖记录
                cell_key = f"{changed_row_index}:{new_table_data[changed_row_index]['text'][:50]}"
                _last_processed_cell = cell_key
                _last_processed_time = current_time
                
                return new_dataframe_data, new_table_data, ""
    except Exception as e:
        logger.error(f"[自动拆分-单元格改变] 拆分失败: {e}", exc_info=True)
        # 拆分失败时删除换行符，避免重复尝试
        try:
            new_table_data = table_data.copy()
            new_table_data[changed_row_index]['text'] = changed_row_text.replace('\n', '').replace('\r', '').strip()
            new_dataframe_data = convert_table_data_to_dataframe(new_table_data)
            if isinstance(dataframe_data, pd.DataFrame):
                new_df = pd.DataFrame(new_dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
                _last_processed_cell = f"{changed_row_index}:{new_table_data[changed_row_index]['text'][:50]}"
                _last_processed_time = current_time
                return new_df, new_table_data, ""
            else:
                _last_processed_cell = f"{changed_row_index}:{new_table_data[changed_row_index]['text'][:50]}"
                _last_processed_time = current_time
                return new_dataframe_data, new_table_data, ""
        except:
            pass
        return dataframe_data, table_data, ""
    finally:
        # 释放处理锁
        _processing_lock = False


def convert_table_to_segments(table_data_list: List[Dict[str, Any]], original_segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    将表格数据（字典列表）转换为segments格式
    
    Args:
        table_data_list: 表格数据
        original_segments: 原始segments数据
    
    Returns:
        转换后的segments列表
    """
    if not table_data_list or not original_segments:
        return []
    
    new_segments = []
    for i, row in enumerate(table_data_list):
        if not isinstance(row, dict):
            continue
        
        seq_num = row.get('seq_num', i + 1)
        start_time = row.get('start_time', 0.0)
        end_time = row.get('end_time', 0.0)
        text = row.get('text', '')
        speaker_id = row.get('speaker', '')
        
        # 从所有原始分段中根据时间范围查找 words
        # 不依赖索引匹配，避免编辑后索引不对应的问题
        all_words = []
        for seg in original_segments:
            all_words.extend(seg.get('words', []))
        
        # 根据时间范围查找 words
        filtered_words = find_words_in_time_range(all_words, float(start_time), float(end_time))
        
        # 尝试通过时间戳匹配原始分段（用于获取 speaker_id）
        matched_original_seg = None
        for original_seg in original_segments:
            original_seg_start = original_seg.get('start', 0)
            original_seg_end = original_seg.get('end', 0)
            # 允许0.01秒的误差
            if abs(original_seg_start - float(start_time)) < 0.01 and abs(original_seg_end - float(end_time)) < 0.01:
                matched_original_seg = original_seg
                break
        
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
        elif matched_original_seg and 'speaker_id' in matched_original_seg:
            new_seg['speaker_id'] = matched_original_seg['speaker_id']
        
        new_segments.append(new_seg)
    
    return new_segments


def convert_table_data_to_dataframe(table_data_list: List[Dict[str, Any]]) -> List[List[Any]]:
    """
    将表格数据（字典列表）转换为Dataframe格式（列表的列表）
    
    Args:
        table_data_list: 表格数据（字典列表）
    
    Returns:
        Dataframe格式的数据（列表的列表）：[[序号, 开始时间, 结束时间, 文本内容, 说话人], ...]
    """
    dataframe_data = []
    for row in table_data_list:
        dataframe_data.append([
            row.get('seq_num', 0),
            row.get('start_time', 0.0),
            row.get('end_time', 0.0),
            row.get('text', ''),
            row.get('speaker', '')
        ])
    return dataframe_data


def convert_dataframe_to_table_data(dataframe_data: List[List[Any]]) -> List[Dict[str, Any]]:
    """
    将Dataframe格式（列表的列表）转换为表格数据（字典列表）
    
    Args:
        dataframe_data: Dataframe格式的数据（列表的列表）
    
    Returns:
        表格数据（字典列表）
    """
    table_data = []
    for i, row in enumerate(dataframe_data):
        if len(row) >= 5:
            # 去除文本的前导和尾随空格，确保表格中顶格显示
            text = str(row[3]).strip() if row[3] is not None else ''
            table_data.append({
                'index': i,
                'seq_num': int(row[0]) if isinstance(row[0], (int, float)) else i + 1,
                'start_time': float(row[1]) if isinstance(row[1], (int, float)) else 0.0,
                'end_time': float(row[2]) if isinstance(row[2], (int, float)) else 0.0,
                'text': text,
                'speaker': str(row[4]) if row[4] is not None else ''
            })
    return table_data


def load_segments_for_editing(task_dir_val: str, segments_file_val: str, media_path: str, mode: str, output_dir: str) -> Tuple[List[List[Any]], List[Dict[str, Any]], str, List[Dict[str, Any]], str]:
    """
    加载分段文件用于编辑
    
    Returns:
        (dataframe_data, table_data, segments_json, segments, status_msg)
    """
    if not task_dir_val or not segments_file_val:
        return (
            [],
            [],
            "",
            [],
            "无法加载分段文件"
        )
    
    try:
        import shutil
        
        # 读取分段文件
        segments = load_segments(segments_file_val)
        
        # 保存原始segments文件（用于后续恢复和验证）
        output_manager = OutputManager(media_path, output_dir)
        output_manager.task_dir = task_dir_val
        original_segments_file = os.path.join(task_dir_val, "04_segments_original.json")
        if not os.path.exists(original_segments_file):
            shutil.copy2(segments_file_val, original_segments_file)
            logger.info(f"已保存原始分段文件: {original_segments_file}")
        
        # 转换为表格数据格式
        table_data = []
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
        
        # 转换为Dataframe格式
        dataframe_data = convert_table_data_to_dataframe(table_data)
        
        # 转换为JSON字符串显示（高级选项）
        segments_json = json.dumps(segments, ensure_ascii=False, indent=2)
        
        return (
            dataframe_data,
            table_data,
            segments_json,
            segments,
            f"✅ 分段文件已加载，共 {len(segments)} 个片段"
        )
    except Exception as e:
        logger.error(f"加载分段文件失败: {e}")
        import traceback
        traceback.print_exc()
        return (
            [],
            [],
            "",
            [],
            f"❌ 加载分段文件失败: {str(e)}"
        )


def get_selected_indices_from_html(html_content: str) -> List[int]:
    """
    从HTML表格中提取选中的复选框索引
    由于Gradio的限制，实际通过JavaScript事件同步，这里返回空列表
    
    Args:
        html_content: HTML内容
    
    Returns:
        选中的索引列表
    """
    # 实际实现中，选中的索引通过JavaScript事件同步到State
    return []


def merge_selected_segments(table_data: List[Dict[str, Any]], selected_indices: List[int]) -> Tuple[List[Dict[str, Any]], str]:
    """
    合并选中的分段
    
    Args:
        table_data: 表格数据
        selected_indices: 选中的行索引列表
    
    Returns:
        (new_table_data, status_msg)
    """
    logger.info(f"merge_selected_segments: table_data长度={len(table_data) if table_data else 0}, selected_indices={selected_indices}")
    
    if not table_data:
        return [], "表格数据为空"
    
    if not selected_indices or len(selected_indices) < 2:
        return table_data, f"请至少选择2个分段进行合并（当前选中: {len(selected_indices) if selected_indices else 0}个）"
    
    # 按索引排序
    sorted_indices = sorted(selected_indices)
    logger.info(f"排序后的索引: {sorted_indices}")
    
    # 检查是否相邻
    for i in range(len(sorted_indices) - 1):
        if sorted_indices[i+1] - sorted_indices[i] != 1:
            return table_data, "只能合并相邻的分段，请选择连续的分段"
    
    # 合并第一个和最后一个分段
    first_idx = sorted_indices[0]
    last_idx = sorted_indices[-1]
    
    if first_idx >= len(table_data) or last_idx >= len(table_data):
        logger.error(f"索引越界: first_idx={first_idx}, last_idx={last_idx}, table_data长度={len(table_data)}")
        return table_data, f"索引越界错误: first_idx={first_idx}, last_idx={last_idx}, 表格长度={len(table_data)}"
    
    first_seg = table_data[first_idx]
    last_seg = table_data[last_idx]
    
    # 合并文本
    merged_text = ' '.join([table_data[i]['text'] for i in sorted_indices if i < len(table_data)])
    
    # 创建合并后的分段
    merged_seg = {
        'index': first_idx,
        'seq_num': first_seg['seq_num'],
        'start_time': first_seg['start_time'],
        'end_time': last_seg['end_time'],
        'text': merged_text,
        'speaker': str(first_seg.get('speaker') or '')
    }
    
    # 删除被合并的分段（从后往前删除，避免索引变化）
    new_table_data = table_data.copy()
    for idx in reversed(sorted_indices[1:]):  # 跳过第一个，删除其他的
        if 0 <= idx < len(new_table_data):
            new_table_data.pop(idx)
    
    # 替换第一个分段为合并后的分段
    if first_idx < len(new_table_data):
        new_table_data[first_idx] = merged_seg
    else:
        logger.error(f"替换分段时索引越界: first_idx={first_idx}, new_table_data长度={len(new_table_data)}")
        return table_data, "合并时发生错误：索引越界"
    
    # 重新编号
    for i in range(len(new_table_data)):
        new_table_data[i]['seq_num'] = i + 1
        new_table_data[i]['index'] = i
    
    logger.info(f"合并完成: 新表格长度={len(new_table_data)}")
    
    return new_table_data, f"✅ 成功合并 {len(sorted_indices)} 个分段"


def split_segment_func(table_data: List[Dict[str, Any]], selected_indices: List[int], split_method: str, split_time: float, split_text_search: str, original_segments: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """
    拆分分段
    
    Args:
        table_data: 表格数据
        selected_indices: 选中的行索引列表
        split_method: 拆分方式
        split_time: 拆分时间点
        split_text_search: 要搜索的文本片段（用于"按文本位置拆分"）
        original_segments: 原始segments数据
    
    Returns:
        (new_table_data, status_msg)
    """
    if not table_data:
        return [], "表格数据为空"
    
    if len(selected_indices) != 1:
        return table_data, f"请选择1个分段进行拆分（当前输入: {len(selected_indices)}个）。请输入单个分段编号，如：12"
    
    seg_idx = selected_indices[0]
    if seg_idx >= len(table_data):
        return table_data, "分段索引无效"
    
    seg = table_data[seg_idx]
    start_time = float(seg['start_time'])
    end_time = float(seg['end_time'])
    text = str(seg['text'])
    speaker_id = str(seg.get('speaker', '') or '')
    
    logger.info(f"[拆分分段] split_segment_func - seg_idx: {seg_idx}, table_data长度: {len(table_data)}, original_segments长度: {len(original_segments) if original_segments else 0}")
    logger.info(f"[拆分分段] split_segment_func - table_data[{seg_idx}] 时间: {start_time:.3f}s-{end_time:.3f}s, 文本: '{text[:50]}...'")
    
    # 直接从所有原始分段中根据时间范围查找 words
    # 不依赖索引匹配，避免编辑后索引不对应的问题
    all_words = []
    if original_segments:
        for seg_item in original_segments:
            all_words.extend(seg_item.get('words', []))
    
    # 根据时间范围过滤 words
    words = find_words_in_time_range(all_words, start_time, end_time)
    
    if not words:
        logger.warning(f"[拆分分段] split_segment_func - ⚠️ 未找到对应时间范围的 words，使用空列表")
        # 如果找不到 words，仍然可以拆分，但会使用文本拆分
        words = []
    
    # 构建临时分段对象用于拆分（直接使用 table_data 中的数据）
    temp_segment = {
        'start': start_time,
        'end': end_time,
        'text': text,
        'words': words,
    }
    
    # 保留 speaker_id（如果有）
    if speaker_id and speaker_id.strip():
        temp_segment['speaker_id'] = speaker_id.strip()
    
    logger.info(f"[拆分分段] split_segment_func - 使用 table_data 中的数据，找到 {len(words)} 个 words")
    
    # 使用segment_editor的拆分功能
    try:
        from .segment_editor import split_segment
        
        # 确定拆分点
        if split_method == "按时间点拆分":
            split_point = float(split_time)
            if split_point <= start_time or split_point >= end_time:
                return table_data, f"拆分时间点必须在 {start_time:.3f}s 和 {end_time:.3f}s 之间"
            # 使用时间点拆分（直接使用 table_data 中的数据）
            seg_first, seg_second = split_segment(temp_segment, split_time=split_point)
        else:  # 按文本位置拆分
            if not split_text_search or not split_text_search.strip():
                return table_data, "❌ 拆分文本不能为空，请保留至少一个字符作为第一段"
            # 直接使用搜索文本拆分（直接使用 table_data 中的数据）
            seg_first, seg_second = split_segment(temp_segment, split_text_search=split_text_search)
        
        # 构建新表格数据
        new_table_data = table_data.copy()
        
        # 替换原分段为第一个分段
        speaker_id_first = seg_first.get('speaker_id') or ''
        new_table_data[seg_idx] = {
            'index': seg_idx,
            'seq_num': seg_idx + 1,
            'start_time': round(seg_first['start'], 3),
            'end_time': round(seg_first['end'], 3),
            'text': seg_first['text'],
            'speaker': str(speaker_id_first) if speaker_id_first else ''
        }
        
        # 插入第二个分段
        speaker_id_second = seg_second.get('speaker_id') or ''
        new_table_data.insert(seg_idx + 1, {
            'index': seg_idx + 1,
            'seq_num': seg_idx + 2,
            'start_time': round(seg_second['start'], 3),
            'end_time': round(seg_second['end'], 3),
            'text': seg_second['text'],
            'speaker': str(speaker_id_second) if speaker_id_second else ''
        })
        
        # 重新编号
        for i in range(len(new_table_data)):
            new_table_data[i]['seq_num'] = i + 1
            new_table_data[i]['index'] = i
        
        return new_table_data, "✅ 分段拆分成功"
    except Exception as e:
        logger.error(f"拆分分段失败: {e}", exc_info=True)
        return table_data, f"❌ 拆分失败: {str(e)}"


def delete_selected_segments(table_data: List[Dict[str, Any]], selected_indices: List[int]) -> Tuple[List[Dict[str, Any]], str]:
    """
    删除选中的分段
    
    Args:
        table_data: 表格数据
        selected_indices: 选中的行索引列表
    
    Returns:
        (new_table_data, status_msg)
    """
    logger.info(f"[删除分段] table_data长度={len(table_data) if table_data else 0}, selected_indices={selected_indices}")
    
    if not table_data:
        return [], "表格数据为空"
    
    if not selected_indices:
        return table_data, "❌ 请选择要删除的分段。请输入分段编号，用逗号分隔，如：12,13"
    
    # 从后往前删除，避免索引变化
    new_table_data = table_data.copy()
    deleted_count = 0
    for idx in reversed(sorted(selected_indices)):
        if 0 <= idx < len(new_table_data):
            new_table_data.pop(idx)
            deleted_count += 1
    
    # 重新编号
    for i in range(len(new_table_data)):
        new_table_data[i]['seq_num'] = i + 1
        new_table_data[i]['index'] = i
    
    logger.info(f"[删除分段] 删除完成: 新表格长度={len(new_table_data)}")
    
    return new_table_data, f"✅ 成功删除 {deleted_count} 个分段"


def add_new_segment(table_data: List[Dict[str, Any]], start_time: float, end_time: float, text: str, original_segments: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
    """
    添加新分段
    
    Args:
        table_data: 表格数据
        start_time: 开始时间
        end_time: 结束时间
        text: 文本内容
        original_segments: 原始segments数据
    
    Returns:
        (new_table_data, status_msg)
    """
    logger.info(f"[添加分段] 开始时间={start_time}, 结束时间={end_time}, 文本长度={len(text) if text else 0}")
    
    if not text or not text.strip():
        return table_data, "❌ 文本内容不能为空"
    
    if float(end_time) <= float(start_time):
        return table_data, "❌ 结束时间必须大于开始时间"
    
    # 从原始segments中查找对应时间范围的单词
    all_words = []
    for seg in original_segments:
        all_words.extend(seg.get('words', []))
    
    words = find_words_in_time_range(all_words, float(start_time), float(end_time))
    
    # 如果找到单词，使用单词重建文本；否则使用用户输入的文本
    if words:
        auto_text = rebuild_text_from_words(words)
        if auto_text:
            text = auto_text
    
    # 添加到表格（按时间戳排序插入）
    new_table_data = table_data.copy()
    new_seg = {
        'index': len(new_table_data),  # 临时索引，后续会重新编号
        'seq_num': len(new_table_data) + 1,  # 临时序号，后续会重新编号
        'start_time': round(float(start_time), 3),
        'end_time': round(float(end_time), 3),
        'text': text.strip(),
        'speaker': ''  # 说话人（新分段默认无说话人）
    }
    
    # 找到按 start_time 排序的插入位置
    insert_idx = len(new_table_data)  # 默认插入到末尾
    for i, seg in enumerate(new_table_data):
        seg_start_time = float(seg.get('start_time', 0))
        if float(start_time) < seg_start_time:
            insert_idx = i
            break
    
    # 插入到正确位置
    new_table_data.insert(insert_idx, new_seg)
    logger.info(f"[添加分段] 插入位置: {insert_idx}, 新分段时间: {start_time:.3f}s-{end_time:.3f}s")
    
    # 重新编号
    for i in range(len(new_table_data)):
        new_table_data[i]['seq_num'] = i + 1
        new_table_data[i]['index'] = i
    
    logger.info(f"[添加分段] 添加完成: 新表格长度={len(new_table_data)}")
    
    return new_table_data, "✅ 新分段添加成功"


def save_segments_and_continue(
    table_data: List[Dict[str, Any]],
    segments_data_state: List[Dict[str, Any]],
    task_dir_val: str,
    segments_file_val: str,
    media: str,
    output_dir: str
) -> Tuple[bool, str]:
    """
    保存编辑后的分段
    
    Args:
        table_data: 表格数据
        segments_data_state: segments数据State
        task_dir_val: 任务目录
        segments_file_val: 分段文件路径
        media: 媒体文件路径
        output_dir: 输出目录
    
    Returns:
        (success, error_msg) 元组
    """
    if not task_dir_val or not segments_file_val:
        return False, "❌ 无法继续：缺少任务目录或分段文件路径"
    
    try:
        # 读取原始分段数据
        output_manager = OutputManager(media, output_dir)
        output_manager.task_dir = task_dir_val
        original_segments_file = os.path.join(task_dir_val, "04_segments_original.json")
        
        if not os.path.exists(original_segments_file):
            return False, f"❌ 无法继续：原始分段文件不存在: {original_segments_file}"
        
        original_segments = load_segments(original_segments_file)
        
        # 将表格数据转换为segments格式
        edited_segments = convert_table_to_segments(table_data, original_segments)
        
        if not edited_segments:
            return False, "❌ 分段数据为空"
        
        # 收集所有单词用于验证
        all_words = []
        for seg in original_segments:
            all_words.extend(seg.get('words', []))
        
        # 验证分段数据
        is_valid, error_msg = validate_segment_data(edited_segments, all_words)
        if not is_valid:
            return False, f"❌ 验证失败: {error_msg}"
        
        # 保存分段文件
        save_segments(edited_segments, output_manager, all_words)
        
        return True, "✅ 分段保存成功"
    except Exception as e:
        logger.error(f"保存分段失败: {e}")
        import traceback
        traceback.print_exc()
        return False, f"❌ 保存分段失败: {str(e)}"


# ============================================================================
# Gradio 包装函数（用于适配 Gradio 接口）
# ============================================================================

def find_text_position_in_segment(segment_text: str, search_text: str) -> Tuple[int, str]:
    """
    在分段文本中搜索文本片段，返回匹配位置的字符索引
    
    Args:
        segment_text: 分段文本
        search_text: 要搜索的文本片段（保留空格，要求完全匹配）
    
    Returns:
        (字符索引, 状态消息)
        如果找到匹配，返回该文本片段结束位置的字符索引
        如果找不到，返回 -1 和错误消息
    """
    if not search_text:
        return -1, "❌ 请输入要查找的文本片段"
    
    # 保留原始空格，不进行strip
    segment_text = str(segment_text)
    
    # 方法1: 精确匹配（包括空格）
    pos = segment_text.find(search_text)
    if pos != -1:
        # 返回文本片段结束位置的字符索引
        char_index = pos + len(search_text)
        return char_index, f"✅ 找到匹配文本，将在第 {char_index} 个字符后拆分"
    
    # 方法2: 忽略大小写匹配（保留空格）
    pos = segment_text.lower().find(search_text.lower())
    if pos != -1:
        char_index = pos + len(search_text)
        return char_index, f"✅ 找到匹配文本（忽略大小写），将在第 {char_index} 个字符后拆分"
    
    # 找不到匹配，直接报错
    return -1, f"❌ 未找到匹配的文本片段：\"{search_text}\"\n\n提示：\n- 请检查输入是否正确（包括空格）\n- 文本片段必须完全出现在分段文本中\n- 请从分段文本中复制准确的文本片段"


def parse_segment_indices_from_input(input_str: str) -> List[int]:
    """
    从输入框解析分段编号（用户输入的是显示编号，需要转换为索引）
    
    Args:
        input_str: 用户输入的字符串，如 "12,13" 或 "12"
    
    Returns:
        索引列表（从0开始），如 [11, 12]
    """
    if not input_str or not input_str.strip():
        return []
    try:
        # 分割逗号，去除空格
        parts = [p.strip() for p in input_str.split(',')]
        indices = []
        for part in parts:
            if part:
                # 用户输入的是显示编号（从1开始），需要转换为索引（从0开始）
                display_num = int(part)
                if display_num < 1:
                    logger.warning(f"[解析分段编号] 无效的分段编号: {display_num}（必须>=1）")
                    continue
                # 转换为索引（从0开始）
                index = display_num - 1
                indices.append(index)
        if indices:
            logger.info(f"[解析分段编号] 输入: '{input_str}' -> 索引: {indices}")
        return indices
    except ValueError as e:
        logger.error(f"[解析分段编号] 解析失败: {e}, 输入: '{input_str}'")
        return []
    except Exception as e:
        logger.error(f"[解析分段编号] 异常: {e}, 输入: '{input_str}'", exc_info=True)
        return []


def load_segments_for_editing_wrapper(task_dir_val: str, segments_file_val: str, media_path: str, mode: str, output_dir: str):
    """
    包装函数，适配 Gradio 接口
    
    Args:
        task_dir_val: 任务目录
        segments_file_val: 分段文件路径
        media_path: 媒体文件路径
        mode: 模式（"视频" 或 "音频"）
        output_dir: 输出目录
    
    Returns:
        Gradio 兼容的返回值元组
    """
    import time
    start_time = time.time()
    logger.info(f"[load_segments_for_editing_wrapper] 开始加载分段，task_dir: {task_dir_val}, segments_file: {segments_file_val}")
    
    if not task_dir_val or not segments_file_val:
        logger.warning(f"[load_segments_for_editing_wrapper] 参数为空: task_dir={task_dir_val}, segments_file={segments_file_val}")
        import pandas as pd
        empty_df = pd.DataFrame(columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
        return (
            empty_df,
            [],
            "",
            [],
            gr.update(visible=True),
            gr.update(visible=False),
            gr.update(visible=False),
            "❌ 无法加载分段：缺少任务目录或分段文件路径"
        )
    
    # 步骤1: 加载分段数据
    step1_start = time.time()
    try:
        dataframe_data, table_data, segments_json, segments, status_msg = load_segments_for_editing(
            task_dir_val, segments_file_val, media_path, mode, output_dir
        )
        step1_time = time.time() - step1_start
        logger.info(f"[load_segments_for_editing_wrapper] 步骤1-加载分段数据完成，耗时: {step1_time:.3f}秒，分段数量: {len(table_data)}")
        
        # 详细的诊断日志
        logger.info(f"[load_segments_for_editing_wrapper] 诊断信息 - table_data长度: {len(table_data) if table_data else 0}, dataframe_data长度: {len(dataframe_data) if dataframe_data else 0}")
        if table_data and len(table_data) > 0:
            logger.info(f"[load_segments_for_editing_wrapper] table_data前3行: {table_data[:3]}")
        if dataframe_data and len(dataframe_data) > 0:
            logger.info(f"[load_segments_for_editing_wrapper] dataframe_data前3行: {dataframe_data[:3]}")
    except Exception as e:
        logger.error(f"[load_segments_for_editing_wrapper] 加载分段数据失败: {e}", exc_info=True)
        import pandas as pd
        empty_df = pd.DataFrame(columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
        return (
            empty_df,
            [],
            "",
            [],
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            f"❌ 加载分段失败: {str(e)}"
        )
    
    # 步骤2: 转换为DataFrame（优化：只在需要时转换）
    step2_start = time.time()
    import pandas as pd
    
    # 如果 dataframe_data 为空但 table_data 有数据，从 table_data 重新生成
    if (not dataframe_data or len(dataframe_data) == 0) and table_data and len(table_data) > 0:
        logger.warning(f"[load_segments_for_editing_wrapper] dataframe_data为空，从table_data重新生成")
        dataframe_data = convert_table_data_to_dataframe(table_data)
        logger.info(f"[load_segments_for_editing_wrapper] 从table_data重新生成dataframe_data，长度: {len(dataframe_data)}")
    
    if dataframe_data and len(dataframe_data) > 0:
        try:
            df = pd.DataFrame(dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
            
            # 确保数据类型正确
            df["序号"] = pd.to_numeric(df["序号"], errors='coerce').astype('Int64')
            df["开始时间(秒)"] = pd.to_numeric(df["开始时间(秒)"], errors='coerce')
            df["结束时间(秒)"] = pd.to_numeric(df["结束时间(秒)"], errors='coerce')
            df["文本内容"] = df["文本内容"].astype(str)
            df["说话人"] = df["说话人"].astype(str)
            
            # 处理 None 值
            df["文本内容"] = df["文本内容"].replace('None', '').replace('nan', '')
            df["说话人"] = df["说话人"].replace('None', '').replace('nan', '')
            
            # 详细的诊断日志
            logger.info(f"[load_segments_for_editing_wrapper] DataFrame创建成功 - 形状: {df.shape}, 列名: {list(df.columns)}")
            logger.info(f"[load_segments_for_editing_wrapper] DataFrame数据类型: {df.dtypes.to_dict()}")
            if len(df) > 0:
                logger.info(f"[load_segments_for_editing_wrapper] DataFrame前3行:\n{df.head(3).to_string()}")
            
            # 验证 DataFrame 不为空
            if len(df) == 0:
                logger.error(f"[load_segments_for_editing_wrapper] ⚠️ DataFrame为空！dataframe_data长度: {len(dataframe_data)}, table_data长度: {len(table_data)}")
        except Exception as e:
            logger.error(f"[load_segments_for_editing_wrapper] DataFrame创建失败: {e}", exc_info=True)
            # 如果创建失败，尝试从 table_data 重新生成
            if table_data and len(table_data) > 0:
                logger.info(f"[load_segments_for_editing_wrapper] 尝试从table_data重新生成DataFrame")
                try:
                    dataframe_data = convert_table_data_to_dataframe(table_data)
                    df = pd.DataFrame(dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
                    df["序号"] = pd.to_numeric(df["序号"], errors='coerce').astype('Int64')
                    df["开始时间(秒)"] = pd.to_numeric(df["开始时间(秒)"], errors='coerce')
                    df["结束时间(秒)"] = pd.to_numeric(df["结束时间(秒)"], errors='coerce')
                    df["文本内容"] = df["文本内容"].astype(str).replace('None', '').replace('nan', '')
                    df["说话人"] = df["说话人"].astype(str).replace('None', '').replace('nan', '')
                    logger.info(f"[load_segments_for_editing_wrapper] 从table_data重新生成DataFrame成功，形状: {df.shape}")
                except Exception as e2:
                    logger.error(f"[load_segments_for_editing_wrapper] 从table_data重新生成DataFrame也失败: {e2}", exc_info=True)
                    df = pd.DataFrame(columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
            else:
                df = pd.DataFrame(columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
    else:
        logger.warning(f"[load_segments_for_editing_wrapper] ⚠️ dataframe_data为空，创建空DataFrame")
        df = pd.DataFrame(columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
    
    step2_time = time.time() - step2_start
    logger.info(f"[load_segments_for_editing_wrapper] 步骤2-转换为DataFrame完成，耗时: {step2_time:.3f}秒，DataFrame行数: {len(df)}")
    
    # 验证列名是否匹配
    expected_columns = ["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"]
    actual_columns = list(df.columns)
    if actual_columns != expected_columns:
        logger.error(f"[load_segments_for_editing_wrapper] ⚠️ 列名不匹配！期望: {expected_columns}, 实际: {actual_columns}")
        # 尝试修复列名
        if len(actual_columns) == len(expected_columns):
            df.columns = expected_columns
            logger.info(f"[load_segments_for_editing_wrapper] 已修复列名: {list(df.columns)}")
    else:
        logger.info(f"[load_segments_for_editing_wrapper] ✅ 列名匹配: {actual_columns}")
    
    # 步骤3: 查找媒体文件路径（优化：延迟初始化OutputManager）
    step3_start = time.time()
    audio_file = None
    video_update = gr.update(visible=False)
    
    try:
        # 对于视频模式，直接使用左上角已加载的 input_video 的值（media_path）
        # 这样浏览器会复用已经加载的视频，不会重复下载，节省流量
        if mode == "视频" and media_path:
            video_update = gr.update(value=media_path, visible=True)
            logger.info(f"[load_segments_for_editing_wrapper] 视频模式：使用已加载的视频路径")
        elif mode == "音频":
            # 只在音频模式下查找音频文件
            output_manager = OutputManager(media_path, output_dir)
            output_manager.task_dir = task_dir_val
            audio_file = output_manager.get_file_path(StepNumbers.STEP_1, "audio")
            if not os.path.exists(audio_file):
                audio_file = media_path if os.path.exists(media_path) else None
            logger.info(f"[load_segments_for_editing_wrapper] 音频模式：音频文件路径: {audio_file}")
    except Exception as e:
        logger.warning(f"[load_segments_for_editing_wrapper] 查找媒体文件路径时出错: {e}，继续执行")
    
    step3_time = time.time() - step3_start
    logger.info(f"[load_segments_for_editing_wrapper] 步骤3-查找媒体文件完成，耗时: {step3_time:.3f}秒")
    
    total_time = time.time() - start_time
    logger.info(f"[load_segments_for_editing_wrapper] 全部加载完成，总耗时: {total_time:.3f}秒，分段数量: {len(table_data)}, dataframe行数: {len(dataframe_data) if dataframe_data else 0}")
    
    return (
        df,  # Dataframe数据（pandas DataFrame）
        table_data,  # 表格数据State
        segments_json,  # JSON数据
        segments,  # 完整segments数据（用于State）
        gr.update(visible=True),  # 保存按钮可见
        gr.update(value=audio_file, visible=(mode == "音频" and audio_file)),  # 音频播放器
        video_update,  # 视频播放器（复用左上角的 input_video，避免重复加载）
        status_msg
    )


def merge_segments_wrapper(dataframe_data, merge_input_str: str):
    """
    合并分段包装函数（适配 Gradio 接口）
    
    Args:
        dataframe_data: Gradio Dataframe 返回的数据（可能是 pandas DataFrame 或列表）
        merge_input_str: 用户输入的分段编号字符串，如 "12,13"
    
    Returns:
        (new_dataframe_data, new_table_data, cleared_input, status_msg)
    """
    logger.info(f"[合并分段] ========== 开始合并分段 ==========")
    
    # 处理pandas DataFrame（Gradio Dataframe返回的是pandas DataFrame）
    import pandas as pd
    if dataframe_data is not None:
        if isinstance(dataframe_data, pd.DataFrame):
            # 转换为列表的列表
            dataframe_list = dataframe_data.values.tolist()
            logger.info(f"[合并分段] DataFrame转换为列表，长度: {len(dataframe_list)}")
        elif isinstance(dataframe_data, list):
            dataframe_list = dataframe_data
            logger.info(f"[合并分段] 已经是列表格式，长度: {len(dataframe_list)}")
        else:
            logger.warning(f"[合并分段] 未知的数据格式: {type(dataframe_data)}")
            dataframe_list = []
    else:
        dataframe_list = []
    
    logger.info(f"[合并分段] dataframe_data长度: {len(dataframe_list)}")
    logger.info(f"[合并分段] 输入的分段编号: '{merge_input_str}'")
    
    # 从Dataframe转换为表格数据
    table_data = convert_dataframe_to_table_data(dataframe_list) if dataframe_list else []
    
    # 从输入框解析分段编号
    selected_indices = parse_segment_indices_from_input(merge_input_str)
    
    if not selected_indices:
        # 如果没有输入或解析失败，返回错误信息
        error_msg = (
            "❌ 请输入要合并的分段编号（至少2个）。\n\n"
            "格式：用逗号分隔，如：12,13\n"
            "注意：输入的是表格中显示的分段编号（从1开始），不是索引。"
        )
        # 返回Dataframe格式（如果是DataFrame则返回DataFrame，否则返回列表）
        if isinstance(dataframe_data, pd.DataFrame):
            return dataframe_data, table_data, "", error_msg
        else:
            return dataframe_list, table_data, "", error_msg
    
    if len(selected_indices) < 2:
        # 如果少于2个，返回错误信息
        error_msg = (
            f"❌ 至少需要选择2个分段进行合并（当前输入: {len(selected_indices)}个）。\n\n"
            "格式：用逗号分隔，如：12,13"
        )
        # 返回Dataframe格式（如果是DataFrame则返回DataFrame，否则返回列表）
        if isinstance(dataframe_data, pd.DataFrame):
            return dataframe_data, table_data, "", error_msg
        else:
            return dataframe_list, table_data, "", error_msg
    
    # 执行合并
    new_table_data, status_msg = merge_selected_segments(table_data, selected_indices)
    # 转换为Dataframe格式
    new_dataframe_data = convert_table_data_to_dataframe(new_table_data)
    # 如果原始输入是pandas DataFrame，则转换为DataFrame返回
    if isinstance(dataframe_data, pd.DataFrame):
        new_df = pd.DataFrame(new_dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
        return new_df, new_table_data, "", status_msg  # 合并后清空输入框
    else:
        return new_dataframe_data, new_table_data, "", status_msg  # 合并后清空输入框


def split_segments_wrapper(dataframe_data, split_input_str: str, split_method: str, split_time: float, split_text_search: str, segments_data: List[Dict[str, Any]]):
    """
    拆分分段包装函数（适配 Gradio 接口）
    
    Args:
        dataframe_data: Gradio Dataframe 返回的数据（可能是 pandas DataFrame 或列表）
        split_input_str: 用户输入的分段编号字符串，如 "12"
        split_method: 拆分方式（"按时间点拆分" 或 "按文本位置拆分"）
        split_time: 拆分时间点（秒）
        split_text_search: 要搜索的文本片段（用于"按文本位置拆分"）
        segments_data: 原始segments数据
    
    Returns:
        (new_dataframe_data, new_table_data, cleared_input, status_msg)
    """
    logger.info(f"[拆分分段] ========== 开始拆分分段 ==========")
    
    # 处理pandas DataFrame（Gradio Dataframe返回的是pandas DataFrame）
    import pandas as pd
    if dataframe_data is not None:
        if isinstance(dataframe_data, pd.DataFrame):
            dataframe_list = dataframe_data.values.tolist()
            logger.info(f"[拆分分段] DataFrame转换为列表，长度: {len(dataframe_list)}")
        elif isinstance(dataframe_data, list):
            dataframe_list = dataframe_data
            logger.info(f"[拆分分段] 已经是列表格式，长度: {len(dataframe_list)}")
        else:
            logger.warning(f"[拆分分段] 未知的数据格式: {type(dataframe_data)}")
            dataframe_list = []
    else:
        dataframe_list = []
    
    logger.info(f"[拆分分段] dataframe_data长度: {len(dataframe_list)}")
    logger.info(f"[拆分分段] 输入的分段编号: '{split_input_str}'")
    logger.info(f"[拆分分段] 拆分方式: '{split_method}', 拆分时间点: {split_time}, 搜索文本: '{split_text_search}'")
    
    # 从Dataframe转换为表格数据
    table_data = convert_dataframe_to_table_data(dataframe_list) if dataframe_list else []
    
    # 从输入框解析分段编号
    selected_indices = parse_segment_indices_from_input(split_input_str)
    
    if not selected_indices:
        error_msg = (
            "❌ 请输入要拆分的分段编号。\n\n"
            "格式：单个分段编号，如：12"
        )
        if isinstance(dataframe_data, pd.DataFrame):
            return dataframe_data, table_data, "", error_msg
        else:
            return dataframe_list, table_data, "", error_msg
    
    if len(selected_indices) != 1:
        error_msg = (
            f"❌ 只能拆分1个分段（当前输入: {len(selected_indices)}个）。\n\n"
            "格式：单个分段编号，如：12"
        )
        if isinstance(dataframe_data, pd.DataFrame):
            return dataframe_data, table_data, "", error_msg
        else:
            return dataframe_list, table_data, "", error_msg
    
    # 如果是按文本位置拆分，需要验证搜索文本不为空
    if split_method == "按文本位置拆分":
        if not split_text_search or not split_text_search.strip():
            error_msg = "❌ 请输入要查找的文本片段"
            if isinstance(dataframe_data, pd.DataFrame):
                return dataframe_data, table_data, "", error_msg
            else:
                return dataframe_list, table_data, "", error_msg
        
        logger.info(f"[拆分分段] 使用搜索文本进行拆分: '{split_text_search}'")
    
    # 执行拆分（直接传递搜索文本）
    new_table_data, status_msg = split_segment_func(
        table_data, selected_indices, split_method, split_time, split_text_search, segments_data
    )
    
    # 转换为Dataframe格式
    new_dataframe_data = convert_table_data_to_dataframe(new_table_data)
    
    # 如果原始输入是pandas DataFrame，则转换为DataFrame返回
    if isinstance(dataframe_data, pd.DataFrame):
        new_df = pd.DataFrame(new_dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
        return new_df, new_table_data, "", status_msg  # 拆分后清空输入框
    else:
        return new_dataframe_data, new_table_data, "", status_msg  # 拆分后清空输入框


def show_split_dialog_wrapper(dataframe_data, split_input_str: str, split_method_val: str, segments_data: List[Dict[str, Any]] = None):
    """
    显示拆分对话框包装函数（适配 Gradio 接口）
    
    Args:
        dataframe_data: Gradio Dataframe 返回的数据（可能是 pandas DataFrame 或列表）
        split_input_str: 用户输入的分段编号字符串，如 "12"
        split_method_val: 拆分方式（"按时间点拆分" 或 "按文本位置拆分"）
        segments_data: 原始分段数据（用于获取原始文本，保留空格）
    
    Returns:
        (dialog_visible, time_input_update, text_pos_input_update, text_html, status_msg)
    """
    logger.info(f"[拆分分段] 显示对话框，输入的分段编号: '{split_input_str}', 拆分方式: '{split_method_val}'")
    
    # 处理pandas DataFrame（Gradio Dataframe返回的是pandas DataFrame）
    import pandas as pd
    if dataframe_data is not None:
        if isinstance(dataframe_data, pd.DataFrame):
            dataframe_list = dataframe_data.values.tolist()
        elif isinstance(dataframe_data, list):
            dataframe_list = dataframe_data
        else:
            dataframe_list = []
    else:
        dataframe_list = []
    
    # 从Dataframe转换为表格数据
    table_data = convert_dataframe_to_table_data(dataframe_list) if dataframe_list else []
    
    # 从输入框解析分段编号
    selected_indices = parse_segment_indices_from_input(split_input_str)
    
    if not selected_indices:
        # 根据拆分方式设置输入框可见性
        if split_method_val == "按时间点拆分":
            time_visible, text_visible = True, False
        else:
            time_visible, text_visible = False, True
        return (
            gr.update(visible=False),
            gr.update(value=0.0, visible=time_visible),
            gr.update(value="", visible=text_visible),
            "",
            f"❌ 请输入要拆分的分段编号。\n\n格式：单个分段编号，如：12"
        )
    
    if len(selected_indices) != 1:
        # 根据拆分方式设置输入框可见性
        if split_method_val == "按时间点拆分":
            time_visible, text_visible = True, False
        else:
            time_visible, text_visible = False, True
        return (
            gr.update(visible=False),
            gr.update(value=0.0, visible=time_visible),
            gr.update(value="", visible=text_visible),
            "",
            f"❌ 只能拆分1个分段（当前输入: {len(selected_indices)}个）。\n\n格式：单个分段编号，如：12"
        )
    
    seg_idx = selected_indices[0]
    if seg_idx >= len(table_data):
        # 根据拆分方式设置输入框可见性
        if split_method_val == "按时间点拆分":
            time_visible, text_visible = True, False
        else:
            time_visible, text_visible = False, True
        return (
            gr.update(visible=False),
            gr.update(value=0.0, visible=time_visible),
            gr.update(value="", visible=text_visible),
            "",
            f"❌ 分段索引无效（索引: {seg_idx}, 表格长度: {len(table_data)}）"
        )
    
    seg = table_data[seg_idx]
    start_time = float(seg['start_time'])
    end_time = float(seg['end_time'])
    
    # 直接使用 table_data 中的文本（用户看到的就是这个文本）
    # 不需要从 segments_data 中查找，避免索引不匹配的问题
    logger.info(f"[拆分分段] 显示对话框 - seg_idx: {seg_idx}, table_data长度: {len(table_data)}, segments_data长度: {len(segments_data) if segments_data else 0}")
    logger.info(f"[拆分分段] 显示对话框 - table_data[{seg_idx}] 时间: {start_time:.3f}s-{end_time:.3f}s, 文本: '{str(seg['text'])[:50]}...'")
    
    # 直接使用 table_data 中的文本
    text = str(seg['text']).strip()
    original_text = str(seg['text'])  # 保留原始文本（可能包含前导/尾随空格）用于编辑
    
    # 计算默认拆分点（中间点）
    default_split_time = (start_time + end_time) / 2
    # 使用原始文本作为文本框的初始值（用户可编辑）
    default_text_value = original_text
    
    # 根据拆分方式设置输入框可见性
    if split_method_val == "按时间点拆分":
        time_visible, text_visible = True, False
    else:
        time_visible, text_visible = False, True
    
    # 转义文本中的特殊字符，防止XSS攻击
    escaped_text = html.escape(text)
    
    # 生成可点击的文本HTML（现在主要用于显示分段文本，方便用户查看）
    text_html = f'''
    <div id="split-text-container-{seg_idx}" style="border: 1px solid #ddd; padding: 15px; border-radius: 4px; background-color: #f9f9f9;">
        <div style="margin-bottom: 10px; font-size: 12px; color: #666;">
            分段信息：开始时间 {start_time:.3f}s，结束时间 {end_time:.3f}s，文本长度 {len(text)} 字符
        </div>
        <div id="split-text-content-{seg_idx}" style="font-size: 14px; line-height: 1.6; white-space: pre-line; word-wrap: break-word; min-height: 60px; border: 1px solid #ccc; padding: 10px; background-color: white; border-radius: 3px; text-align: left;">
            {escaped_text}
        </div>
        <div style="margin-top: 10px; font-size: 12px; color: #666;">
            💡 提示：在下方"拆分文本"输入框中，删除不需要的部分，保留的部分将成为第一段
        </div>
    </div>
    <script>
    (function() {{
        const containerId = 'split-text-container-{seg_idx}';
        const contentId = 'split-text-content-{seg_idx}';
        
        // 等待DOM加载
        function initSplitText() {{
            const container = document.getElementById(containerId);
            const content = document.getElementById(contentId);
            
            if (!container || !content) {{
                setTimeout(initSplitText, 100);
                return;
            }}
            
            // 现在主要用于显示文本，不再需要点击选择功能
            // 文本搜索功能由用户在"拆分文本"输入框中输入文本片段来实现
        }}
        
        // 初始化
        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initSplitText);
        }} else {{
            initSplitText();
        }}
    }})();
    </script>
    '''
    
    return (
        gr.update(visible=True),
        gr.update(value=default_split_time, visible=time_visible),
        gr.update(value=default_text_value, visible=text_visible),
        text_html,
        f"✅ 准备拆分分段 {seg_idx + 1}\n开始时间: {start_time:.3f}s，结束时间: {end_time:.3f}s\n文本长度: {len(original_text)} 字符\n\n💡 提示：在下方文本框中，删除不需要的部分，保留的部分将成为第一段"
    )


def on_split_method_change(method: str):
    """
    根据拆分方式显示/隐藏相应的输入框
    
    Args:
        method: 拆分方式（"按时间点拆分" 或 "按文本位置拆分"）
    
    Returns:
        (text_display_update, time_input_update, text_pos_input_update)
    """
    if method == "按时间点拆分":
        return gr.update(visible=False), gr.update(visible=True), gr.update(visible=False)
    else:  # 按文本位置拆分
        return gr.update(visible=True), gr.update(visible=False), gr.update(visible=True)


def delete_segments_wrapper(dataframe_data, delete_input_str: str):
    """
    删除分段包装函数（适配 Gradio 接口）
    
    Args:
        dataframe_data: Gradio Dataframe 返回的数据（可能是 pandas DataFrame 或列表）
        delete_input_str: 用户输入的分段编号字符串，如 "12,13"
    
    Returns:
        (new_dataframe_data, new_table_data, cleared_input, status_msg)
    """
    logger.info(f"[删除分段] ========== 开始删除分段 ==========")
    
    # 处理pandas DataFrame（Gradio Dataframe返回的是pandas DataFrame）
    import pandas as pd
    if dataframe_data is not None:
        if isinstance(dataframe_data, pd.DataFrame):
            dataframe_list = dataframe_data.values.tolist()
            logger.info(f"[删除分段] DataFrame转换为列表，长度: {len(dataframe_list)}")
        elif isinstance(dataframe_data, list):
            dataframe_list = dataframe_data
            logger.info(f"[删除分段] 已经是列表格式，长度: {len(dataframe_list)}")
        else:
            logger.warning(f"[删除分段] 未知的数据格式: {type(dataframe_data)}")
            dataframe_list = []
    else:
        dataframe_list = []
    
    logger.info(f"[删除分段] dataframe_data长度: {len(dataframe_list)}")
    logger.info(f"[删除分段] 输入的分段编号: '{delete_input_str}'")
    
    # 从Dataframe转换为表格数据
    table_data = convert_dataframe_to_table_data(dataframe_list) if dataframe_list else []
    
    # 从输入框解析分段编号
    selected_indices = parse_segment_indices_from_input(delete_input_str)
    
    if not selected_indices:
        error_msg = (
            "❌ 请输入要删除的分段编号。\n\n"
            "格式：用逗号分隔，如：12,13"
        )
        if isinstance(dataframe_data, pd.DataFrame):
            return dataframe_data, table_data, "", error_msg
        else:
            return dataframe_list, table_data, "", error_msg
    
    # 执行删除
    new_table_data, status_msg = delete_selected_segments(table_data, selected_indices)
    
    # 转换为Dataframe格式
    new_dataframe_data = convert_table_data_to_dataframe(new_table_data)
    
    # 如果原始输入是pandas DataFrame，则转换为DataFrame返回
    if isinstance(dataframe_data, pd.DataFrame):
        new_df = pd.DataFrame(new_dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
        return new_df, new_table_data, "", status_msg  # 删除后清空输入框
    else:
        return new_dataframe_data, new_table_data, "", status_msg  # 删除后清空输入框


def add_segment_wrapper(dataframe_data, start_time: float, end_time: float, text: str, segments_data: List[Dict[str, Any]]):
    """
    添加分段包装函数（适配 Gradio 接口）
    
    Args:
        dataframe_data: Gradio Dataframe 返回的数据（可能是 pandas DataFrame 或列表）
        start_time: 开始时间（秒）
        end_time: 结束时间（秒）
        text: 文本内容
        segments_data: 原始segments数据
    
    Returns:
        (new_dataframe_data, new_table_data, cleared_inputs, status_msg)
    """
    logger.info(f"[添加分段] ========== 开始添加分段 ==========")
    
    # 处理pandas DataFrame（Gradio Dataframe返回的是pandas DataFrame）
    import pandas as pd
    if dataframe_data is not None:
        if isinstance(dataframe_data, pd.DataFrame):
            dataframe_list = dataframe_data.values.tolist()
            logger.info(f"[添加分段] DataFrame转换为列表，长度: {len(dataframe_list)}")
        elif isinstance(dataframe_data, list):
            dataframe_list = dataframe_data
            logger.info(f"[添加分段] 已经是列表格式，长度: {len(dataframe_list)}")
        else:
            logger.warning(f"[添加分段] 未知的数据格式: {type(dataframe_data)}")
            dataframe_list = []
    else:
        dataframe_list = []
    
    logger.info(f"[添加分段] dataframe_data长度: {len(dataframe_list)}")
    logger.info(f"[添加分段] 开始时间: {start_time}, 结束时间: {end_time}, 文本长度: {len(text) if text else 0}")
    
    # 从Dataframe转换为表格数据
    table_data = convert_dataframe_to_table_data(dataframe_list) if dataframe_list else []
    
    # 执行添加
    new_table_data, status_msg = add_new_segment(table_data, start_time, end_time, text, segments_data)
    
    # 转换为Dataframe格式
    new_dataframe_data = convert_table_data_to_dataframe(new_table_data)
    
    # 如果原始输入是pandas DataFrame，则转换为DataFrame返回
    if isinstance(dataframe_data, pd.DataFrame):
        new_df = pd.DataFrame(new_dataframe_data, columns=["序号", "开始时间(秒)", "结束时间(秒)", "文本内容", "说话人"])
        return new_df, new_table_data, status_msg  # 返回更新后的Dataframe和状态
    else:
        return new_dataframe_data, new_table_data, status_msg  # 返回更新后的Dataframe和状态

