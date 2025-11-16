#!/usr/bin/env python3
"""
列出任务目录工具
用于查看output目录中的所有任务
"""

import os
import argparse
from datetime import datetime
from pathlib import Path


def list_tasks(output_dir: str = "data/outputs", verbose: bool = False) -> list:
    """
    列出所有任务目录
    
    Args:
        output_dir: 输出目录路径
        verbose: 是否显示详细信息
        
    Returns:
        任务目录列表
    """
    if not os.path.exists(output_dir):
        print(f"❌ 输出目录不存在: {output_dir}")
        return []
    
    tasks = []
    for item in os.listdir(output_dir):
        item_path = os.path.join(output_dir, item)
        if os.path.isdir(item_path):
            # 检查目录名格式 (时间戳_文件名)
            if len(item.split('_')) >= 4:  # YYYY-MM-DD_HH-MM-SS_文件名
                try:
                    # 解析时间戳
                    timestamp_str = '_'.join(item.split('_')[:3])  # YYYY-MM-DD_HH-MM-SS
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d_%H-%M-%S")
                    
                    # 获取目录大小
                    size = get_directory_size(item_path)
                    
                    # 获取文件列表
                    files = []
                    if verbose:
                        files = get_file_list(item_path)
                    
                    tasks.append({
                        'name': item,
                        'path': item_path,
                        'timestamp': timestamp,
                        'size': size,
                        'size_mb': size / (1024 * 1024),
                        'files': files
                    })
                except ValueError:
                    # 不是标准格式的任务目录，跳过
                    continue
    
    # 按时间排序（最新的在前）
    tasks.sort(key=lambda x: x['timestamp'], reverse=True)
    return tasks


def get_directory_size(directory: str) -> int:
    """
    计算目录大小
    
    Args:
        directory: 目录路径
        
    Returns:
        目录大小（字节）
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    return total_size


def get_file_list(directory: str) -> list:
    """
    获取目录中的文件列表
    
    Args:
        directory: 目录路径
        
    Returns:
        文件列表
    """
    files = []
    for item in os.listdir(directory):
        item_path = os.path.join(directory, item)
        if os.path.isfile(item_path):
            size = os.path.getsize(item_path)
            files.append({
                'name': item,
                'size': size,
                'size_mb': size / (1024 * 1024)
            })
    
    # 按大小排序
    files.sort(key=lambda x: x['size'], reverse=True)
    return files


def format_size(size_mb: float) -> str:
    """
    格式化文件大小
    
    Args:
        size_mb: 大小（MB）
        
    Returns:
        格式化的大小字符串
    """
    if size_mb < 1:
        return f"{size_mb * 1024:.1f} KB"
    elif size_mb < 1024:
        return f"{size_mb:.1f} MB"
    else:
        return f"{size_mb / 1024:.1f} GB"


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='列出任务目录工具')
    parser.add_argument('--output-dir', default='data/outputs', help='输出目录路径 (默认: data/outputs)')
    parser.add_argument('--verbose', '-v', action='store_true', help='显示详细信息')
    parser.add_argument('--summary', '-s', action='store_true', help='只显示摘要信息')
    
    args = parser.parse_args()
    
    print("📋 任务目录列表")
    print("=" * 50)
    
    # 列出所有任务
    tasks = list_tasks(args.output_dir, args.verbose)
    
    if not tasks:
        print(f"📁 在 {args.output_dir} 中没有找到任务目录")
        return
    
    # 显示摘要信息
    total_size = sum(task['size_mb'] for task in tasks)
    print(f"📊 任务统计:")
    print(f"  📁 任务数量: {len(tasks)}")
    print(f"  💾 总大小: {format_size(total_size)}")
    print()
    
    if args.summary:
        return
    
    # 显示任务列表
    for i, task in enumerate(tasks, 1):
        print(f"📁 任务 {i}: {task['name']}")
        print(f"   ⏰ 时间: {task['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   💾 大小: {format_size(task['size_mb'])}")
        print(f"   📍 路径: {task['path']}")
        
        if args.verbose and task['files']:
            print(f"   📄 文件列表:")
            for file_info in task['files']:
                print(f"      - {file_info['name']} ({format_size(file_info['size_mb'])})")
        
        print()
    
    # 显示清理建议
    print("💡 清理建议:")
    print(f"  🗓️  保留最近7天: python tools/cleanup_old_tasks.py --keep-days 7 --dry-run")
    print(f"  🔢 保留最近10个: python tools/cleanup_old_tasks.py --keep-count 10 --dry-run")
    print(f"  💾 限制总大小1GB: python tools/cleanup_old_tasks.py --max-size 1024 --dry-run")


if __name__ == "__main__":
    main()
