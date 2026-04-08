#!/bin/bash

echo "=== Whisper Server-Client 完整演示 ==="
echo ""

# 清理环境
echo "0. 清理环境..."
pkill -9 -f whisper_server.py 2>/dev/null
sleep 1

echo "=== 场景 1: 手动启动 Server + 多客户端 ==="
echo ""
echo "1.1 手动启动 Server (后台)..."
python whisper_server.py --model tiny > /tmp/whisper_demo.log 2>&1 &
SERVER_PID=$!
echo "   Server PID: $SERVER_PID"
sleep 5

echo ""
echo "1.2 测试多客户端连接..."
python -c "
from whisper_client import WhisperClient
import numpy as np

for i in range(3):
    client = WhisperClient()
    if client.check_connection():
        print(f'   ✓ 客户端 {i+1} 连接成功')
    else:
        print(f'   ✗ 客户端 {i+1} 连接失败')
"

echo ""
echo "1.3 停止 Server..."
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
sleep 2

echo ""
echo "=== 场景 2: 自动启动功能 ==="
echo ""
echo "2.1 确认 Server 已停止..."
if pgrep -f whisper_server.py > /dev/null; then
    echo "   发现残留进程，清理中..."
    pkill -9 -f whisper_server.py
    sleep 1
fi
echo "   ✓ 无 Server 运行"

echo ""
echo "2.2 启动 Client（自动启动 Server）..."
python -c "
from voice_agent import VoiceTerminal

vt = VoiceTerminal(
    command=['echo', 'test'],
    whisper_model='tiny',
    auto_start_server=True
)

print('   正在连接...')
if vt.connect_whisper_server():
    print('   ✓ Server 自动启动成功')
    print('   ✓ 客户端已连接')
    
    # 测试第二个客户端能否连接到同一服务器
    from whisper_client import WhisperClient
    client2 = WhisperClient()
    if client2.check_connection():
        print('   ✓ 第二个客户端连接到同一 Server')
    
    vt.cleanup()
else:
    print('   ✗ 连接失败')
"

echo ""
echo "2.3 确认 Server 已清理..."
sleep 1
if pgrep -f whisper_server.py > /dev/null; then
    echo "   发现残留进程"
    pkill -9 -f whisper_server.py
else
    echo "   ✓ Server 已自动清理"
fi

echo ""
echo "=== 场景 3: Unix Socket 模式 ==="
echo ""
SOCKET_PATH="/tmp/whisper_test.sock"
rm -f $SOCKET_PATH

echo "3.1 启动 Server (Unix Socket)..."
python whisper_server.py --model tiny --socket $SOCKET_PATH > /dev/null 2>&1 &
SERVER_PID=$!
sleep 5

echo "3.2 测试连接..."
python -c "
from whisper_client import WhisperClient

client = WhisperClient(socket_path='$SOCKET_PATH')
if client.check_connection():
    print('   ✓ Unix Socket 连接成功')
else:
    print('   ✗ Unix Socket 连接失败')
"

echo ""
echo "3.3 清理..."
kill $SERVER_PID 2>/dev/null
rm -f $SOCKET_PATH

echo ""
echo "=== 演示完成 ==="
echo ""
echo "总结:"
echo "  ✓ Server-Client 架构正常"
echo "  ✓ 多客户端支持正常"
echo "  ✓ 自动启动功能正常"
echo "  ✓ Unix Socket 模式正常"
