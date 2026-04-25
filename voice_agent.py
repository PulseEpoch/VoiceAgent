import os
import sys
import pty
import tty
import termios
import select
import signal
import struct
import fcntl
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
        whisper_model: str = "mlx-community/whisper-medium-mlx",
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
        self._reconnecting = False  # Prevent nested reconnection attempts
        
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
        self._child_pid = None
        self._update_terminal_size()

    def _update_terminal_size(self):
        """Read current terminal dimensions and propagate to the PTY slave.
        The PTY gets one fewer row to reserve the status bar line."""
        try:
            size = os.get_terminal_size()
            self.terminal_rows, self.terminal_cols = size.lines, size.columns
        except OSError:
            self.terminal_rows, self.terminal_cols = 24, 80
        if self.master_fd is not None:
            pty_rows = max(1, self.terminal_rows - 1)
            winsize = struct.pack("HHHH", pty_rows, self.terminal_cols, 0, 0)
            try:
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass

    def _sigwinch_handler(self, signum, frame):
        """Handle terminal resize: update dimensions and notify the child PTY."""
        self._update_terminal_size()

    def _sigchld_handler(self, signum, frame):
        """Reap zombie child processes."""
        try:
            while True:
                pid, _ = os.waitpid(-1, os.WNOHANG)
                if pid <= 0:
                    break
        except ChildProcessError:
            pass

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
            script_dir = os.path.dirname(os.path.realpath(__file__))
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
                # 如果进程已崩溃，提前退出
                if self.server_process.poll() is not None:
                    self.update_status("Server 进程异常退出", "31")
                    return False
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
            return WhisperClient(
                host=self.whisper_host,
                port=self.whisper_port,
                socket_path=self.whisper_socket
            ).check_connection(self.fs)
        except Exception:
            return False

    def _handle_server_failure(self) -> bool:
        """Callback for when server connection fails. Attempts to restart the server.
        Returns True if server was successfully restarted."""
        if self._reconnecting:
            return False

        self._reconnecting = True
        try:
            self.update_status("Server 断开，正在重连...", "33", inline=True)

            # Clean up old server process if it exists
            if self.server_process:
                try:
                    self.server_process.terminate()
                    self.server_process.wait(timeout=2)
                except:
                    try:
                        self.server_process.kill()
                    except:
                        pass
                self.server_process = None

            # Restart the server
            if self.auto_start_server and self.start_whisper_server():
                self.update_status("Server 已重连", "32", inline=True)
                return True

            self.update_status("Server 重连失败", "31", inline=True)
            return False

        finally:
            self._reconnecting = False

    def connect_whisper_server(self) -> bool:
        """连接 Whisper Server，失败时自动启动"""
        self.update_status("正在连接 Whisper Server...", "33")
        try:
            self.client = WhisperClient(
                host=self.whisper_host,
                port=self.whisper_port,
                socket_path=self.whisper_socket,
                max_retries=3,
                retry_delay=0.5,
                on_reconnect=self._handle_server_failure
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
                            socket_path=self.whisper_socket,
                            max_retries=3,
                            retry_delay=0.5,
                            on_reconnect=self._handle_server_failure
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
                        socket_path=self.whisper_socket,
                        max_retries=3,
                        retry_delay=0.5,
                        on_reconnect=self._handle_server_failure
                    )
                    return True

            self.update_status(f"连接失败: {str(e)[:20]}...", "31")
            return False

    def update_status(self, message: str, color_code: str = "32", inline: bool = False):
        """显示状态消息。
        inline=True：写入倒数第二行状态栏（录音/识别等需要可见的提示）。
        inline=False：写入窗口标题（次要信息，不占屏幕空间）。
        """
        fd = sys.stdout.fileno()
        # 窗口标题始终更新
        try:
            os.write(fd, f"\x1b]0;[MLX-Whisper] {message}\x07".encode('utf-8'))
        except OSError:
            pass
        if not inline:
            return
        # 倒数第二行状态栏：\x1b7 保存光标，\x1b8 恢复，不触发滚动
        status_row = max(1, self.terminal_rows - 1)
        bar = (
            f"\x1b7"                                              # 保存光标（DEC）
            f"\x1b[{status_row};1H\x1b[K"                        # 跳到状态行并清空
            f"\x1b[{color_code}m[MLX-Whisper] {message}\x1b[0m"  # 写消息
            f"\x1b8"                                              # 恢复光标（DEC）
        )
        try:
            os.write(fd, bar.encode('utf-8'))
        except OSError:
            pass

    def clear_status(self):
        """清除倒数第二行状态栏"""
        fd = sys.stdout.fileno()
        status_row = max(1, self.terminal_rows - 1)
        try:
            os.write(fd, f"\x1b7\x1b[{status_row};1H\x1b[K\x1b8".encode('utf-8'))
            os.write(fd, b"\x1b]0;\x07")  # 重置窗口标题
        except OSError:
            pass

    def audio_callback(self, indata, frames, time_info, status):
        """录音实时回调"""
        if self.is_recording:
            # 必须转换为 float32 才能由 mlx-whisper 处理
            self.audio_queue.put(indata.copy().astype(np.float32))

    def process_voice(self):
        """触发 Whisper 异步转录"""
        self.is_transcribing = True
        self.update_status("正在识别...", "35", inline=True)
        
        audio_data = []
        while not self.audio_queue.empty():
            audio_data.append(self.audio_queue.get())
        
        if not audio_data:
            self.is_transcribing = False
            return

        # 合并所有音频片段
        recording = np.concatenate(audio_data, axis=0).flatten()
        
        def run_inference():
            try:
                result = self.client.transcribe(recording)
                text = result.text.strip()
                
                if text:
                    # 逐块写入文字，模拟用户打字，避免子进程丢字符
                    text_bytes = text.encode('utf-8')
                    chunk_size = 64
                    for i in range(0, len(text_bytes), chunk_size):
                        os.write(self.master_fd, text_bytes[i:i+chunk_size])
                        time.sleep(0.01)
                    # PTY 中用 \r 触发回车（line discipline 会将其转为 \n 传给子进程）
                    time.sleep(0.05)
                    os.write(self.master_fd, b"\r")
                
                self.is_transcribing = False
                self.clear_status()
            except Exception as e:
                self.is_transcribing = False
                self.update_status(f"识别出错: {str(e)[:20]}...", "31", inline=True)

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

        # 读取真实终端尺寸
        self._update_terminal_size()

        # 用 openpty 代替 pty.fork，先设好 slave 尺寸再 fork，
        # 保证子进程启动时读到的 TIOCGWINSZ 已经是正确值
        self.master_fd, slave_fd = pty.openpty()
        pty_rows = max(1, self.terminal_rows - 1)
        winsize = struct.pack("HHHH", pty_rows, self.terminal_cols, 0, 0)
        fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, winsize)

        self._child_pid = os.fork()
        if self._child_pid == 0:  # 子进程
            os.close(self.master_fd)
            # 让 slave 成为控制终端
            os.setsid()
            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            # 把 slave 接到标准 I/O
            for fd in (0, 1, 2):
                os.dup2(slave_fd, fd)
            if slave_fd > 2:
                os.close(slave_fd)
            os.execvp(self.command[0], self.command)

        # 父进程
        os.close(slave_fd)
        signal.signal(signal.SIGWINCH, self._sigwinch_handler)
        signal.signal(signal.SIGCHLD, self._sigchld_handler)

        # 配置终端为 Raw 模式以拦截按键
        self.old_settings = termios.tcgetattr(sys.stdin.fileno())
        tty.setraw(sys.stdin.fileno())

        try:
            self.main_loop()
        finally:
            # 退出时恢复终端设置并清理状态栏
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_settings)
            self.clear_status()
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
                                self.update_status("录音中 (松开 Ctrl+K 停止)...", "31", inline=True)
                                # 开启新录音前清空旧缓存
                                while not self.audio_queue.empty(): self.audio_queue.get()
                            
                            self.last_key_time = now
                            # 过滤掉 Ctrl+K，不发送给子进程
                            data = data.replace(b'\x0b', b'')

                        if data:
                            try:
                                os.write(self.master_fd, data)
                            except OSError:
                                break
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
    parser.add_argument("--model", default="mlx-community/whisper-medium-mlx",
                       help="Whisper model (推荐: mlx-community/whisper-medium-mlx)")
    parser.add_argument("--no-auto-start", action="store_true", help="Disable auto-start server")
    parser.add_argument("command", nargs="*", help="Command to run (default: $SHELL)")

    args, extra = parser.parse_known_args()
    target_cmd = (args.command + extra) if (args.command or extra) else [os.environ.get("SHELL", "/bin/bash")]
    
    app = VoiceTerminal(
        command=target_cmd,
        whisper_host=args.host,
        whisper_port=args.port,
        whisper_socket=args.socket,
        whisper_model=args.model,
        auto_start_server=not args.no_auto_start
    )
    app.start()