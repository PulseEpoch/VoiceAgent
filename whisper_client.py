import socket
import json
import numpy as np
from typing import Optional
from dataclasses import dataclass


@dataclass
class TranscriptionResult:
    text: str
    language: Optional[str] = None
    status: str = "ok"


class WhisperClient:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        socket_path: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.socket_path = socket_path

    def _connect(self) -> socket.socket:
        if self.socket_path:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(self.socket_path)
        else:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self.host, self.port))
        return s

    @staticmethod
    def _recv_all(s: socket.socket) -> bytes:
        """Read until the peer closes the connection."""
        chunks = []
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def transcribe(self, audio_data: np.ndarray) -> TranscriptionResult:
        s = self._connect()
        try:
            # Prefix with a 4-byte big-endian length so the server can find the
            # exact message boundary without scanning binary audio data for a
            # text sentinel (which could appear accidentally in float32 bytes).
            audio_bytes = audio_data.tobytes()
            length_prefix = len(audio_bytes).to_bytes(4, "big")
            s.sendall(length_prefix + audio_bytes)
            s.shutdown(socket.SHUT_WR)

            response = self._recv_all(s).decode('utf-8')
            data = json.loads(response)
            return TranscriptionResult(
                text=data.get("text", ""),
                language=data.get("language"),
                status=data.get("status", "ok")
            )
        except Exception as e:
            return TranscriptionResult(text=f"[错误] {str(e)}", status="error")
        finally:
            s.close()

    def check_connection(self, sample_rate: int = 16000) -> bool:
        try:
            s = self._connect()
            metadata = json.dumps({"sample_rate": sample_rate, "dtype": "float32"})
            s.sendall(b"JSON:" + metadata.encode('utf-8') + b"<END>")
            s.shutdown(socket.SHUT_WR)

            response = self._recv_all(s).decode('utf-8')
            data = json.loads(response)
            s.close()
            return data.get("status") == "ok"
        except Exception:
            return False


if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description="Whisper Client")
    parser.add_argument("--host", default="127.0.0.1", help="服务器地址")
    parser.add_argument("--port", type=int, default=8765, help="服务器端口")
    parser.add_argument("--socket", type=str, default=None, help="Unix socket 路径")
    parser.add_argument("audio_file", nargs="?", help="音频文件路径")
    
    args = parser.parse_args()
    
    client = WhisperClient(host=args.host, port=args.port, socket_path=args.socket)
    
    if args.audio_file:
        try:
            audio = np.fromfile(args.audio_file, dtype=np.float32)
            result = client.transcribe(audio)
            print(result.text)
        except Exception as e:
            print(f"[错误] {e}", file=sys.stderr)
            sys.exit(1)
    else:
        if client.check_connection():
            print("[WhisperClient] 连接成功")
        else:
            print("[WhisperClient] 连接失败", file=sys.stderr)
            sys.exit(1)