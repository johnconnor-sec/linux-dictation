# Linux Voice Dictation

A native Linux application for system-wide voice dictation, similar to Windows' `Win+H` or macOS's "Dictation".

## Features

- **System-wide:** Works in (almost) any application.
- **Open Source STT:** Uses `faster-whisper` (an optimized Whisper implementation) for high-quality transcription.
- **Global Hotkey:** Activate/deactivate dictation with a configurable keyboard shortcut.
- **Continuous Dictation:** Keeps listening until stopped or silence timeout.
- **Text Insertion:** Automatically types transcribed text into the focused window.
- **Configurable:** Change hotkey, language, STT model, performance settings, etc. via `config.ini`.
- **System Tray Icon:** Provides status feedback (idle, listening, processing, error) and quick access to actions.
- **Wayland Considerations:** Includes options (`pynput`, `ydotool`) for text insertion, but global hotkeys and input simulation on Wayland require specific user permissions.

## Requirements

- Python 3.7+
- PortAudio library (`libportaudio2` on Debian/Ubuntu, `portaudio` on Fedora/Arch)
- `ffmpeg` (for audio conversion if needed by Whisper, though `sounddevice` usually handles format)
- (Optional but recommended for `ydotool`) `ydotool` and the `ydotoold` service running.
- (Optional for GPU) NVIDIA GPU, CUDA Toolkit, cuDNN.

## Installation

1. **Install System Dependencies:**

   - **Debian/Ubuntu:**

     ```bash
     sudo apt update
     sudo apt install python3 python3-pip python3-venv libportaudio2 ffmpeg
     # Optional for ydotool:
     # sudo apt install ydotool # (May need newer repo or manual install for latest)
     ```

   - **Fedora:**

     ```bash
     sudo dnf install python3 python3-pip python3-tkinter portaudio-devel ffmpeg-free
     # Optional for ydotool:
     # sudo dnf install ydotool
     ```

   - **Arch Linux:**

     ```bash
     sudo pacman -Syu python python-pip tk portaudio ffmpeg
     # Optional for ydotool:
     # sudo pacman -S ydotool
     ```

