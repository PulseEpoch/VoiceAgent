#!/bin/bash

echo "=== Whisper Server-Client 架构演示 ==="
echo ""
echo "架构说明:"
echo "  whisper_server.py - 独立推理服务器"
echo "  whisper_client.py - 客户端库"
echo "  voice_agent.py    - 语音终端（客户端）"
echo ""

echo "1. 启动 Whisper Server (后台)..."
python whisper_server.py --model tiny > /tmp/whisper_demo.log 2>&1 &
SERVER_PID=$!
echo "   Server PID: $SERVER_PID"
sleep 5

echo ""
echo "2. 测试多个客户端连接..."
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
echo "3. 服务器状态:"
echo "   进程: $(ps -p $SERVER_PID -o comm= 2>/dev/null || echo '已停止')"
echo "   端口: $(lsof -i :8765 -sTCP:LISTEN | grep -v COMMAND || echo '未监听')"

echo ""
echo "4. 清理..."
kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
echo "   ✓ 服务器已关闭"

echo ""
echo "演示完成！"
