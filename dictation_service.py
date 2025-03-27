import threading
import queue
import time
import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput.keyboard import Controller as PynputController
import subprocess # For ydotool

# Simple VAD based on energy threshold (if faster-whisper VAD isn't used or sufficient)
SILENCE_THRESHOLD = 500 # Adjust based on microphone sensitivity
CHUNK_DURATION_MS = 500 # Corresponds to block_size in config

class DictationService:
    def __init__(self, config):
        self.config = config
        self.status_queue = queue.Queue() # To report status changes (idle, listening, processing, error)
        self.text_queue = queue.Queue()   # To send transcribed text for insertion

        self._load_config()

        self.is_running = False
        self.is_dictating = False
        self.audio_stream = None
        self.stt_thread = None
        self.audio_queue = queue.Queue()
        self.last_speech_time = time.time()

        self.stt_model = None # Lazy load
        self.pynput_kb = None
        if self.text_inserter == 'pynput':
            try:
                self.pynput_kb = PynputController()
            except Exception as e:
                print(f"Error initializing pynput Controller: {e}. Text insertion might fail.")
                self.status_queue.put(("error", f"Pynput init failed: {e}"))


    def _load_config(self):
        """Load settings from the config object."""
        self.language = self.config.get('General', 'language')
        self.model_size = self.config.get('General', 'model_size')
        self.device = self.config.get('General', 'device')
        self.compute_type = self.config.get('General', 'compute_type')
        self.use_vad = self.config.getboolean('Whisper', 'use_vad_filter')
        self.beam_size = self.config.getint('Whisper', 'beam_size')
        self.initial_prompt = self.config.get('Whisper', 'initial_prompt') or None
        self.sample_rate = self.config.getint('Advanced', 'sample_rate')
        self.block_size = self.config.getint('Advanced', 'block_size')
        self.audio_device = self.config.get('Advanced', 'audio_device') or None # Use None for default
        self.silence_timeout = self.config.getfloat('General', 'silence_timeout')
        self.text_inserter = self.config.get('General', 'text_inserter').lower()


    def _load_stt_model(self):
        """Loads the STT model if not already loaded."""
        if self.stt_model is None:
            try:
                self.status_queue.put(("processing", "Loading STT model..."))
                print(f"Loading model: {self.model_size} ({self.device}, {self.compute_type})")
                # Check ~/.cache/faster_whisper for existing models first
                self.stt_model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
                print("Model loaded.")
                self.status_queue.put(("idle", "Model loaded")) # Or back to previous state if needed
            except Exception as e:
                print(f"Error loading STT model: {e}")
                self.status_queue.put(("error", f"Model load failed: {e}"))
                self.stt_model = None # Ensure it stays None on failure

    def _audio_callback(self, indata, frames, time_info, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(f"Audio callback status: {status}", file=sys.stderr)
        if self.is_dictating:
            # Basic RMS energy VAD (optional layer)
            rms = np.sqrt(np.mean(indata**2))
            # print(f"RMS: {rms:.2f}") # Debug VAD
            is_speech = rms > (SILENCE_THRESHOLD / 32768.0) # Normalize threshold for float data

            if is_speech:
                self.last_speech_time = time.time()

            # Put audio data into the queue for the STT thread
            self.audio_queue.put(indata.copy())

    def _stt_worker(self):
        """Thread worker function for running STT."""
        self._load_stt_model()
        if not self.stt_model:
            self.is_dictating = False # Stop if model failed to load
            self.status_queue.put(("idle", "Dictation stopped (model load failed)"))
            return

        print("STT worker started.")
        audio_buffer = np.array([], dtype=np.float32)

        while self.is_dictating or not self.audio_queue.empty():
            try:
                # Get audio data, wait if necessary but with a timeout
                try:
                    chunk = self.audio_queue.get(timeout=0.1)
                    audio_buffer = np.concatenate((audio_buffer, chunk))
                except queue.Empty:
                    # No new audio, check silence timeout
                    if self.is_dictating and self.silence_timeout > 0 and (time.time() - self.last_speech_time) > self.silence_timeout:
                        print("Silence timeout reached.")
                        self.toggle_dictation() # Signal to stop
                        # Process any remaining buffer before exiting loop
                        if audio_buffer.size == 0:
                             continue # Nothing left to process

                    # If not dictating anymore, process remaining buffer then exit
                    elif not self.is_dictating and audio_buffer.size == 0:
                        break
                    # If waiting for more audio or timeout not reached, continue loop
                    elif self.is_dictating:
                        continue
                    # If stopped and buffer has data, process it one last time below


                # --- Transcribe when enough data or stopping ---
                # Decide when to transcribe. Simple approach: process buffer when it's long enough
                # or when stopping. A better approach would involve VAD more intelligently.
                buffer_duration_sec = len(audio_buffer) / self.sample_rate

                # Process if buffer is reasonably long OR if we are stopping and have data
                should_process = buffer_duration_sec > 1.0 or (not self.is_dictating and audio_buffer.size > self.sample_rate * 0.2) # Process min 0.2s on stop

                if should_process and self.stt_model:
                    # print(f"Processing {buffer_duration_sec:.2f}s of audio...")
                    self.status_queue.put(("processing", "Transcribing..."))

                    segments, info = self.stt_model.transcribe(
                        audio_buffer,
                        language=self.language if self.language != 'auto' else None,
                        beam_size=self.beam_size,
                        vad_filter=self.use_vad,
                        initial_prompt=self.initial_prompt,
                        word_timestamps=False # Keep it simpler for now
                    )

                    full_text = ""
                    for segment in segments:
                        # print(f"Segment: {segment.text}")
                        full_text += segment.text

                    if full_text.strip():
                        self.text_queue.put(full_text.lstrip()) # Remove leading space often added
                        self.last_speech_time = time.time() # Reset silence timer on getting text

                    # Clear buffer after processing
                    audio_buffer = np.array([], dtype=np.float32)
                    self.status_queue.put(("listening", "Listening...")) # Back to listening

            except Exception as e:
                print(f"Error in STT worker: {e}")
                self.status_queue.put(("error", f"STT Error: {e}"))
                # Maybe add a delay or break? For now, continue.

        print("STT worker finished.")
        # Ensure final state is idle if we exited loop
        if not self.is_dictating:
            self.status_queue.put(("idle", "Dictation stopped"))

    def _text_insertion_worker(self):
        """Thread worker for inserting text using the chosen method."""
        while self.is_running:
            try:
                text = self.text_queue.get(timeout=0.5) # Wait briefly for text
                if text:
                    self._insert_text(text)
                    self.text_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error inserting text: {e}")
                self.status_queue.put(("error", f"Text insert failed: {e}"))

    def _insert_text(self, text):
        """Inserts text using pynput or ydotool."""
        print(f"Inserting text: {text}")
        if not text:
            return

        try:
            if self.text_inserter == 'pynput':
                if self.pynput_kb:
                    # Add a space before inserting if the text doesn't start with one
                    # This helps separate consecutive dictation results.
                    # However, Whisper often adds leading spaces itself, so lstrip in _stt_worker
                    # might be better. Let's type as is for now.
                    self.pynput_kb.type(text)
                else:
                    raise RuntimeError("Pynput keyboard controller not initialized.")
            elif self.text_inserter == 'ydotool':
                # Ensure ydotool is installed and ydotoold is running
                subprocess.run(['ydotool', 'type', text], check=True)
            else:
                print(f"Warning: Unknown text_inserter '{self.text_inserter}'. Defaulting to pynput.")
                if self.pynput_kb:
                    self.pynput_kb.type(text)
                else:
                    raise RuntimeError("Pynput keyboard controller not initialized.")

            # Optional: Add a space after insertion if desired?
            # if self.pynput_kb and self.text_inserter == 'pynput':
            #     self.pynput_kb.type(' ')
            # elif self.text_inserter == 'ydotool':
            #      subprocess.run(['ydotool', 'key', 'space'], check=True)

        except FileNotFoundError:
            if self.text_inserter == 'ydotool':
                 print("Error: 'ydotool' command not found. Is it installed and in PATH?")
                 self.status_queue.put(("error","ydotool not found"))
            else: # Should not happen for pynput unless internal error
                 raise
        except subprocess.CalledProcessError as e:
             print(f"Error executing ydotool: {e}. Is ydotoold running?")
             self.status_queue.put(("error",f"ydotool failed: {e}"))
        except Exception as e:
            print(f"General error during text insertion ({self.text_inserter}): {e}")
            self.status_queue.put(("error",f"Insert failed: {e}"))


    def start(self):
        """Starts the background services (text insertion)."""
        print("Starting Dictation Service...")
        self.is_running = True
        # Start text insertion thread
        self.text_insert_thread = threading.Thread(target=self._text_insertion_worker, daemon=True)
        self.text_insert_thread.start()
        self.status_queue.put(("idle", "Ready"))

    def stop(self):
        """Stops all services and threads."""
        print("Stopping Dictation Service...")
        if self.is_dictating:
            self.toggle_dictation() # Stop dictation first

        self.is_running = False
        # Wait briefly for threads to notice the flag
        time.sleep(0.2)

        # Signal queues if needed (e.g., put None to unblock) - less critical with timeouts/daemon threads
        # self.text_queue.put(None) # If text_insert_thread waits indefinitely

        if self.text_insert_thread and self.text_insert_thread.is_alive():
            self.text_insert_thread.join(timeout=1.0)

        # STT thread should stop when is_dictating becomes false and queue is empty
        if self.stt_thread and self.stt_thread.is_alive():
             self.stt_thread.join(timeout=1.0)

        # Clean up audio stream if it's somehow still open
        if self.audio_stream:
            try:
                if not self.audio_stream.closed:
                    self.audio_stream.stop()
                    self.audio_stream.close()
            except Exception as e:
                print(f"Error closing audio stream: {e}")
            self.audio_stream = None

        print("Dictation Service stopped.")
        self.status_queue.put(("offline", "Stopped"))


    def toggle_dictation(self):
        """Starts or stops the dictation process."""
        if not self.is_running:
            print("Service not running. Cannot toggle dictation.")
            return

        if not self.is_dictating:
            # --- Start Dictation ---
            if not self.stt_model: # Lazy load model on first activation
                self._load_stt_model()
                if not self.stt_model: # Check if loading failed
                     print("Cannot start dictation: STT model failed to load.")
                     # status_queue already updated by _load_stt_model on error
                     return

            try:
                print("Starting dictation...")
                self.last_speech_time = time.time() # Reset silence timer
                # Clear queues
                while not self.audio_queue.empty(): self.audio_queue.get_nowait()
                while not self.text_queue.empty(): self.text_queue.get_nowait()

                self.audio_stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    blocksize=self.block_size,
                    device=self.audio_device,
                    channels=1,
                    dtype='float32',
                    callback=self._audio_callback
                )
                self.audio_stream.start()
                self.is_dictating = True

                # Start STT worker thread
                self.stt_thread = threading.Thread(target=self._stt_worker, daemon=True)
                self.stt_thread.start()

                self.status_queue.put(("listening", "Listening..."))
                print("Dictation active.")

            except Exception as e:
                print(f"Error starting audio stream: {e}")
                self.status_queue.put(("error", f"Audio start failed: {e}"))
                if self.audio_stream:
                    try:
                        self.audio_stream.close()
                    except Exception: pass # Ignore errors during cleanup on failure
                    self.audio_stream = None
                self.is_dictating = False # Ensure state is correct
        else:
            # --- Stop Dictation ---
            print("Stopping dictation...")
            self.is_dictating = False # Signal threads to stop

            if self.audio_stream:
                try:
                    if not self.audio_stream.closed:
                        self.audio_stream.stop()
                        self.audio_stream.close()
                    print("Audio stream stopped and closed.")
                except Exception as e:
                    print(f"Error stopping/closing audio stream: {e}")
                self.audio_stream = None
            else:
                print("Audio stream was already None.")


            # STT thread will finish processing remaining audio and exit
            # Text insertion thread keeps running
            self.status_queue.put(("processing", "Finishing transcription...")) # Indicate final processing
            # STT worker will send ("idle", ...) when done.

    def reload_config(self, new_config):
        """Reloads configuration, restarting components if necessary."""
        print("Reloading configuration...")
        was_dictating = self.is_dictating
        if was_dictating:
            self.toggle_dictation() # Stop current dictation cleanly

        # Check which critical settings changed
        old_model = self.model_size
        old_device = self.device
        old_compute = self.compute_type
        old_audio_dev = self.audio_device
        old_inserter = self.text_inserter

        self.config = new_config
        self._load_config() # Update internal variables

        # Check if model needs reloading
        if (self.model_size != old_model or
            self.device != old_device or
            self.compute_type != old_compute):
            print("STT configuration changed, unloading model.")
            self.stt_model = None # Force reload on next use/start

        # Check if text inserter needs re-initialization
        if self.text_inserter != old_inserter or self.text_inserter == 'pynput':
             print(f"Text inserter changed to {self.text_inserter}. Re-initializing.")
             self.pynput_kb = None # Clear old one
             if self.text_inserter == 'pynput':
                 try:
                     self.pynput_kb = PynputController()
                 except Exception as e:
                     print(f"Error re-initializing pynput Controller: {e}.")
                     self.status_queue.put(("error", f"Pynput init failed: {e}"))

        # Check if audio device changed (requires restart if active)
        # Restarting is handled by stopping/starting toggle if was_dictating

        print("Configuration reloaded.")
        self.status_queue.put(("idle", "Config reloaded"))

        # Optional: Immediately try to reload the model if not lazy loading
        # self._load_stt_model()

        # If dictation was active before reload, restart it
        # if was_dictating:
        #     self.toggle_dictation() # Start again with new settings
        # Instead of auto-restarting, let user toggle again. Simpler.

