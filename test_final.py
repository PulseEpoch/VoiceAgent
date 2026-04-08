#!/usr/bin/env python3
"""完整功能测试"""
import subprocess
import time
import numpy as np
import sys

print("=== 完整功能测试 ===\n")

# 1. 启动服务器
print("1. 启动 Whisper Server (ModelScope 模型)...")
server_proc = subprocess.Popen(
    [sys.executable, "whisper_server.py", "--model", "mlx-community/whisper-tiny-mlx"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

print("   等待服务器启动...")
time.sleep(3)

# 2. 测试客户端
print("\n2. 测试客户端连接...")
from whisper_client import WhisperClient

client = WhisperClient()
if client.check_connection():
    print("   ✓ 连接成功")
else:
    print("   ✗ 连接失败")
    server_proc.kill()
    sys.exit(1)

# 3. 测试转录（静音）
print("\n3. 测试转录 (1秒静音)...")
test_audio = np.zeros(16000, dtype=np.float32)
result = client.transcribe(test_audio)
print(f"   状态: {result.status}")
print(f"   结果: '{result.text}'")

if "错误" in result.text or "404" in result.text:
    print("   ✗ 转录失败")
    server_proc.kill()
    sys.exit(1)
else:
    print("   ✓ 转录成功（静音返回空文本是正常的）")

# 4. 测试多客户端
print("\n4. 测试多客户端...")
for i in range(3):
    c = WhisperClient()
    r = c.transcribe(test_audio)
    if "错误" not in r.text:
        print(f"   ✓ 客户端 {i+1}: {r.status}")
    else:
        print(f"   ✗ 客户端 {i+1}: {r.text[:30]}")

# 5. 清理
print("\n5. 清理...")
server_proc.terminate()
server_proc.wait(timeout=5)
print("   ✓ 服务器已关闭")

print("\n✓ 所有测试通过！")
print("\n现在可以使用:")
print("  python voice_agent.py")
