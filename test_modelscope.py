#!/usr/bin/env python3
"""测试 ModelScope 模型下载"""
import sys
import time

print("=== 测试 ModelScope 模型下载 ===\n")

print("1. 检查依赖...")
try:
    from modelscope import snapshot_download
    print("   ✓ modelscope 已安装")
except ImportError:
    print("   ✗ modelscope 未安装")
    print("   执行: pip install modelscope")
    sys.exit(1)

try:
    import mlx_whisper
    print("   ✓ mlx-whisper 已安装")
except ImportError:
    print("   ✗ mlx-whisper 未安装")
    print("   执行: pip install mlx-whisper")
    sys.exit(1)

print("\n2. 下载 tiny 模型（最小，速度最快）...")
model_id = "mlx-community/whisper-tiny-mlx"
try:
    start = time.time()
    model_path = snapshot_download(model_id)
    elapsed = time.time() - start
    print(f"   ✓ 下载成功: {model_path}")
    print(f"   耗时: {elapsed:.1f} 秒")
except Exception as e:
    print(f"   ✗ 下载失败: {e}")
    sys.exit(1)

print("\n3. 测试模型加载...")
try:
    import numpy as np
    # 生成 1 秒静音测试音频
    test_audio = np.zeros(16000, dtype=np.float32)
    
    print("   正在转录测试音频...")
    result = mlx_whisper.transcribe(test_audio, path_or_hf_repo=model_path)
    print(f"   ✓ 转录成功")
    print(f"   结果: '{result.get('text', '').strip()}'")
    
except Exception as e:
    print(f"   ✗ 转录失败: {e}")
    sys.exit(1)

print("\n✓ 所有测试通过！")
print("\n可用的 ModelScope 模型:")
print("  - mlx-community/whisper-tiny-mlx   (最快)")
print("  - mlx-community/whisper-base-mlx   (平衡)")
print("  - mlx-community/whisper-small-mlx  (更准确)")
print("  - mlx-community/whisper-medium-mlx (大模型)")