2. **Create a Virtual Environment (Recommended):**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install Python Packages:**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

   - **GPU Support:** If you have an NVIDIA GPU and CUDA installed, install the GPU-enabled `ctranslate2` and CUDA libraries _before_ installing `faster-whisper` via `requirements.txt`. Follow instructions on the [CTranslate2](https://github.com/OpenNMT/CTranslate2) and [faster-whisper](https://github.com/guillaumekln/faster-whisper) pages. E.g., for CUDA 12:

     ```bash
     # Deactivate venv first if requirements.txt was already installed
     # deactivate
     # source .venv/bin/activate
     pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 # Adjust cuXX for your CUDA version
     pip install -U ctranslate2 --extra-index-url https://pip.download.nvidia.com/compute-ctranslate2/redist/ # Check CTranslate2 docs for latest URL/method
     pip install -r requirements.txt # Now install the rest
     ```

4. **Configure:**

   - Copy `config.ini.example` to `~/.config/linux-dictation/config.ini`.

     ```bash
     mkdir -p ~/.config/linux-dictation
     cp config.ini.example ~/.config/linux-dictation/config.ini
     ```

   - Edit `~/.config/linux-dictation/config.ini` to set your preferred `activation_hotkey`, `language`, `model_size`, `device` (cpu/cuda), etc.

5. **Permissions (CRITICAL for Wayland and some X11 setups):**

   - **Global Hotkey (`keyboard` library):** This library often needs access to `/dev/input/event*` devices.

     - **Option A (Recommended):** Add your user to the `input` group:

       ```bash
       sudo usermod -a -G input $USER
       ```

       **You MUST log out and log back in for this change to take effect.**

     - **Option B (Less Secure):** Run the script with `sudo`:

       ```bash
       sudo python main.py
       # Or if using venv: sudo .venv/bin/python main.py
       ```

       _(Note: Running GUI apps with sudo is generally discouraged. User config might also be saved to root's home.)_

   - **Text Input (`pynput` on Wayland / `ydotool`):**

     - `pynput` might work on some Wayland compositors if the `input` group permissions are set, but it's not guaranteed.
     - `ydotool` is often more reliable on Wayland but requires `ydotoold` to be running as a systemd service (usually system-wide or user-specific).

       ```bash
       # Start ydotoold (example for user service)
       systemctl --user start ydotoold.service
       # Enable ydotoold to start on login
       systemctl --user enable ydotoold.service
       ```

       Ensure `text_inserter = ydotool` is set in `config.ini`.

## Usage

1. **Activate Virtual Environment (if used):**

   ```bash
   source .venv/bin/activate
   ```

2. **Run the Application:**

   ```bash
   python main.py
   ```

   A system tray icon should appear.

3. **Press Your Hotkey:** Press the `activation_hotkey` defined in your `config.ini` (default: `Ctrl+Alt+D`).
4. **Dictate:** Start speaking. The tray icon should change (e.g., to green).
5. **Text Appears:** Transcribed text will be typed into the currently focused application window.
6. **Stop Dictation:** Press the hotkey again. The icon will change (e.g., orange while finishing, then blue). Or, wait for the `silence_timeout` if configured > 0.
7. **Configure:** Right-click the tray icon and select "Configure" to change settings.
8. **Quit:** Right-click the tray icon and select "Quit".

## Model Downloads

The first time you run dictation with a specific model size, `faster-whisper` will download the model files (this may take some time) and cache them, usually in `~/.cache/faster_whisper`.

## Troubleshooting

- **Hotkey Not Working:**
  - Check permissions (see Installation Step 5). Did you log out/in after adding user to `input` group?
  - Is another application using the same hotkey? Try a different combination in `config.ini`.
  - Run `sudo python main.py` temporarily to see if it's purely a permission issue.
- **Text Not Appearing:**
  - Check permissions (see Installation Step 5).
  - If on Wayland, try switching `text_inserter` to `ydotool` in `config.ini` and ensure `ydotoold` service is running.
  - Check application logs for errors related to `pynput` or `ydotool`.
  - Ensure the target application window is focused.
- **Poor Transcription Quality:**
  - Try a larger model size in `config.ini` (e.g., `small.en`, `medium.en`). Requires more resources.
  - Ensure the correct `language` is set.
  - Check microphone input level and quality in system sound settings.
  - Adjust `beam_size` or `initial_prompt` in the `[Whisper]` section of `config.ini`.
  - Try enabling/disabling `use_vad_filter`.
- **High CPU Usage:**
  - Use a smaller model (`tiny.en`, `base.en`).
  - Ensure `device = cpu` and try different `compute_type` options like `int8` (usually faster on CPU). Requires `pip install ctranslate2>=3.10.0,<4.0.0` if not already installed.
  - If using GPU (`device = cuda`), ensure drivers and CUDA libraries are correctly installed. Try `compute_type = float16` or `int8_float16`.
- **Error Loading Model:** Check internet connection for download, sufficient disk space in `~/.cache`, and RAM/VRAM availability.
- **Error related to `pystray` or `tkinter`:** Ensure system packages like `python3-tk` and potentially `python3-gi` (for some `pystray` backends) are installed.

## Limitations & Future Improvements

[ ] **Wayland Robustness:** Global hotkeys and input injection remain challenging on Wayland. Success depends heavily on the compositor, setup, and permissions.
[ ] **Error Reporting:** Improve user feedback for errors (e.g., more specific tray notifications).
[ ] **Audio Device Selection:** Implement a GUI dropdown for audio devices.
[ ] **Alternative STT Engines:** Add support for Vosk or others.
[ ] **Packaging:** Create `.deb`, `.rpm`, or AppImage packages for easier distribution.
[ ] **More Sophisticated VAD:** Implement more advanced silence detection or use STT engine's VAD more effectively to manage continuous dictation segments.
