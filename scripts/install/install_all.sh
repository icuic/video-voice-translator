#!/bin/bash
# 兼容性包装脚本 - 请使用项目根目录的 install_all.sh
# 此脚本仅为向后兼容保留，功能与根目录 install_all.sh 完全一致

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "⚠️  建议直接使用项目根目录的安装脚本："
echo "   cd ${PROJECT_ROOT} && ./install_all.sh"
echo ""
echo "即将调用根目录的 install_all.sh ..."
echo ""

exec bash "${PROJECT_ROOT}/install_all.sh" "$@"
