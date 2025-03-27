import threading
import queue
import time
import sys
import signal
from PIL import Image, ImageDraw # For creating icon images

import pystray
import keyboard

import config_manager
from dictation_service import DictationService
from gui import ConfigWindow
import tkinter as tk # Need root for ConfigWindow


# --- Globals ---
dictation_service = None
tray_icon = None
status_queue = queue.Queue()
root = None # Tk root for GUI window

# --- Status Handling ---
current_status = "offline"
status_icons = {}

def create_icon_image(color):
    """Creates a simple colored circle icon."""
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    dc.ellipse(
        [(size * 0.1, size * 0.1), (size * 0.9, size * 0.9)],
        fill=color,
        outline=(0,0,0,128) # Slight border
    )
    # Optional: Add a letter or symbol
    # font = ImageFont.truetype("sans-serif.ttf", 32)
    # dc.text((size/2, size/2), "D", fill="white", anchor="mm", font=font)
    return image

def setup_status_icons():
    """Generates icons for different states."""
    global status_icons
    status_icons = {
        "offline": create_icon_image('gray'),
        "idle": create_icon_image('blue'),
        "listening": create_icon_image('green'),
        "processing": create_icon_image('orange'),
        "error": create_icon_image('red'),
    }

def update_tray_status(status, message=""):
    """Updates the tray icon and tooltip based on status."""
    global current_status, tray_icon
    current_status = status
    if tray_icon and status in status_icons:
        tray_icon.icon = status_icons[status]
        tooltip = f"Linux Dictation: {message or status.capitalize()}"
        # Limit tooltip length if necessary
        tray_icon.title = tooltip[:63]
    print(f"Status: {status} - {message}")

# --- Tray Icon Callbacks ---
def on_toggle_dictation(icon=None, item=None):
    """Callback to toggle dictation via tray menu or hotkey."""
    if dictation_service:
        dictation_service.toggle_dictation()

def on_configure(icon, item):
    """Callback to open the configuration window."""
    global root, config
    if not root:
        print("Error: Tk root not initialized.")
        return

    # Ensure config is up-to-date before opening window
    config = config_manager.load_config()

    # Define the reload callback function here or pass it from main
    def reload_config_callback(new_config):
        global config
        config = new_config # Update global config reference
        if dictation_service:
            dictation_service.reload_config(new_config)
        # Hotkey might need re-registering if changed
        setup_hotkey(config) # Re-setup hotkey with potentially new binding

    # Check if a window is already open? (Simple check)
    # Tkinter's Toplevel should handle modality via grab_set in gui.py
    try:
        # Make sure root window exists and is updated before creating Toplevel
        root.deiconify() # Make sure it exists even if hidden
        root.update()
        ConfigWindow(root, config, reload_config_callback)
        root.withdraw() # Hide root window again after creating child
    except tk.TclError as e:
         print(f"Tkinter error opening config: {e}")
         if "application has been destroyed" in str(e):
             print("Attempting to re-initialize Tk...")
             setup_tk_root() # Try re-initializing
             if root:
                 try:
                     ConfigWindow(root, config, reload_config_callback)
                     root.withdraw()
                 except Exception as e2:
                     print(f"Failed to open config window after re-init: {e2}")
             else:
                  print("Failed to re-initialize Tk.")

def on_quit(icon, item):
    """Callback to clean up and exit the application."""
    print("Quit requested.")
    if tray_icon:
        tray_icon.stop()
    # Cleanup will be handled in main after tray_icon.run() finishes

# --- Hotkey Handling ---
hotkey_listener_thread = None
stop_hotkey_listener = threading.Event()
registered_hotkey = None

def hotkey_worker(activation_key):
    """Listens for the global hotkey."""
    global registered_hotkey
    try:
        print(f"Registering hotkey: {activation_key}")
        # Unregister previous hotkey if any
        if registered_hotkey:
            try:
                 keyboard.remove_hotkey(registered_hotkey)
                 print(f"Unregistered previous hotkey.")
            except Exception as e:
                 print(f"Warning: Could not unregister previous hotkey: {e}")
            registered_hotkey = None

        # Use keyboard.add_hotkey
        # The trigger_on_release=True helps prevent accidental double-triggering
        # and ensures the hotkey isn't active while keys are held for typing.
        registered_hotkey = keyboard.add_hotkey(
            activation_key,
            on_toggle_dictation,
            trigger_on_release=True
        )
        print(f"Hotkey '{activation_key}' registered successfully.")
        update_tray_status(current_status, f"Ready (Hotkey: {activation_key})")

        # Keep the thread alive while listening - keyboard library handles this internally
        # Wait for the stop event
        stop_hotkey_listener.wait()
        print("Hotkey listener stopping.")

    except (ImportError, OSError, ValueError) as e:
         print(f"\n*** Error setting up global hotkey '{activation_key}' ***")
         print(f"    Error: {e}")
         print(f"    The 'keyboard' library might require root privileges")
         print(f"    or your user to be in the 'input' group on Linux (especially Wayland).")
         print(f"    Try running with 'sudo python main.py' OR")
         print(f"    'sudo usermod -a -G input $USER' (logout/login required).")
         update_tray_status("error", f"Hotkey failed: {e}")
    except Exception as e:
         print(f"Unexpected error in hotkey listener: {e}")
         update_tray_status("error", f"Hotkey unexpected error: {e}")
    finally:
         # Cleanup hotkey registration when thread stops
         if registered_hotkey:
             try:
                 keyboard.remove_hotkey(registered_hotkey)
                 print("Hotkey unregistered on exit.")
             except Exception as e:
                 print(f"Warning: Could not unregister hotkey on exit: {e}")

