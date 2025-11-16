#!/usr/bin/env python3
"""
清理旧任务目录工具
用于清理output目录中的旧任务，释放磁盘空间
"""

import os
import sys
import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path


def list_tasks(output_dir: str = "data/outputs") -> list:
    """
    列出所有任务目录
    
    Args:
        output_dir: 输出目录路径
        
    Returns:
        任务目录列表
    """
    if not os.path.exists(output_dir):
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
                    
                    tasks.append({
                        'name': item,
                        'path': item_path,
                        'timestamp': timestamp,
                        'size': size,
                        'size_mb': size / (1024 * 1024)
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


def cleanup_by_days(tasks: list, keep_days: int) -> list:
    """
    按天数清理任务
    
    Args:
        tasks: 任务列表
        keep_days: 保留天数
        
    Returns:
        要删除的任务列表
    """
    cutoff_date = datetime.now() - timedelta(days=keep_days)
    to_delete = []
    
    for task in tasks:
        if task['timestamp'] < cutoff_date:
            to_delete.append(task)
    
    return to_delete


def cleanup_by_count(tasks: list, keep_count: int) -> list:
    """
    按数量清理任务
    
    Args:
        tasks: 任务列表
        keep_count: 保留数量
        
    Returns:
        要删除的任务列表
    """
    if len(tasks) <= keep_count:
        return []
    
    return tasks[keep_count:]


def cleanup_by_size(tasks: list, max_size_mb: int) -> list:
    """
    按大小清理任务
    
    Args:
        tasks: 任务列表
        max_size_mb: 最大总大小（MB）
        
    Returns:
        要删除的任务列表
    """
    total_size = sum(task['size_mb'] for task in tasks)
    if total_size <= max_size_mb:
        return []
    
    # 从最旧的开始删除
    to_delete = []
    current_size = total_size
    
    for task in reversed(tasks):  # 从最旧的开始
        if current_size <= max_size_mb:
            break
        to_delete.append(task)
        current_size -= task['size_mb']
    
    return to_delete


def delete_tasks(tasks_to_delete: list, dry_run: bool = True) -> dict:
    """
    删除任务目录
    
    Args:
        tasks_to_delete: 要删除的任务列表
        dry_run: 是否为试运行（不实际删除）
        
    Returns:
        删除结果统计
    """
    results = {
        'deleted': 0,
        'failed': 0,
        'total_size_freed': 0,
        'errors': []
    }
    
    for task in tasks_to_delete:
        try:
            if dry_run:
                print(f"[试运行] 将删除: {task['name']} ({task['size_mb']:.1f} MB)")
                results['deleted'] += 1
                results['total_size_freed'] += task['size_mb']
            else:
                print(f"删除任务目录: {task['name']} ({task['size_mb']:.1f} MB)")
                shutil.rmtree(task['path'])
                results['deleted'] += 1
                results['total_size_freed'] += task['size_mb']
                print(f"✅ 已删除: {task['name']}")
        except Exception as e:
            error_msg = f"删除失败 {task['name']}: {e}"
            print(f"❌ {error_msg}")
            results['failed'] += 1
            results['errors'].append(error_msg)
    
    return results


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='清理旧任务目录工具')
    parser.add_argument('--output-dir', default='data/outputs', help='输出目录路径 (默认: data/outputs)')
    parser.add_argument('--keep-days', type=int, help='保留最近N天的任务')
    parser.add_argument('--keep-count', type=int, help='保留最近N个任务')
    parser.add_argument('--max-size', type=int, help='最大总大小（MB）')
    parser.add_argument('--dry-run', action='store_true', help='试运行，不实际删除')
    parser.add_argument('--list', action='store_true', help='只列出任务，不删除')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    print("🧹 任务目录清理工具")
    print("=" * 50)
    
    # 列出所有任务
    tasks = list_tasks(args.output_dir)
    
    if not tasks:
        print(f"📁 在 {args.output_dir} 中没有找到任务目录")
        return
    
    print(f"📊 找到 {len(tasks)} 个任务目录")
    print(f"💾 总大小: {sum(task['size_mb'] for task in tasks):.1f} MB")
    print()
    
    # 显示任务列表
    print("📋 任务列表:")
    for i, task in enumerate(tasks, 1):
        print(f"  {i:2d}. {task['name']}")
        print(f"      时间: {task['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"      大小: {task['size_mb']:.1f} MB")
        if args.verbose:
            print(f"      路径: {task['path']}")
        print()
    
    if args.list:
        print("📋 仅列出模式，不执行删除操作")
        return
    
    # 确定要删除的任务
    tasks_to_delete = []
    
    if args.keep_days:
        tasks_to_delete = cleanup_by_days(tasks, args.keep_days)
        print(f"🗓️  按天数清理: 保留最近 {args.keep_days} 天")
    elif args.keep_count:
        tasks_to_delete = cleanup_by_count(tasks, args.keep_count)
        print(f"🔢 按数量清理: 保留最近 {args.keep_count} 个")
    elif args.max_size:
        tasks_to_delete = cleanup_by_size(tasks, args.max_size)
        print(f"💾 按大小清理: 最大 {args.max_size} MB")
    else:
        print("❌ 请指定清理条件: --keep-days, --keep-count, 或 --max-size")
        return
    
    if not tasks_to_delete:
        print("✅ 没有需要删除的任务")
        return
    
    print(f"🗑️  将删除 {len(tasks_to_delete)} 个任务:")
    for task in tasks_to_delete:
        print(f"  - {task['name']} ({task['size_mb']:.1f} MB)")
    
    print()
    
    # 执行删除
    if args.dry_run:
        print("🔍 试运行模式 - 不会实际删除文件")
    else:
        confirm = input("⚠️  确认删除这些任务吗？(y/N): ")
        if confirm.lower() != 'y':
            print("❌ 操作已取消")
            return
    
    results = delete_tasks(tasks_to_delete, args.dry_run)
    
    # 显示结果
    print()
    print("📊 清理结果:")
    print(f"  ✅ 成功删除: {results['deleted']} 个")
    print(f"  ❌ 删除失败: {results['failed']} 个")
    print(f"  💾 释放空间: {results['total_size_freed']:.1f} MB")
    
    if results['errors']:
        print("\n❌ 错误详情:")
        for error in results['errors']:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
