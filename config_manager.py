import configparser
import os
from pathlib import Path

DEFAULT_CONFIG = {
    "General": {
        "activation_hotkey": "ctrl+alt+d",
        "language": "en",
        "model_size": "base.en",
        "device": "cpu",
        "compute_type": "default",
        "silence_timeout": "2.0",
        "text_inserter": "pynput",
    },
    "Whisper": {
        "use_vad_filter": "true",
        "beam_size": "5",
        "initial_prompt": "",
    },
    "Advanced": {
        "audio_device": "",
        "sample_rate": "16000",
        "block_size": "8000",  # 0.5 seconds * 16000 Hz
    },
}

CONFIG_FILENAME = "config.ini"


def get_config_path():
    """Gets the path to the configuration file."""
    config_dir = (
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        / "linux-dictation"
    )
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / CONFIG_FILENAME


def load_config():
    """Loads configuration from file, creating defaults if necessary."""
    config_path = get_config_path()
    config = configparser.ConfigParser()
    # Set defaults first
    config.read_dict(DEFAULT_CONFIG)
    # Load existing config, overriding defaults
    if config_path.exists():
        config.read(config_path)
    else:
        # Save defaults if file didn't exist
        save_config(config)
    return config


def save_config(config):
    """Saves the configuration object to the file."""
    config_path = get_config_path()
    with open(config_path, "w") as configfile:
        config.write(configfile)


def get_setting(config, section, key, type_converter=str):
    """Helper to get a setting with type conversion."""
    try:
        return type_converter(config.get(section, key))
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        # Fallback to default if key is missing or conversion fails
        try:
            return type_converter(DEFAULT_CONFIG[section][key])
        except (KeyError, ValueError):
            # Handle case where default is also missing or invalid (shouldn't happen with defined defaults)
            print(f"Warning: Default config missing or invalid for [{section}]{key}")
            return None  # Or raise an error


if __name__ == "__main__":
    # Example usage: Load and print a setting
    cfg = load_config()
    print(f"Activation Hotkey: {get_setting(cfg, 'General', 'activation_hotkey')}")
    print(f"Config file location: {get_config_path()}")