def setup_hotkey(config):
    """Sets up or updates the global hotkey listener thread."""
    global hotkey_listener_thread, stop_hotkey_listener, registered_hotkey

    activation_key = config_manager.get_setting(config, 'General', 'activation_hotkey')

    if hotkey_listener_thread and hotkey_listener_thread.is_alive():
        print("Stopping existing hotkey listener...")
        stop_hotkey_listener.set()
        hotkey_listener_thread.join(timeout=1.0)
        if hotkey_listener_thread.is_alive():
             print("Warning: Hotkey listener thread did not stop gracefully.")
        # Clear previous registration just in case remove_hotkey in worker failed
        if registered_hotkey:
             try: keyboard.remove_hotkey(registered_hotkey)
             except: pass
             registered_hotkey = None


    stop_hotkey_listener.clear()
    hotkey_listener_thread = threading.Thread(
        target=hotkey_worker,
        args=(activation_key,),
        daemon=True # Allows program exit even if this thread is blocked (though it shouldn't be)
    )
    hotkey_listener_thread.start()

# --- Status Queue Processing ---
def process_status_queue():
    """Checks the status queue and updates the UI."""
    while not status_queue.empty():
        try:
            status, message = status_queue.get_nowait()
            update_tray_status(status, message)
        except queue.Empty:
            break
        except Exception as e:
            print(f"Error processing status queue: {e}")

    # Schedule next check if tray icon is running
    if tray_icon and tray_icon.HAS_NOTIFICATION: # Check if tray backend supports notifications/updates
        # Schedule using Tkinter's after() method since tray runs in main thread with it
        if root:
             root.after(200, process_status_queue) # Check every 200ms

# --- Main Application Logic ---
def setup_tk_root():
    """Initializes or re-initializes the hidden Tk root window."""
    global root
    try:
        if root: # If exists, try destroying first
            root.destroy()
    except tk.TclError: # May already be destroyed
        pass
    try:
        root = tk.Tk()
        root.withdraw() # Hide the main window
        print("Tk root initialized.")
    except Exception as e:
        print(f"Failed to initialize Tkinter: {e}")
        root = None


def main():
    global dictation_service, tray_icon, config, root

    print("Starting Linux Dictation...")

    # Handle termination signals gracefully
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Load configuration
    config = config_manager.load_config()

    # Initialize hidden Tk root for GUI dialogs
    setup_tk_root()
    if not root:
        print("Error: Could not initialize Tkinter. Configuration window will not work.")
        # Optionally exit or continue without GUI config

    # Setup status icons
    setup_status_icons()

    # Initialize Dictation Service
    dictation_service = DictationService(config)
    # Pass its queue for status updates
    dictation_service.status_queue = status_queue
    dictation_service.start() # Start background threads (like text insertion)

    # Setup Hotkey Listener
    setup_hotkey(config)

    # Create System Tray Icon
    menu = pystray.Menu(
        pystray.MenuItem('Toggle Dictation', on_toggle_dictation, default=True, visible=False), # Double-click action
        pystray.MenuItem('Toggle Dictation', on_toggle_dictation),
        pystray.MenuItem('Configure', on_configure),
        pystray.MenuItem('Quit', on_quit)
    )

    # Initial icon and status
    initial_status = "idle"
    initial_message = "Ready"
    if not hotkey_listener_thread or not hotkey_listener_thread.is_alive():
         initial_status = "error"
         initial_message = "Hotkey setup failed (check logs)"

    update_tray_status(initial_status, initial_message) # Set initial icon before showing

    try:
        tray_icon = pystray.Icon("linux_dictation", status_icons[initial_status], "Linux Dictation", menu)

        # Start status queue processing loop via Tkinter's mainloop
        if root:
            root.after(100, process_status_queue) # Start checking queue

        print("Running tray icon. Use hotkey or tray menu.")
        # pystray's run() method blocks until stop() is called
        # It often integrates with underlying GUI toolkits (like Tkinter if available)
        tray_icon.run()

    except Exception as e:
        print(f"Error running tray icon: {e}")
        print("Check if required packages for pystray backends are installed (e.g., python3-gi, python3-tk).")

    finally:
        # --- Cleanup ---
        print("Cleaning up...")

        # Stop hotkey listener thread
        if hotkey_listener_thread and hotkey_listener_thread.is_alive():
            print("Stopping hotkey listener...")
            stop_hotkey_listener.set()
            hotkey_listener_thread.join(timeout=1.0)

        # Stop dictation service
        if dictation_service:
            print("Stopping dictation service...")
            dictation_service.stop()

        # Destroy Tkinter root window if it exists
        if root:
            try:
                root.quit() # Exit Tkinter mainloop if somehow still running
                root.destroy()
                print("Tk root destroyed.")
            except tk.TclError:
                pass # Already destroyed

        print("Linux Dictation finished.")
        sys.exit(0)


def signal_handler(sig, frame):
    """Handle Ctrl+C or termination signals."""
    print(f"Signal {sig} received, initiating shutdown...")
    if tray_icon:
        tray_icon.stop()
    # The rest of the cleanup happens in the finally block of main()

if __name__ == "__main__":
    main()
