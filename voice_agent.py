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
from typing import Optional

# 核心依赖：mlx-whisper 专门用于 MLX 框架下的 Whisper 推理
try:
    import mlx_whisper
except ImportError:
    mlx_whisper = None

# ModelScope 用于国内环境下高速下载模型
try:
    from modelscope import snapshot_download
except ImportError:
    snapshot_download = None

class VoiceTerminal:
    def __init__(self, command: list[str], model_id: str = "mlx-community/whisper-small-mlx"):
        self.command = command
        self.model_id = model_id
        self.local_model_path = None
        
        # 音频配置 (Whisper 强制要求 16kHz)
        self.fs = 16000
        self.audio_queue = queue.Queue()
        self.is_recording = False
        self.is_transcribing = False
        self.last_key_time = 0
        self.record_threshold = 0.6  # 判定松开按键的延迟时间
        
        # 终端状态
        self.old_settings = None
        self.master_fd = None
        # 初始化终端尺寸
        try:
            self.terminal_rows, self.terminal_cols = os.get_terminal_size()
        except:
            self.terminal_rows, self.terminal_cols = 24, 80

    def check_dependencies(self):
        """检查并提示必要依赖"""
        missing = []
        if mlx_whisper is None: missing.append("mlx-whisper")
        if snapshot_download is None: missing.append("modelscope")
        
        if missing:
            print(f"\r\n[错误] 缺少必要组件: {', '.join(missing)}")
            print(f"请执行: pip install {' '.join(missing)} sounddevice numpy")
            return False
        return True

    def update_status(self, message: str, color_code: str = "32"):
        """使用 ANSI 转义码在终端底部打印非侵入式状态栏"""
        # 保存光标 -> 移动到最后一行 -> 清行 -> 打印 -> 恢复光标
        status_line = f"\x1b[s\x1b[{self.terminal_rows};1H\x1b[K\x1b[{color_code}m[MLX-Whisper] {message}\x1b[0m\x1b[u"
        os.write(sys.stdout.fileno(), status_line.encode('utf-8'))

    def load_model(self):
        """通过 ModelScope 下载并定位本地模型"""
        self.update_status(f"正在从 ModelScope 下载/校验模型: {self.model_id}...", "33")
        try:
            # 下载模型到本地缓存，返回本地路径
            self.local_model_path = snapshot_download(self.model_id)
            self.update_status("模型就绪", "32")
            return True
        except Exception as e:
            self.update_status(f"模型加载失败: {str(e)}", "31")
            return False

    def audio_callback(self, indata, frames, time_info, status):
        """录音实时回调"""
        if self.is_recording:
            # 必须转换为 float32 才能由 mlx-whisper 处理
            self.audio_queue.put(indata.copy().astype(np.float32))

    def process_voice(self):
        """触发 MLX Whisper 异步转录"""
        self.is_transcribing = True
        self.update_status("正在进行 MLX 推理...", "35")
        
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
                # 调用 mlx_whisper 进行本地 GPU 加速识别
                # path_or_hf_repo 传入 ModelScope 的本地路径
                result = mlx_whisper.transcribe(
                    recording, 
                    path_or_hf_repo=self.local_model_path
                )
                text = result["text"].strip()
                
                if text:
                    # 将文字写入 PTY master，并在末尾加空格和回车符以执行命令
                    os.write(self.master_fd, (text).encode('utf-8'))
                    os.write(self.master_fd, b"\r")
                
                self.is_transcribing = False
                self.update_status("识别完成")
                # 短暂延迟后恢复就绪状态
                time.sleep(0.5)
                self.update_status("就绪")
            except Exception as e:
                self.is_transcribing = False
                self.update_status(f"识别出错: {str(e)[:20]}...", "31")

        # 使用守护线程，防止阻塞终端 I/O
        threading.Thread(target=run_inference, daemon=True).start()

    def start(self):
        if not self.check_dependencies(): return
        if not self.load_model(): return

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
    # 默认执行 zsh 或 bash，支持指定命令，如: python voice_terminal.py claude
    target_cmd = sys.argv[1:] if len(sys.argv) > 1 else [os.environ.get("SHELL", "/bin/bash")]
    app = VoiceTerminal(target_cmd)
    app.start()