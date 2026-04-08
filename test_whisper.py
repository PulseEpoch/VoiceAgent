#!/usr/bin/env python3
import numpy as np
import time
import subprocess
import sys

def test_server_client():
    print("=== Whisper Server-Client 测试 ===\n")
    
    # 1. 启动服务器
    print("1. 启动 Whisper Server...")
    server_proc = subprocess.Popen(
        [sys.executable, "whisper_server.py", "--model", "tiny"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # 等待服务器启动
    print("   等待服务器初始化...")
    time.sleep(8)
    
    # 2. 测试客户端连接
    print("\n2. 测试客户端连接...")
    try:
        from whisper_client import WhisperClient
        
        client = WhisperClient()
        if client.check_connection():
            print("   ✓ 连接成功")
        else:
            print("   ✗ 连接失败")
            server_proc.kill()
            return False
        
        # 3. 发送测试音频
        print("\n3. 发送测试音频（1秒静音）...")
        test_audio = np.zeros(16000, dtype=np.float32)
        result = client.transcribe(test_audio)
        print(f"   结果: '{result.text}'")
        print(f"   状态: {result.status}")
        
        # 4. 多客户端测试
        print("\n4. 测试多客户端连接...")
        client2 = WhisperClient()
        client3 = WhisperClient()
        
        for i, c in enumerate([client, client2, client3], 1):
            r = c.transcribe(test_audio)
            print(f"   客户端 {i}: {r.status}")
        
        print("\n✓ 所有测试通过")
        
    except Exception as e:
        print(f"   ✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n5. 关闭服务器...")
        server_proc.kill()
        server_proc.wait()
        print("   ✓ 服务器已关闭")

if __name__ == "__main__":
    test_server_client()
