#!/bin/bash

# 翻译任务监控脚本 - 每小时报告一次进度

# 获取脚本所在目录的绝对路径，然后回到项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOG_FILE="${PROJECT_ROOT}/data/logs/system_2025-11-03_15-38-09.log"
TASK_DIR="${PROJECT_ROOT}/data/outputs/2025-11-03_15-38-09_How I use LLMs"

echo "🔍 翻译任务监控脚本"
echo "日志文件: $LOG_FILE"
echo "任务目录: $TASK_DIR"
echo "=================================="
echo ""

while true; do
    # 检查进程是否还在运行
    PROCESS=$(ps aux | grep "media_translation_cli.py.*How I use LLMs" | grep -v grep)
    
    if [ -z "$PROCESS" ]; then
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "📊 任务状态报告 - $(date '+%Y-%m-%d %H:%M:%S')"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "✅ 任务已完成或已终止"
        echo ""
        
        # 检查是否有最终输出文件
        if [ -f "$TASK_DIR/09_translated.wav" ] || [ -f "$TASK_DIR/09_translated.mp4" ]; then
            echo "✅ 找到最终输出文件:"
            ls -lh "$TASK_DIR/09_translated"* 2>/dev/null
            echo ""
            echo "🎉 翻译任务成功完成！"
        else
            echo "⚠️  未找到最终输出文件，请检查日志"
        fi
        
        # 显示最后50行日志
        echo ""
        echo "📝 最新日志信息:"
        tail -50 "$LOG_FILE" | grep -E "(完成|失败|✅|❌|步骤|进度)" | tail -20
        
        break
    fi
    
    # 显示当前状态
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 任务状态报告 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 进程信息
    PROCESS_INFO=$(ps aux | grep "media_translation_cli.py.*How I use LLMs" | grep -v grep | awk '{print "进程ID: " $2 ", CPU: " $3 "%, 内存: " $4 "%, 运行时间: " $10}')
    echo "🔄 任务状态: 运行中"
    echo "   $PROCESS_INFO"
    echo ""
    
    # 检查日志中的进度
    echo "📝 当前进度:"
    tail -100 "$LOG_FILE" | grep -E "(步骤|完成|✅|❌|识别|翻译|克隆|合并|最终)" | tail -10 | sed 's/^/   /'
    echo ""
    
    # 检查已生成的文件
    if [ -d "$TASK_DIR" ]; then
        echo "📁 已生成的文件:"
        ls -lh "$TASK_DIR"/*.wav "$TASK_DIR"/*.txt "$TASK_DIR"/*.json 2>/dev/null | awk '{print "   " $9 " (" $5 ")"}' | tail -10
        echo ""
        
        # 检查关键步骤文件
        if [ -f "$TASK_DIR/02_vocals.wav" ]; then
            echo "   ✅ 步骤2完成: 音频分离"
        fi
        if [ -f "$TASK_DIR/04_segments_json.json" ]; then
            echo "   ✅ 步骤4完成: 语音识别"
        fi
        if [ -f "$TASK_DIR/05_translation.txt" ]; then
            echo "   ✅ 步骤5完成: 文本翻译"
        fi
        if [ -d "$TASK_DIR/cloned_audio" ] && [ "$(ls -1 $TASK_DIR/cloned_audio/*.wav 2>/dev/null | wc -l)" -gt 0 ]; then
            CLONED_COUNT=$(ls -1 "$TASK_DIR/cloned_audio"/*.wav 2>/dev/null | wc -l)
            echo "   🔄 步骤7进行中: 音色克隆 ($CLONED_COUNT 个片段)"
        fi
        if [ -f "$TASK_DIR/08_final_voice.wav" ]; then
            echo "   ✅ 步骤8完成: 音频合并"
        fi
        if [ -f "$TASK_DIR/09_translated.wav" ]; then
            echo "   ✅ 步骤9完成: 最终输出"
        fi
    fi
    
    echo ""
    echo "⏰ 下次检查时间: $(date -d '+1 hour' '+%Y-%m-%d %H:%M:%S')"
    echo ""
    
    # 等待1小时
    sleep 3600
done


