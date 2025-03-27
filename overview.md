**Design Choices:**

1.  **Language:** Python 3 - Rich ecosystem for audio, STT, system interaction, and GUI. Relatively easy to develop and maintain.
2.  **STT Engine:** `faster-whisper` - A reimplementation of OpenAI's Whisper using CTranslate2, offering significant speedups (especially on CPU) and lower memory usage compared to the original PyTorch implementation. It supports VAD (Voice Activity Detection) and punctuation.
3.  **Audio Capture:** `sounddevice` - Cross-platform library based on PortAudio, simple API.
4.  **Hotkey:** `keyboard` - Pure Python library, aims to work on Windows, Linux (X11 & Wayland via `evdev` - *requires permissions*), and macOS.
5.  **Text Insertion:** `pynput` - Provides keyboard control (typing simulation). Works well on X11, *may* require permissions or alternative methods (like `ydotool`) on Wayland. We'll primarily use `pynput` and mention Wayland alternatives.
6.  **Configuration:** `configparser` (built-in) for INI-style files.
7.  **GUI/Feedback:** `pystray` for a system tray icon providing status and basic controls (start/stop/configure/quit). `tkinter` for the configuration window.
8.  **Threading:** Essential for responsiveness. Separate threads for hotkey listening, audio processing/STT, and the main application/tray icon loop.
9.  **Wayland Considerations:** Global hotkeys and input simulation are inherently problematic on Wayland due to its security model.
    *   The `keyboard` library often needs root privileges or the user to be in the `input` group to access `/dev/input/event*` devices on Wayland.
    *   `pynput`'s keyboard simulation might not work reliably on all Wayland compositors. An alternative is using `ydotool` (requires `ydotoold` service running), which we can integrate as a fallback or configurable option. We'll start with `pynput` and document the Wayland challenge.
