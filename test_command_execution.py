#!/usr/bin/env python3
"""测试命令执行"""
import os
import pty
import time
import sys

print("测试 PTY 命令执行\n")

# Fork PTY
pid, master_fd = pty.fork()

if pid == 0:  # 子进程
    os.execvp("bash", ["bash"])
else:  # 父进程
    time.sleep(0.5)
    
    # 测试1: 写入命令 + 回车
    print("1. 发送: echo 'test1'")
    os.write(master_fd, b"echo 'test1'\r")
    time.sleep(0.5)
    
    # 测试2: 写入命令 + \n
    print("2. 发送: echo 'test2' (with \\n)")
    os.write(master_fd, b"echo 'test2'\n")
    time.sleep(0.5)
    
    # 测试3: 分开写入
    print("3. 发送: echo 'test3' (separate)")
    os.write(master_fd, b"echo 'test3'")
    os.write(master_fd, b"\r")
    time.sleep(0.5)
    
    # 测试4: opencode 命令
    print("4. 发送: echo 'opencode test'")
    os.write(master_fd, b"echo 'opencode test'\r")
    time.sleep(0.5)
    
    # 退出
    os.write(master_fd, b"exit\r")
    time.sleep(0.2)
    
    print("\n完成")
