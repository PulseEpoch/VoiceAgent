#!/usr/bin/env python3
import os
import socket
import threading
import json
import numpy as np
from typing import Optional, Union
from dataclasses import dataclass

try:
    import mlx_whisper
    MLX_WHISPER_AVAILABLE = True
except ImportError:
    MLX_WHISPER_AVAILABLE = False

try:
    from modelscope import snapshot_download
    MODELSCOPE_AVAILABLE = True
except ImportError:
    MODELSCOPE_AVAILABLE = False


@dataclass
class TranscriptionResult:
    text: str
    language: Optional[str] = None
    segments: Optional[list] = None


class WhisperServer:
    def __init__(
        self,
        model_id: str = "mlx-community/whisper-small-mlx",
        host: str = "127.0.0.1",
        port: int = 8765,
        socket_path: Optional[str] = None
    ):
        self.model_id = model_id
        self.local_model_path = None
        self.model_loaded = False
        self.host = host
        self.port = port
        self.socket_path = socket_path
        self._server_socket: Optional[socket.socket] = None
        self._running = False
        self._clients: list[socket.socket] = []
        self._model_load_lock = threading.Lock()

    def check_dependencies(self) -> bool:
        if not MLX_WHISPER_AVAILABLE:
            print("[错误] 缺少 mlx-whisper")
            print("请执行: pip install mlx-whisper")
            return False
        return True

    def load_model(self) -> bool:
        print(f"[WhisperServer] 正在加载模型: {self.model_id}")
        try:
            # 优先使用 ModelScope 下载（国内网络更快）
            if MODELSCOPE_AVAILABLE and '/' in self.model_id:
                print(f"[WhisperServer] 从 ModelScope 下载模型...")
                self.local_model_path = snapshot_download(self.model_id)
                print(f"[WhisperServer] 模型下载成功: {self.local_model_path}")
            else:
                # 使用内置模型名称或本地路径
                # mlx_whisper 支持: tiny, base, small, medium, large
                # 首次使用会从 HuggingFace 下载
                self.local_model_path = self.model_id
                print(f"[WhisperServer] 使用模型: {self.model_id}")
                print(f"[WhisperServer] 提示: 首次使用会自动下载模型")
            
            self.model_loaded = True
            return True
        except Exception as e:
            print(f"[WhisperServer] 模型加载失败: {e}")
            print(f"[WhisperServer] 建议: 使用 ModelScope 格式，如: mlx-community/whisper-tiny-mlx")
            return False

    def transcribe(self, audio_data: np.ndarray) -> TranscriptionResult:
        if not MLX_WHISPER_AVAILABLE:
            return TranscriptionResult(text="[错误] mlx-whisper 不可用")
        
        # 延迟加载模型（首次转录时）
        with self._model_load_lock:
            if not self.model_loaded:
                print(f"[WhisperServer] 首次转录，正在下载模型...")
                if not self.load_model():
                    return TranscriptionResult(text="[错误] 模型加载失败")
        
        try:
            # 设置环境变量使用镜像（如果需要）
            import os
            hf_endpoint = os.environ.get('HF_ENDPOINT', '')
            
            result = mlx_whisper.transcribe(
                audio_data,
                path_or_hf_repo=self.local_model_path
            )
            return TranscriptionResult(
                text=result.get("text", "").strip(),
                language=result.get("language"),
                segments=result.get("segments")
            )
        except Exception as e:
            error_msg = str(e)
            print(f"[WhisperServer] 转录错误: {error_msg}")
            
            # 如果是下载错误，给出友好提示
            if "404" in error_msg or "Client Error" in error_msg:
                return TranscriptionResult(text="[提示] 模型下载失败，请使用 ModelScope 模型")
            
            return TranscriptionResult(text=f"[错误] {error_msg[:50]}")

    @staticmethod
    def _recv_exactly(s: socket.socket, n: int) -> bytes:
        """Read exactly n bytes from socket, raising EOFError on premature close."""
        buf = b""
        while len(buf) < n:
            chunk = s.recv(n - len(buf))
            if not chunk:
                raise EOFError("Connection closed before expected bytes were received")
            buf += chunk
        return buf

    @staticmethod
    def _recv_until_end(s: socket.socket) -> bytes:
        """Read bytes until the <END> sentinel is found (used for JSON ping only)."""
        buf = b""
        while b"<END>" not in buf:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
        return buf.split(b"<END>")[0]

    def _handle_client(self, client_socket: socket.socket):
        try:
            # Peek at the first 5 bytes to distinguish message types:
            #   "JSON:" → connection-check ping (legacy <END>-delimited)
            #   4-byte big-endian length → binary audio frame (new framing)
            header = self._recv_exactly(client_socket, 5)

            if header.startswith(b"JSON:"):
                # Connection-check: read the rest up to <END>
                rest = self._recv_until_end(client_socket)
                payload = header[5:] + rest
                metadata = json.loads(payload.decode('utf-8'))
                sample_rate = metadata.get("sample_rate", 16000)
                response = json.dumps({"status": "ok", "sample_rate": sample_rate})
                client_socket.sendall(response.encode('utf-8'))
            else:
                # Binary audio: first 4 bytes are big-endian payload length,
                # 5th byte is the first byte of the audio payload.
                payload_len = int.from_bytes(header[:4], "big")
                audio_bytes = header[4:] + self._recv_exactly(client_socket, payload_len - 1)
                audio_array = np.frombuffer(audio_bytes, dtype=np.float32)
                result = self.transcribe(audio_array)
                response = json.dumps({
                    "text": result.text,
                    "language": result.language,
                    "status": "ok"
                })
                client_socket.sendall(response.encode('utf-8'))

        except Exception as e:
            print(f"[WhisperServer] 客户端处理错误: {e}")
        finally:
            client_socket.close()

    def start(self):
        if not self.check_dependencies():
            print("[WhisperServer] 依赖检查失败")
            return
        
        # 延迟加载模型，在首次转录时再加载
        # 这样服务器可以快速启动
        print("[WhisperServer] 模型将在首次转录时加载")
        
        if self.socket_path:
            if os.path.exists(self.socket_path):
                os.remove(self.socket_path)
            self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._server_socket.bind(self.socket_path)
            self._server_socket.listen(5)
            print(f"[WhisperServer] 监听: {self.socket_path}")
        else:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind((self.host, self.port))
            self._server_socket.listen(5)
            print(f"[WhisperServer] 监听: {self.host}:{self.port}")
        
        self._running = True
        
        try:
            while self._running:
                client_socket, addr = self._server_socket.accept()
                print(f"[WhisperServer] 客户端连接: {addr}")
                thread = threading.Thread(target=self._handle_client, args=(client_socket,))
                thread.daemon = True
                thread.start()
        except KeyboardInterrupt:
            print("\n[WhisperServer] 正在关闭...")
        finally:
            self._running = False
            if self._server_socket:
                self._server_socket.close()

    def stop(self):
        self._running = False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Whisper Server")
    parser.add_argument("--model", default="mlx-community/whisper-tiny-mlx", 
                       help="模型 ID (推荐使用 ModelScope: mlx-community/whisper-tiny-mlx)")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("--socket", type=str, default=None, help="Unix socket 路径")
    
    args = parser.parse_args()
    
    # 显示推荐的 ModelScope 模型
    print("[WhisperServer] 推荐使用 ModelScope 模型（国内下载更快）:")
    print("  - mlx-community/whisper-tiny-mlx")
    print("  - mlx-community/whisper-base-mlx")
    print("  - mlx-community/whisper-small-mlx")
    print("")
    
    server = WhisperServer(
        model_id=args.model,
        host=args.host,
        port=args.port,
        socket_path=args.socket
    )
    server.start()