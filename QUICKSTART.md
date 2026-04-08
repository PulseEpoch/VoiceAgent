# 快速开始

## 最简单的使用方式

```bash
# 直接启动，会自动启动 Whisper Server（使用 ModelScope 下载模型）
python voice_agent.py
```

就这么简单！程序会：
1. 自动检测 Server 是否运行
2. 如果没有运行，自动启动 Server（使用 ModelScope 镜像下载模型，国内速度快）
3. 连接并开始语音终端
4. 退出时自动清理 Server

**首次运行**：会自动从 ModelScope 下载 tiny 模型（约 71MB，需要 8-15 秒）

## 常用命令

```bash
# 使用不同 ModelScope 模型（推荐，国内下载快）
python voice_agent.py --model mlx-community/whisper-tiny-mlx    # 默认，最快
python voice_agent.py --model mlx-community/whisper-base-mlx    # 平衡
python voice_agent.py --model mlx-community/whisper-small-mlx   # 更准确

# 指定要运行的 Shell
python voice_agent.py zsh
python voice_agent.py bash

# 使用 Unix Socket（延迟更低）
python voice_agent.py --socket /tmp/whisper.sock
```

**模型对比**：
- `whisper-tiny-mlx`: 71MB，最快，实时性好
- `whisper-base-mlx`: 142MB，平衡，推荐日常使用
- `whisper-small-mlx`: 483MB，更准确，适合高要求场景

## 按键操作

- **Ctrl+K**: 按住录音，松开识别并执行
- **正常按键**: 直接传递给 Shell

## 架构说明

```
┌─────────────────┐
│ voice_agent.py  │  ← 你运行这个
└────────┬────────┘
         │ 自动启动
         ▼
┌─────────────────┐
│whisper_server.py│  ← 自动管理
└────────┬────────┘
         │
    MLX Whisper
    (GPU 加速)
```

## 高级用法

### 手动管理 Server

如果你想手动控制 Server（比如多个 Agent 共享一个 Server）：

```bash
# 终端 1: 启动 Server
python whisper_server.py --model base

# 终端 2, 3, 4...: 启动多个 Agent
python voice_agent.py --no-auto-start
python voice_agent.py --no-auto-start
python voice_agent.py --no-auto-start
```

### 远程 Server

```bash
# 服务器上（假设 IP 192.168.1.100）
python whisper_server.py --host 0.0.0.0 --port 8765 --model base

# 客户端
python voice_agent.py --host 192.168.1.100 --port 8765 --no-auto-start
```

## 测试

```bash
# 运行完整测试
python test_whisper.py

# 运行自动启动测试
python test_auto_start.py

# 运行演示
./demo_complete.sh
```

## 故障排除

### 问题：连接失败
```bash
# 检查 Server 是否运行
ps aux | grep whisper_server

# 手动启动 Server 查看错误
python whisper_server.py --model tiny
```

### 问题：模型下载慢或失败
```bash
# 使用 ModelScope（推荐，已默认使用）
python whisper_server.py --model mlx-community/whisper-tiny-mlx

# ModelScope 镜像自动使用国内源，无需额外配置
```

### 问题：Server 残留进程
```bash
# 清理所有 Server
pkill -9 -f whisper_server.py
```

## 性能建议

1. **首选 Unix Socket**: `--socket /tmp/whisper.sock`（延迟最低）
2. **选择合适的模型**:
   - `tiny`: 最快，实时性最好
   - `base`: 推荐，速度和准确度平衡
   - `small`: 更准确，稍慢
3. **Apple Silicon**: MLX 自动使用 GPU，性能最佳
