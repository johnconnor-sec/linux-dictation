import tkinter as tk
from tkinter import ttk, messagebox
import config_manager

class ConfigWindow:
    def __init__(self, parent, config, reload_callback):
        self.config = config
        self.reload_callback = reload_callback # Function to call when saving

        self.window = tk.Toplevel(parent)
        self.window.title("Dictation Settings")
        # self.window.geometry("450x400") # Adjust size as needed

        # Variables to hold settings
        self.vars = {}

        # Create sections (Frames)
        general_frame = ttk.LabelFrame(self.window, text="General", padding="10")
        general_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        whisper_frame = ttk.LabelFrame(self.window, text="Whisper Model", padding="10")
        whisper_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        advanced_frame = ttk.LabelFrame(self.window, text="Advanced", padding="10")
        advanced_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        # --- General Settings ---
        self._add_entry(general_frame, "activation_hotkey", "Activation Hotkey:", 0)
        self._add_entry(general_frame, "language", "Language Code (e.g., en, de, auto):", 1)
        self._add_entry(general_frame, "silence_timeout", "Silence Timeout (s, 0=disable):", 2, type_converter=float)
        self._add_combobox(general_frame, "text_inserter", "Text Input Method:", ["pynput", "ydotool"], 3)

        # --- Whisper Settings ---
        # Consider adding more model options if needed
        models = ["tiny", "tiny.en", "base", "base.en", "small", "small.en", "medium", "medium.en", "large-v3", "distil-large-v2"]
        self._add_combobox(whisper_frame, "model_size", "Model Size:", models, 0, section='Whisper')
        self._add_combobox(whisper_frame, "device", "Device:", ["cpu", "cuda"], 1, section='Whisper')
        # Common compute types - add more if needed
        compute_types = ["default", "int8", "int8_float16", "float16", "float32"]
        self._add_combobox(whisper_frame, "compute_type", "Compute Type:", compute_types, 2, section='Whisper')
        self._add_checkbutton(whisper_frame, "use_vad_filter", "Use VAD Filter (improves silence handling):", 3, section='Whisper')
        self._add_entry(whisper_frame, "beam_size", "Beam Size:", 4, section='Whisper', type_converter=int)
        self._add_entry(whisper_frame, "initial_prompt", "Initial Prompt (optional):", 5, section='Whisper', width=40)

        # --- Advanced Settings ---
        self._add_entry(advanced_frame, "audio_device", "Audio Device (name or index, blank=default):", 0, section='Advanced')
        # self._add_entry(advanced_frame, "sample_rate", "Sample Rate (Hz):", 1, section='Advanced', type_converter=int) # Usually fixed for Whisper
        # self._add_entry(advanced_frame, "block_size", "Audio Block Size (samples):", 2, section='Advanced', type_converter=int) # Usually fixed

        # --- Save/Cancel Buttons ---
        button_frame = ttk.Frame(self.window, padding="10")
        button_frame.grid(row=3, column=0, pady=10)

        save_button = ttk.Button(button_frame, text="Save", command=self.save_settings)
        save_button.pack(side=tk.LEFT, padx=5)
        cancel_button = ttk.Button(button_frame, text="Cancel", command=self.window.destroy)
        cancel_button.pack(side=tk.LEFT, padx=5)

        self.window.columnconfigure(0, weight=1) # Allow frame to expand horizontally

        # Load initial values
        self.load_initial_values()

        # Center window (optional)
        self.window.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.window.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.window.winfo_height() // 2)
        self.window.geometry(f"+{x}+{y}")
        self.window.transient(parent) # Keep on top of parent
        self.window.grab_set() # Modal behavior


    def _add_widget(self, frame, key, label_text, row, section='General'):
        ttk.Label(frame, text=label_text).grid(row=row, column=0, padx=5, pady=2, sticky="w")
        if section not in self.vars:
            self.vars[section] = {}

    def _add_entry(self, frame, key, label_text, row, section='General', type_converter=str, width=25):
        self._add_widget(frame, key, label_text, row, section)
        var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=var, width=width)
        entry.grid(row=row, column=1, padx=5, pady=2, sticky="ew")
        self.vars[section][key] = (var, type_converter)
        frame.columnconfigure(1, weight=1) # Allow entry to expand

    def _add_combobox(self, frame, key, label_text, values, row, section='General', type_converter=str):
        self._add_widget(frame, key, label_text, row, section)
        var = tk.StringVar()
        combo = ttk.Combobox(frame, textvariable=var, values=values, state="readonly")
        combo.grid(row=row, column=1, padx=5, pady=2, sticky="ew")
        self.vars[section][key] = (var, type_converter)
        frame.columnconfigure(1, weight=1)

    def _add_checkbutton(self, frame, key, label_text, row, section='General'):
        self._add_widget(frame, key, label_text, row, section) # Label on left
        var = tk.BooleanVar()
        # Place checkbutton itself in column 1
        chk = ttk.Checkbutton(frame, variable=var, onvalue=True, offvalue=False)
        chk.grid(row=row, column=1, padx=5, pady=2, sticky="w") # Align left in its cell
        self.vars[section][key] = (var, bool)
        frame.columnconfigure(1, weight=1)


    def load_initial_values(self):
        for section, keys in self.vars.items():
            for key, (var, type_converter) in keys.items():
                value = config_manager.get_setting(self.config, section, key, type_converter)
                if isinstance(var, tk.BooleanVar):
                     var.set(bool(value))
                else:
                     var.set(str(value) if value is not None else "")

    def save_settings(self):
        try:
            # Update the config object
            for section, keys in self.vars.items():
                if not self.config.has_section(section):
                    self.config.add_section(section)
                for key, (var, type_converter) in keys.items():
                    value = var.get()
                    # Validate type if possible (especially for numbers)
                    try:
                        if type_converter is int:
                            int(value)
                        elif type_converter is float:
                            float(value)
                    except ValueError:
                         messagebox.showerror("Invalid Input", f"Invalid value for '{key}': '{value}'. Please enter a valid {type_converter.__name__}.")
                         return # Stop saving

                    self.config.set(section, key, str(value))

            # Save to file
            config_manager.save_config(self.config)

            # Notify main app to reload
            if self.reload_callback:
                self.reload_callback(self.config)

            messagebox.showinfo("Settings Saved", "Settings saved successfully. Some changes may require restarting the application or dictation.", parent=self.window)
            self.window.destroy()

        except Exception as e:
            messagebox.showerror("Error Saving", f"Failed to save settings: {e}", parent=self.window)


# Example usage (for testing GUI standalone)
if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw() # Hide main window

    # Dummy callback
    def dummy_reload(config):
        print("Reload callback triggered!")
        # Print saved values
        print("\n--- Saved Config ---")
        for section in config.sections():
            print(f"[{section}]")
            for key, value in config.items(section):
                print(f"{key} = {value}")
        print("--------------------\n")


    cfg = config_manager.load_config()
    config_win = ConfigWindow(root, cfg, dummy_reload)
    root.mainloop()
