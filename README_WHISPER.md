# Whisper Server-Client 架构

## 架构说明

已将 Whisper 推理分离为独立的 server-client 模式：

- **whisper_server.py**: 独立的 Whisper 推理服务器，可服务多个客户端
- **whisper_client.py**: 轻量级客户端库
- **voice_agent.py**: 语音终端（使用 client 连接 server）

## 优势

1. **资源高效**: 一个服务器进程，多个客户端共享
2. **独立部署**: Server 可部署在其他机器
3. **易于扩展**: 支持 TCP 和 Unix Socket
4. **热更新**: 无需重启客户端即可更换模型
5. **自动启动**: Client 连接失败时自动启动 Server

## 使用方法

### 1. 启动 Whisper Server

```bash
# 使用默认模型（mlx-community/whisper-small-mlx）
python whisper_server.py

# 指定模型
python whisper_server.py --model tiny
python whisper_server.py --model base
python whisper_server.py --model small

# 使用 ModelScope 模型（国内下载更快）
python whisper_server.py --model mlx-community/whisper-small-mlx

# 自定义端口
python whisper_server.py --host 0.0.0.0 --port 9000

# 使用 Unix Socket（推荐，低延迟）
python whisper_server.py --socket /tmp/whisper.sock
```

### 2. 启动语音终端

```bash
# 最简单方式：自动启动服务器（推荐）
python voice_agent.py

# 指定模型（自动启动）
python voice_agent.py --model base

# 连接到已有服务器（禁用自动启动）
python voice_agent.py --no-auto-start

# 连接到远程服务器
python voice_agent.py --host 192.168.1.100 --port 9000 --no-auto-start

# 使用 Unix Socket
python voice_agent.py --socket /tmp/whisper.sock

# 指定命令
python voice_agent.py zsh
python voice_agent.py --model tiny bash
```

**自动启动说明**：
- 默认启用自动启动，Client 会在连接失败时自动启动 Server
- 使用 `--no-auto-start` 禁用此功能
- 退出时自动清理服务器进程

### 3. 运行测试

```bash
# 自动化测试（包括多客户端）
python test_whisper.py

# 手动测试客户端连接
python whisper_client.py
```

## 网络模式

### TCP 模式（默认）
```bash
# Server
python whisper_server.py --host 127.0.0.1 --port 8765

# Client
python voice_agent.py --host 127.0.0.1 --port 8765
```

### Unix Socket 模式（推荐）
```bash
# Server
python whisper_server.py --socket /tmp/whisper.sock

# Client  
python voice_agent.py --socket /tmp/whisper.sock
```

## 协议

客户端与服务器之间使用简单的二进制协议：

1. 客户端发送: `<audio_bytes><END>`
2. 服务器返回: `{"text": "...", "language": "...", "status": "ok"}`

## 模型下载

Server 会自动下载模型：

- 内置模型: `tiny`, `base`, `small`, `medium`, `large`
- ModelScope: `mlx-community/whisper-small-mlx`
- HuggingFace: 任何兼容的 Whisper 模型

首次运行会自动下载，之后会使用缓存。

## 故障排除

### 连接失败
```bash
# 检查服务器是否运行
ps aux | grep whisper_server

# 检查端口占用
lsof -i :8765

# 测试连接
python whisper_client.py
```

### 模型下载失败
如果遇到 404 错误，可能是网络问题：

```bash
# 使用国内镜像
export HF_ENDPOINT=https://hf-mirror.com

# 或使用 ModelScope
python whisper_server.py --model mlx-community/whisper-small-mlx
```

## 性能优化

1. **使用 Unix Socket**: 比 TCP 延迟更低
2. **选择小模型**: `tiny` 速度最快，`base` 平衡性能和准确度
3. **Apple Silicon**: MLX 自动使用 GPU 加速
