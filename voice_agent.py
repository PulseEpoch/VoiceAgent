import os
import sys
import pty
import tty
import termios
import select
import threading
import time
import queue
import numpy as np
import sounddevice as sd
import subprocess
from typing import Optional

try:
    from whisper_client import WhisperClient
except ImportError:
    WhisperClient = None

class VoiceTerminal:
    def __init__(
        self,
        command: list[str],
        whisper_host: str = "127.0.0.1",
        whisper_port: int = 8765,
        whisper_socket: Optional[str] = None,
        whisper_model: str = "mlx-community/whisper-tiny-mlx",
        auto_start_server: bool = True
    ):
        self.command = command
        self.whisper_host = whisper_host
        self.whisper_port = whisper_port
        self.whisper_socket = whisper_socket
        self.whisper_model = whisper_model
        self.auto_start_server = auto_start_server
        self.client: Optional[WhisperClient] = None
        self.server_process: Optional[subprocess.Popen] = None
        
        # 音频配置 (Whisper 强制要求 16kHz)
        self.fs = 16000
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.is_transcribing = False
        self.last_key_time = 0
        self.record_threshold = 0.6
        
        # 终端状态
        self.old_settings = None
        self.master_fd = None
        try:
            self.terminal_rows, self.terminal_cols = os.get_terminal_size()
        except:
            self.terminal_rows, self.terminal_cols = 24, 80

    def check_dependencies(self):
        """检查并提示必要依赖"""
        if WhisperClient is None:
            print("\r\n[错误] 缺少 whisper_client 模块")
            print("请确保 whisper_client.py 与 voice_agent.py 在同一目录")
            return False
        return True

    def start_whisper_server(self) -> bool:
        """启动 Whisper Server"""
        self.update_status("正在启动 Whisper Server...", "33")
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            server_script = os.path.join(script_dir, "whisper_server.py")
            
            if not os.path.exists(server_script):
                self.update_status("未找到 whisper_server.py", "31")
                return False
            
            cmd = [sys.executable, server_script, "--model", self.whisper_model]
            
            if self.whisper_socket:
                cmd.extend(["--socket", self.whisper_socket])
            else:
                cmd.extend(["--host", self.whisper_host, "--port", str(self.whisper_port)])
            
            self.server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
            # 等待服务器启动
            for i in range(30):
                time.sleep(0.5)
                if self._try_connect():
                    self.update_status("Server 已启动", "32")
                    return True
            
            self.update_status("Server 启动超时", "31")
            return False
            
        except Exception as e:
            self.update_status(f"启动失败: {str(e)[:20]}...", "31")
            return False
    
    def _try_connect(self) -> bool:
        """尝试连接服务器"""
        try:
            test_client = WhisperClient(
                host=self.whisper_host,
                port=self.whisper_port,
                socket_path=self.whisper_socket
            )
            return test_client.check_connection(self.fs)
        except:
            return False

    def connect_whisper_server(self) -> bool:
        """连接 Whisper Server，失败时自动启动"""
        self.update_status("正在连接 Whisper Server...", "33")
        try:
            self.client = WhisperClient(
                host=self.whisper_host,
                port=self.whisper_port,
                socket_path=self.whisper_socket
            )
            if self.client.check_connection(self.fs):
                self.update_status("已连接 Whisper Server", "32")
                return True
            else:
                # 连接失败，尝试自动启动
                if self.auto_start_server:
                    self.update_status("Server 未运行，正在启动...", "33")
                    if self.start_whisper_server():
                        # 重新创建客户端连接
                        self.client = WhisperClient(
                            host=self.whisper_host,
                            port=self.whisper_port,
                            socket_path=self.whisper_socket
                        )
                        return True
                
                self.update_status("Whisper Server 连接失败", "31")
                return False
        except Exception as e:
            # 连接异常，尝试自动启动
            if self.auto_start_server:
                self.update_status("Server 未运行，正在启动...", "33")
                if self.start_whisper_server():
                    self.client = WhisperClient(
                        host=self.whisper_host,
                        port=self.whisper_port,
                        socket_path=self.whisper_socket
                    )
                    return True
            
            self.update_status(f"连接失败: {str(e)[:20]}...", "31")
            return False

    def update_status(self, message: str, color_code: str = "32"):
        """使用 ANSI 转义码在终端底部打印非侵入式状态栏"""
        status_line = f"\x1b[s\x1b[{self.terminal_rows};1H\x1b[K\x1b[{color_code}m[MLX-Whisper] {message}\x1b[0m\x1b[u"
        os.write(sys.stdout.fileno(), status_line.encode('utf-8'))

    def audio_callback(self, indata, frames, time_info, status):
        """录音实时回调"""
        if self.is_recording:
            # 必须转换为 float32 才能由 mlx-whisper 处理
            self.audio_queue.put(indata.copy().astype(np.float32))

    def process_voice(self):
        """触发 Whisper 异步转录"""
        self.is_transcribing = True
        self.update_status("正在识别...", "35")
        
        audio_data = []
        while not self.audio_queue.empty():
            audio_data.append(self.audio_queue.get())
        
        if not audio_data:
            self.is_transcribing = False
            self.update_status("就绪")
            return

        # 合并所有音频片段
        recording = np.concatenate(audio_data, axis=0).flatten()
        
        def run_inference():
            try:
                result = self.client.transcribe(recording)
                text = result.text.strip()
                
                if text:
                    os.write(self.master_fd, (text).encode('utf-8'))
                    os.write(self.master_fd, b"\r\n")
                
                self.is_transcribing = False
                self.update_status("识别完成")
                time.sleep(0.5)
                self.update_status("就绪")
            except Exception as e:
                self.is_transcribing = False
                self.update_status(f"识别出错: {str(e)[:20]}...", "31")

        threading.Thread(target=run_inference, daemon=True).start()

    def cleanup(self):
        """清理资源"""
        if self.server_process:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=3)
            except:
                self.server_process.kill()

    def start(self):
        if not self.check_dependencies(): return
        if not self.connect_whisper_server(): return

        # 创建伪终端
        pid, self.master_fd = pty.fork()

        if pid == 0:  # 子进程
            os.execvp(self.command[0], self.command)
        
        # 父进程：配置终端为 Raw 模式以拦截按键
        self.old_settings = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())

        try:
            self.main_loop()
        finally:
            # 退出时恢复终端设置并清理状态栏
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_settings)
            os.write(sys.stdout.fileno(), f"\x1b[{self.terminal_rows};1H\x1b[K".encode())
            # 清理服务器进程
            self.cleanup()

    def main_loop(self):
        """主循环：处理按键拦截与 I/O 转发"""
        with sd.InputStream(samplerate=self.fs, channels=1, callback=self.audio_callback):
            while True:
                # 监控 stdin, master_fd
                rfds, _, _ = select.select([sys.stdin, self.master_fd], [], [], 0.05)
                
                now = time.time()

                # 自动检测 Ctrl+K 松开 (通过重复频率判定)
                if self.is_recording and (now - self.last_key_time > self.record_threshold):
                    self.is_recording = False
                    self.process_voice()

                if sys.stdin in rfds:
                    try:
                        data = os.read(sys.stdin.fileno(), 1024)
                        if not data: break
                        
                        # 检测 Ctrl+K (0x0b)
                        if b'\x0b' in data:
                            if not self.is_recording:
                                self.is_recording = True
                                self.update_status("录音中 (松开 Ctrl+K 停止)...", "31")
                                # 开启新录音前清空旧缓存
                                while not self.audio_queue.empty(): self.audio_queue.get()
                            
                            self.last_key_time = now
                            # 过滤掉 Ctrl+K，不发送给子进程
                            data = data.replace(b'\x0b', b'')

                        if data:
                            os.write(self.master_fd, data)
                    except EOFError: break

                if self.master_fd in rfds:
                    try:
                        data = os.read(self.master_fd, 4096)
                        if not data: break
                        # 将子进程输出转发到物理终端
                        os.write(sys.stdout.fileno(), data)
                    except OSError: break

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Voice Terminal with Whisper")
    parser.add_argument("--host", default="127.0.0.1", help="Whisper server host")
    parser.add_argument("--port", type=int, default=8765, help="Whisper server port")
    parser.add_argument("--socket", type=str, default=None, help="Unix socket path")
    parser.add_argument("--model", default="mlx-community/whisper-small-mlx", 
                       help="Whisper model (推荐 ModelScope: mlx-community/whisper-tiny-mlx)")
    parser.add_argument("--no-auto-start", action="store_true", help="Disable auto-start server")
    parser.add_argument("command", nargs="*", help="Command to run (default: $SHELL)")
    
    args = parser.parse_args()
    
    target_cmd = args.command if args.command else [os.environ.get("SHELL", "/bin/bash")]
    
    app = VoiceTerminal(
        command=target_cmd,
        whisper_host=args.host,
        whisper_port=args.port,
        whisper_socket=args.socket,
        whisper_model=args.model,
        auto_start_server=not args.no_auto_start
    )
    app.start()