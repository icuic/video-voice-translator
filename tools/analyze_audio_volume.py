#!/usr/bin/env python3
"""
分析原始音频和输出音频中背景音乐与人声的相对音量比例
"""

import os
import sys
import numpy as np
import librosa
import soundfile as sf
from pathlib import Path

def calculate_rms(audio_data):
    """计算RMS音量"""
    return np.sqrt(np.mean(audio_data**2))

def analyze_audio_volume(task_dir):
    """
    分析任务目录中的音频文件音量
    
    Args:
        task_dir: 任务目录路径
    """
    task_dir = Path(task_dir)
    
    print("=" * 60)
    print("音频音量分析")
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
    # 优先查找09_translated*.wav
    translated_files = list(task_dir.glob("09_translated*.wav"))
    if translated_files:
        output_audio_path = sorted(translated_files, key=lambda x: x.stat().st_mtime, reverse=True)[0]
    else:
        # 其次查找08_final_voice.wav
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
    
    if vocals_path.exists() and accompaniment_path.exists():
        vocals, vocals_sr = librosa.load(vocals_path, sr=None)
        accompaniment, accomp_sr = librosa.load(accompaniment_path, sr=None)
        print(f"  人声: {len(vocals)/vocals_sr:.2f}秒, {vocals_sr}Hz")
        print(f"  背景音乐: {len(accompaniment)/accomp_sr:.2f}秒, {accomp_sr}Hz")
    else:
        vocals = None
        accompaniment = None
        print("  ⚠️  人声或背景音乐文件不存在，无法进行详细分析")
    
    output_audio, output_sr = librosa.load(output_audio_path, sr=None)
    print(f"  输出音频: {len(output_audio)/output_sr:.2f}秒, {output_sr}Hz")
    print()
    
    # 统一采样率以便比较
    target_sr = max(orig_sr, output_sr)
    if orig_sr != target_sr:
        original_audio = librosa.resample(original_audio, orig_sr=orig_sr, target_sr=target_sr, res_type='kaiser_best')
    if output_sr != target_sr:
        output_audio = librosa.resample(output_audio, orig_sr=output_sr, target_sr=target_sr, res_type='kaiser_best')
    if vocals is not None and vocals_sr != target_sr:
        vocals = librosa.resample(vocals, orig_sr=vocals_sr, target_sr=target_sr, res_type='kaiser_best')
    if accompaniment is not None and accomp_sr != target_sr:
        accompaniment = librosa.resample(accompaniment, orig_sr=accomp_sr, target_sr=target_sr, res_type='kaiser_best')
    
    # 调整长度以匹配
    min_length = min(len(original_audio), len(output_audio))
    original_audio = original_audio[:min_length]
    output_audio = output_audio[:min_length]
    if vocals is not None:
        vocals = vocals[:min_length] if len(vocals) >= min_length else np.pad(vocals, (0, min_length - len(vocals)))
    if accompaniment is not None:
        accompaniment = accompaniment[:min_length] if len(accompaniment) >= min_length else np.pad(accompaniment, (0, min_length - len(accompaniment)))
    
    # 计算RMS
    print("=" * 60)
    print("音量分析结果")
    print("=" * 60)
    
    original_rms = calculate_rms(original_audio)
    output_rms = calculate_rms(output_audio)
    
    print(f"\n📊 整体RMS:")
    print(f"  原始音频RMS: {original_rms:.6f}")
    print(f"  输出音频RMS: {output_rms:.6f}")
    print(f"  输出/原始比例: {output_rms/original_rms:.2f}x")
    
    if vocals is not None and accompaniment is not None:
        vocals_rms = calculate_rms(vocals)
        accompaniment_rms = calculate_rms(accompaniment)
        
        print(f"\n📊 分离后的RMS:")
        print(f"  人声RMS: {vocals_rms:.6f}")
        print(f"  背景音乐RMS: {accompaniment_rms:.6f}")
        print(f"  人声/背景音乐比例: {vocals_rms/accompaniment_rms:.2f}x")
        
        # 估算原始音频中背景音乐和人声的比例
        # 假设原始音频 = 人声 + 背景音乐（简化模型）
        # 原始RMS^2 ≈ 人声RMS^2 + 背景音乐RMS^2（如果它们不相关）
        estimated_original_voice_rms = np.sqrt(max(0, original_rms**2 - accompaniment_rms**2))
        estimated_original_accomp_rms = accompaniment_rms  # 假设分离后的背景音乐RMS接近原始中的背景音乐RMS
        
        print(f"\n📊 估算原始音频中的比例:")
        print(f"  估算人声RMS: {estimated_original_voice_rms:.6f}")
        print(f"  估算背景音乐RMS: {estimated_original_accomp_rms:.6f}")
        if estimated_original_accomp_rms > 0:
            print(f"  原始人声/背景音乐比例: {estimated_original_voice_rms/estimated_original_accomp_rms:.2f}x")
        
        # 分析输出音频中的背景音乐
        # 输出音频 = 克隆人声 + 背景音乐
        # 估算输出音频中背景音乐的比例
        # 假设输出音频中的人声RMS接近克隆人声的RMS
        # 我们需要从输出音频中估算背景音乐的比例
        # 这是一个近似，因为输出音频是混合的
        
        # 使用频谱分析来估算输出音频中背景音乐的比例
        # 简化方法：假设输出音频中背景音乐的比例可以通过对比分离后的背景音乐来估算
        # 实际上，我们需要知道输出音频中背景音乐的实际RMS
        
        print(f"\n📊 输出音频分析:")
        print(f"  输出音频整体RMS: {output_rms:.6f}")
        print(f"  分离后的背景音乐RMS: {accompaniment_rms:.6f}")
        print(f"  如果输出音频中背景音乐被放大2.0x，则背景音乐RMS约为: {accompaniment_rms * 2.0:.6f}")
        
        # 估算输出音频中背景音乐的实际贡献
        # 假设输出音频 = 克隆人声 * voice_gain + 背景音乐 * background_gain
        # 从日志中我们知道 voice_gain ≈ 3.0x, background_gain ≈ 2.0x
        estimated_output_voice_rms = vocals_rms * 3.0  # 假设克隆人声RMS接近原始人声RMS
        estimated_output_accomp_rms = accompaniment_rms * 2.0
        
        print(f"\n📊 估算输出音频中的比例（基于日志数据）:")
        print(f"  估算克隆人声RMS（放大3.0x后）: {estimated_output_voice_rms:.6f}")
        print(f"  估算背景音乐RMS（放大2.0x后）: {estimated_output_accomp_rms:.6f}")
        if estimated_output_accomp_rms > 0:
            print(f"  输出人声/背景音乐比例: {estimated_output_voice_rms/estimated_output_accomp_rms:.2f}x")
        
        # 对比原始和输出的比例
        if estimated_original_accomp_rms > 0 and estimated_output_accomp_rms > 0:
            original_ratio = estimated_original_voice_rms / estimated_original_accomp_rms
            output_ratio = estimated_output_voice_rms / estimated_output_accomp_rms
            print(f"\n📊 比例对比:")
            print(f"  原始人声/背景音乐比例: {original_ratio:.2f}x")
            print(f"  输出人声/背景音乐比例: {output_ratio:.2f}x")
            print(f"  比例变化: {output_ratio/original_ratio:.2f}x")
            if output_ratio < original_ratio:
                print(f"  ⚠️  输出音频中背景音乐相对更大了！")
                print(f"  💡 建议：降低背景音乐的目标比例或增益")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python analyze_audio_volume.py <任务目录>")
        sys.exit(1)
    
    task_dir = sys.argv[1]
    analyze_audio_volume(task_dir)

