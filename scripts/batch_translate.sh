#!/bin/bash

# 批量翻译脚本 - 支持模型预加载，顺序处理多个翻译任务

echo "🎬 批量翻译工具 - 支持模型预加载"
echo "=================================="

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

# 解析参数
PRELOAD_ONLY=false
PRELOAD_MODELS=true
FILES=()

while [[ $# -gt 0 ]]; do
    case $1 in
        --preload-only)
            PRELOAD_ONLY=true
            shift
            ;;
        --no-preload)
            PRELOAD_MODELS=false
            shift
            ;;
        --help|-h)
            echo "用法: $0 [选项] <文件1> [文件2] [文件3] ..."
            echo ""
            echo "选项:"
            echo "  --preload-only     仅预加载模型，不执行翻译"
            echo "  --no-preload       跳过模型预加载"
            echo "  --help, -h         显示帮助信息"
            echo ""
            echo "示例:"
            echo "  # 预加载模型"
            echo "  $0 --preload-only"
            echo ""
            echo "  # 批量翻译多个文件（自动预加载）"
            echo "  $0 file1.mp4 file2.mp4 file3.mp4 --source-lang en --target-lang zh"
            echo ""
            echo "  # 不预加载直接翻译"
            echo "  $0 --no-preload file1.mp4 --source-lang en --target-lang zh"
            exit 0
            ;;
        *)
            FILES+=("$1")
            shift
            ;;
    esac
done

# 如果只是预加载
if [ "$PRELOAD_ONLY" = true ]; then
    echo "🚀 仅预加载模型..."
    "${PROJECT_ROOT}/scripts/preload_models.sh"
    exit $?
fi

# 检查是否有文件
if [ ${#FILES[@]} -eq 0 ]; then
    echo "❌ 错误: 未指定要翻译的文件"
    echo "   使用 --help 查看帮助信息"
    exit 1
fi

# 提取翻译参数（--source-lang, --target-lang, --single-speaker等）
TRANSLATE_ARGS=()
for arg in "${FILES[@]}"; do
    if [[ "$arg" == --* ]]; then
        TRANSLATE_ARGS+=("$arg")
    fi
done

# 提取文件列表（排除翻译参数）
FILE_LIST=()
for arg in "${FILES[@]}"; do
    if [[ ! "$arg" == --* ]]; then
        FILE_LIST+=("$arg")
    fi
done

echo "📁 找到 ${#FILE_LIST[@]} 个文件需要翻译"
echo ""

# 步骤1: 预加载模型
if [ "$PRELOAD_MODELS" = true ]; then
    echo "🚀 步骤1: 预加载模型..."
    echo "-----------------------------------"
    "${PROJECT_ROOT}/scripts/preload_models.sh"
    PRELOAD_RESULT=$?
    echo ""
    
    if [ $PRELOAD_RESULT -eq 0 ]; then
        echo "✅ 模型预加载完成，后续任务将复用预加载的模型"
    else
        echo "⚠️  模型预加载部分失败，但可以继续执行翻译任务"
    fi
    echo ""
fi

# 步骤2: 顺序处理每个文件
echo "🎬 步骤2: 开始批量翻译..."
echo "=================================="
echo ""

SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_FILES=()

for i in "${!FILE_LIST[@]}"; do
    file="${FILE_LIST[$i]}"
    file_num=$((i + 1))
    total=${#FILE_LIST[@]}
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📹 任务 $file_num/$total: $(basename "$file")"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    # 执行翻译
    "${PROJECT_ROOT}/run_cli.sh" "$file" "${TRANSLATE_ARGS[@]}"
    TRANSLATE_RESULT=$?
    
    if [ $TRANSLATE_RESULT -eq 0 ]; then
        echo "✅ 任务 $file_num 完成: $(basename "$file")"
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo "❌ 任务 $file_num 失败: $(basename "$file")"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_FILES+=("$file")
    fi
    
    echo ""
    
    # 如果不是最后一个文件，稍作停顿
    if [ $file_num -lt $total ]; then
        echo "⏳ 等待 2 秒后处理下一个文件..."
        sleep 2
        echo ""
    fi
done

# 显示总结
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 批量翻译总结"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ 成功: $SUCCESS_COUNT 个文件"
echo "❌ 失败: $FAILED_COUNT 个文件"
echo "📁 总计: $total 个文件"

if [ $FAILED_COUNT -gt 0 ]; then
    echo ""
    echo "❌ 失败的文件:"
    for failed_file in "${FAILED_FILES[@]}"; do
        echo "   - $failed_file"
    done
fi

echo ""
if [ $FAILED_COUNT -eq 0 ]; then
    echo "🎉 所有翻译任务完成！"
    exit 0
else
    echo "⚠️  部分翻译任务失败，请检查日志"
    exit 1
fi

