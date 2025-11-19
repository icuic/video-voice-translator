#!/usr/bin/env python3
"""
详细分析原始音频和输出音频中背景音乐与人声的实际音量
"""

import os
import sys
import numpy as np
import librosa
from pathlib import Path

def calculate_rms(audio_data):
    """计算RMS音量"""
    return np.sqrt(np.mean(audio_data**2))

def analyze_detailed_volume(task_dir):
    """
    详细分析任务目录中的音频文件音量
    
    Args:
        task_dir: 任务目录路径
    """
    task_dir = Path(task_dir)
    
    print("=" * 60)
    print("详细音频音量分析")
    print("=" * 60)
    
    # 1. 原始音频文件
    original_audio_path = task_dir / "00_original_input.m4a"
    if not original_audio_path.exists():
        original_audio_path = task_dir / "00_original_input.mp4"
    if not original_audio_path.exists():
        print(f"❌ 未找到原始音频文件")
        return
    
    # 2. 分离后的人声和背景音乐
    vocals_path = task_dir / "02_vocals.wav"
    accompaniment_path = task_dir / "02_accompaniment.wav"
    
    # 3. 最终输出音频
    output_audio_path = None
    translated_files = list(task_dir.glob("09_translated*.wav"))
    if translated_files:
        output_audio_path = sorted(translated_files, key=lambda x: x.stat().st_mtime, reverse=True)[0]
    else:
        final_voice_path = task_dir / "08_final_voice.wav"
        if final_voice_path.exists():
            output_audio_path = final_voice_path
    
    if not output_audio_path or not output_audio_path.exists():
        print(f"❌ 未找到输出音频文件")
        return
    
    print(f"\n📁 任务目录: {task_dir}")
    print(f"📹 原始音频: {original_audio_path.name}")
    print(f"🎤 人声文件: {vocals_path.name if vocals_path.exists() else '不存在'}")
    print(f"🎵 背景音乐: {accompaniment_path.name if accompaniment_path.exists() else '不存在'}")
    print(f"📤 输出音频: {output_audio_path.name}")
    print()
    
    # 加载音频文件
    print("加载音频文件...")
    original_audio, orig_sr = librosa.load(original_audio_path, sr=None)
    print(f"  原始音频: {len(original_audio)/orig_sr:.2f}秒, {orig_sr}Hz")
    
    if not vocals_path.exists() or not accompaniment_path.exists():
        print("  ⚠️  人声或背景音乐文件不存在，无法进行详细分析")
        return
    
    vocals, vocals_sr = librosa.load(vocals_path, sr=None)
    accompaniment, accomp_sr = librosa.load(accompaniment_path, sr=None)
    output_audio, output_sr = librosa.load(output_audio_path, sr=None)
    
    print(f"  人声: {len(vocals)/vocals_sr:.2f}秒, {vocals_sr}Hz")
    print(f"  背景音乐: {len(accompaniment)/accomp_sr:.2f}秒, {accomp_sr}Hz")
    print(f"  输出音频: {len(output_audio)/output_sr:.2f}秒, {output_sr}Hz")
    print()
    
    # 统一采样率以便比较
    target_sr = max(orig_sr, output_sr, vocals_sr, accomp_sr)
    if orig_sr != target_sr:
        original_audio = librosa.resample(original_audio, orig_sr=orig_sr, target_sr=target_sr, res_type='kaiser_best')
    if output_sr != target_sr:
        output_audio = librosa.resample(output_audio, orig_sr=output_sr, target_sr=target_sr, res_type='kaiser_best')
    if vocals_sr != target_sr:
        vocals = librosa.resample(vocals, orig_sr=vocals_sr, target_sr=target_sr, res_type='kaiser_best')
    if accomp_sr != target_sr:
        accompaniment = librosa.resample(accompaniment, orig_sr=accomp_sr, target_sr=target_sr, res_type='kaiser_best')
    
    # 调整长度以匹配
    min_length = min(len(original_audio), len(output_audio), len(vocals), len(accompaniment))
    original_audio = original_audio[:min_length]
    output_audio = output_audio[:min_length]
    vocals = vocals[:min_length] if len(vocals) >= min_length else np.pad(vocals, (0, min_length - len(vocals)))
    accompaniment = accompaniment[:min_length] if len(accompaniment) >= min_length else np.pad(accompaniment, (0, min_length - len(accompaniment)))
    
    # 计算RMS
    print("=" * 60)
    print("详细音量分析结果")
    print("=" * 60)
    
    original_rms = calculate_rms(original_audio)
    output_rms = calculate_rms(output_audio)
    vocals_rms = calculate_rms(vocals)
    accompaniment_rms = calculate_rms(accompaniment)
    
    print(f"\n📊 分离后的RMS（原始音频）:")
    print(f"  人声RMS: {vocals_rms:.6f}")
    print(f"  背景音乐RMS: {accompaniment_rms:.6f}")
    print(f"  人声/背景音乐比例: {vocals_rms/accompaniment_rms:.2f}x")
    
    print(f"\n📊 整体RMS:")
    print(f"  原始音频整体RMS: {original_rms:.6f}")
    print(f"  输出音频整体RMS: {output_rms:.6f}")
    print(f"  输出/原始比例: {output_rms/original_rms:.2f}x")
    
    # 估算输出音频中背景音乐的实际贡献
    # 方法：假设输出音频 = 克隆人声 + 背景音乐
    # 如果背景音乐增益是1.0x，那么输出音频中的背景音乐RMS应该接近原始背景音乐RMS
    # 但实际输出音频是混合的，我们需要估算
    
    # 简化估算：如果背景音乐增益是1.0x，那么输出音频中的背景音乐RMS ≈ accompaniment_rms
    # 输出音频整体RMS^2 ≈ 克隆人声RMS^2 + 背景音乐RMS^2（如果它们不相关）
    # 估算输出音频中的克隆人声RMS
    estimated_output_voice_rms = np.sqrt(max(0, output_rms**2 - accompaniment_rms**2))
    
    print(f"\n📊 估算输出音频中的RMS（基于混合模型）:")
    print(f"  估算克隆人声RMS: {estimated_output_voice_rms:.6f}")
    print(f"  背景音乐RMS（假设增益1.0x）: {accompaniment_rms:.6f}")
    if accompaniment_rms > 0:
        estimated_output_ratio = estimated_output_voice_rms / accompaniment_rms
        print(f"  估算输出人声/背景音乐比例: {estimated_output_ratio:.2f}x")
    
    # 对比
    original_ratio = vocals_rms / accompaniment_rms
    print(f"\n📊 比例对比:")
    print(f"  原始人声/背景音乐比例: {original_ratio:.2f}x")
    if accompaniment_rms > 0:
        print(f"  估算输出人声/背景音乐比例: {estimated_output_ratio:.2f}x")
        ratio_change = estimated_output_ratio / original_ratio
        print(f"  比例变化: {ratio_change:.2f}x")
        
        if ratio_change > 1.1:
            print(f"  ⚠️  输出音频中背景音乐相对变小了（人声相对变大）")
        elif ratio_change < 0.9:
            print(f"  ⚠️  输出音频中背景音乐相对变大了（人声相对变小）")
        else:
            print(f"  ✅ 比例基本保持")
    
    # 分析：如果人声被降低（增益0.82x），而背景音乐保持（增益1.0x）
    # 那么相对感觉背景音乐会更明显
    print(f"\n📊 感知分析:")
    print(f"  如果人声增益是0.82x（降低），背景音乐增益是1.0x（保持）")
    print(f"  那么相对感觉：背景音乐会更明显，因为人声被降低了")
    print(f"  💡 建议：如果人声被降低，背景音乐也应该相应降低，以保持相对比例")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python analyze_detailed_volume.py <任务目录>")
        sys.exit(1)
    
    task_dir = sys.argv[1]
    analyze_detailed_volume(task_dir)

