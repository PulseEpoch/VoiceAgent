# Voice Terminal - Bidirectional Voice Terminal

## [中文文档 (Chinese Documentation)](./README-zh.md)

A PTY wrapper that adds voice interaction capabilities to command-line AI assistants (like Devin/Claude CLI).

## Core Features

- **Voice Input (STT)**: Hold Ctrl+K to record, release to transcribe to text via Whisper model, automatically injected into terminal input with carriage return to execute commands
- **Voice Output (TTS)**: Press Ctrl+T to toggle reading mode, AI responses are automatically synthesized and played via Qwen3-TTS

## Architecture Design

- **Voice Terminal (voice_agent.py)**: Complete solution that combines PTY wrapper, STT (speech-to-text) functionality with MLX Whisper model, and handles keyboard shortcuts. Captures keyboard inputs, processes voice commands, and maintains native terminal experience.

## Key Technologies

- **Key Detection**: Uses keyboard repeat mechanism (repeat rate) to determine Ctrl+K press/release state, considers released if no new bytes for over 0.6s
- **PTY Passthrough**: pty.fork() creates pseudo-terminal, fully passes through stdin/stdout, uses terminal query library to avoid garbled text
- **TTS Buffering**: Caches PTY output, triggers synthesis after detecting 2s pause; async playback in background doesn't block terminal
- **Server Auto-Start**: Client detects and automatically launches server processes on first call

## Environment Setup

### 1. Create Conda Environment

```bash
conda create -n voice-agent python=3.11 -y
conda activate voice-agent
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Dependency Notes

- **MLX Framework**: Apple Silicon acceleration (mlx, mlx-lm, mlx-whisper)
- **Audio Processing**: sounddevice, soundfile, numpy
- **Model Download**: modelscope (prefer downloading models from ModelScope)
- **TTS Model**: torch, transformers

## Usage

### Quick Start

1. Activate environment:
```bash
conda activate voice-agent
```

2. Run client:
```bash
python voice_agent.py
```

The program will automatically detect and start required server processes.

### Shortcut Keys

| Shortcut | Function |
|----------|----------|
| Ctrl+K   | Hold to record, release for speech recognition |
| Ctrl+T   | Toggle TTS reading mode (on/off) |
| Ctrl+D / exit | Exit Voice Terminal |

### Notes

The program is a standalone solution that handles all voice processing internally. No separate server processes are required.

## Project Structure

```
agent-voice-shell/
├── README.md              # Project documentation
├── README-zh.md           # Chinese project documentation
├── requirements.txt       # Python dependencies
└── voice_agent.py         # Main program (Voice-enabled terminal with STT functionality)
```

## Tech Stack

- **Python**: Primary development language
- **MLX**: Apple Silicon acceleration framework
- **MLX Whisper**: Speech recognition model for Apple Silicon
- **ModelScope**: Model download platform
- **sounddevice**: Audio input/output
- **PTY**: Pseudo-terminal
- **NumPy**: Numerical computations for audio processing

## Notes

1. This project is optimized for Apple Silicon, leveraging MLX framework for hardware-accelerated inference
2. First run will automatically download models from ModelScope, requires internet connection
3. Ensure system has recording and playback permissions
4. The application handles both voice input and terminal interaction in a single process

## License

MIT License