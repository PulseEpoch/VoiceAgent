#!/usr/bin/env python3
"""测试自动启动功能"""
import time
import subprocess
import sys

print("=== 测试 Whisper Server 自动启动 ===\n")

print("1. 确认没有服务器运行...")
result = subprocess.run(["pgrep", "-f", "whisper_server.py"], capture_output=True)
if result.returncode == 0:
    print("   发现运行中的服务器，正在清理...")
    subprocess.run(["pkill", "-9", "-f", "whisper_server.py"])
    time.sleep(1)
print("   ✓ 无服务器运行\n")

print("2. 测试客户端自动启动服务器...")
test_code = """
from voice_agent import VoiceTerminal
from whisper_client import WhisperClient

# 创建 VoiceTerminal（不启动终端，只测试连接）
import sys
sys.stdout = open('/tmp/test_output.txt', 'w')

vt = VoiceTerminal(
    command=['echo', 'test'],
    whisper_model='tiny',
    auto_start_server=True
)

# 测试连接（会自动启动服务器）
if vt.connect_whisper_server():
    print('SUCCESS: Server auto-started')
    # 测试连接是否真的可用
    result = vt.client.check_connection()
    print(f'CONNECTION_TEST: {result}')
    
    # 清理
    vt.cleanup()
else:
    print('FAILED: Could not connect')
"""

# 运行测试
proc = subprocess.Popen(
    [sys.executable, "-c", test_code],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

# 等待完成
proc.wait(timeout=20)

# 读取结果
time.sleep(1)
try:
    with open('/tmp/test_output.txt', 'r') as f:
        output = f.read()
        if 'SUCCESS' in output:
            print("   ✓ 服务器自动启动成功")
            if 'CONNECTION_TEST: True' in output:
                print("   ✓ 连接测试通过")
        else:
            print("   ✗ 自动启动失败")
            print(f"   输出: {output}")
except FileNotFoundError:
    print("   ✗ 未找到输出文件")

print("\n3. 检查服务器进程...")
result = subprocess.run(["pgrep", "-f", "whisper_server.py"], capture_output=True)
if result.returncode == 0:
    pids = result.stdout.decode().strip().split('\n')
    print(f"   ✓ 发现 {len(pids)} 个服务器进程")
    # 清理
    subprocess.run(["pkill", "-9", "-f", "whisper_server.py"])
else:
    print("   ✗ 未发现服务器进程（可能已清理）")

print("\n测试完成！")
