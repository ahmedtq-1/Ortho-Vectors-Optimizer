import sys
import tkinter as tk
from tkinter import messagebox

# IMMUTABLE SYSTEM BOOT HOOK: Catches basic structural load anomalies instantly on startup
try:
    import subprocess
    import os
    import bz2
    import math
    import time
    import threading
    import gc
    import shutil
    import json
    import multiprocessing
    import webbrowser
    import urllib.request
    import io
    import re
    import queue
    import string
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    import xml.etree.ElementTree as ET
    from tkinter import filedialog, ttk
    from tkinter import scrolledtext
    if sys.platform == "win32":
        try:
            import winreg
        except ImportError:
            winreg = None
    else:
        winreg = None
except Exception as boot_err:
    import traceback
    root_boot = tk.Tk()
    root_boot.withdraw()
    messagebox.showerror("Fatal Startup Error", f"A critical error occurred during application startup:\n\n{traceback.format_exc()}")
    sys.exit(1)

error_queue = queue.Queue()

def main_exception_hook(exc_type, exc_value, exc_traceback):
    """Hook for catching unhandled exceptions in the main thread."""
    import traceback
    err_det = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    error_title = "Unhandled Application Error"
    error_message = f"A critical error occurred:\n\n{err_det}"

    # If the main GUI is running, use the queue to display the error non-blockingly.
    try:
        # Use 'root' in globals() to avoid NameError on very early startup crashes
        if 'root' in globals() and root and root.winfo_exists():
            error_queue.put((error_title, error_message))
            return # Let the GUI handle it
    except (NameError, tk.TclError):
        pass # root doesn't exist or is destroyed, so fallback to blocking messagebox.

    # Fallback for errors during startup before the mainloop is active. This will block.
    try:
        root_err = tk.Tk()
        root_err.withdraw()
        messagebox.showerror(error_title, error_message)
        root_err.destroy()
    except Exception:
        print(f"--- CRITICAL UNHANDLED EXCEPTION ---\n{err_det}", file=sys.stderr)
    sys.exit(1)

def thread_exception_hook(args):
    """Hook for catching unhandled exceptions in background threads."""
    import traceback
    # args is a threading.ExceptHookArgs object with exc_type, exc_value, exc_traceback
    err_det = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    error_title = "Unhandled Thread Error"
    error_message = f"An error occurred in a background task:\n\n{err_det}"
    # Always use the queue for thread errors to avoid crashing the GUI.
    error_queue.put((error_title, error_message))

def check_error_queue():
    """Periodically check the error queue for messages from other threads."""
    try:
        while True:
            title, message = error_queue.get_nowait()
            messagebox.showerror(title, message)
    except queue.Empty:
        pass
    finally:
        # Reschedule the check
        if 'root' in globals() and root.winfo_exists():
            root.after(250, check_error_queue)

sys.excepthook = main_exception_hook
threading.excepthook = thread_exception_hook

def find_tool_in_dir(directory, tool_prefix):
    """Finds a tool, checking PATH first, then a specific directory. Validates file size."""
    def is_valid_executable(path):
        """Checks if a path exists, is a file, and has a reasonable size."""
        if not path or not os.path.isfile(path):
            return False
        # OSM tools are typically > 100KB. A 10KB check is a safe minimum to filter out 1KB error files.
        return os.path.getsize(path) > 10000

    # First, check the system PATH, which is common for Linux/macOS installs.
    # This is the most reliable way to find tools installed via package managers.
    system_path_tool = shutil.which(tool_prefix)
    if is_valid_executable(system_path_tool):
        return system_path_tool

    # If not in PATH, check the user-specified directory.
    if not os.path.isdir(directory):
        # If dir doesn't exist, return an ideal path for the os.path.exists() check to fail.
        if sys.platform == "win32":
            return os.path.join(directory, f"{tool_prefix}64.exe")
        else:
            return os.path.join(directory, tool_prefix)

    if sys.platform == "win32":
        # Windows: Look for .exe files in the specified directory.
        # Explicitly prefer the 64-bit version.
        path64 = os.path.join(directory, f"{tool_prefix}64.exe")
        if is_valid_executable(path64):
            return path64

        # Fallback to the 32-bit name for old manual installs.
        path32 = os.path.join(directory, f"{tool_prefix}.exe")
        if is_valid_executable(path32):
            return path32

        # Generic fallback for other names (e.g., osmconvert-0.8.exe).
        try:
            for filename in sorted(os.listdir(directory), reverse=True):
                if filename.lower().startswith(tool_prefix) and filename.lower().endswith(".exe"):
                    candidate_path = os.path.join(directory, filename)
                    if is_valid_executable(candidate_path):
                        return candidate_path
        except OSError:
            pass
        
        # If nothing found in the directory, return the ideal path for the check to fail.
        return os.path.join(directory, f"{tool_prefix}64.exe")
    else:
        # Linux/macOS: Look for an executable file without an extension.
        path = os.path.join(directory, tool_prefix)
        if is_valid_executable(path) and os.access(path, os.X_OK):
            return path

        # Generic fallback for other names (e.g., osmconvert-0.8p)
        try:
            for filename in sorted(os.listdir(directory), reverse=True):
                if filename.lower().startswith(tool_prefix):
                    candidate_path = os.path.join(directory, filename)
                    if is_valid_executable(candidate_path) and os.access(candidate_path, os.X_OK):
                        return candidate_path
        except OSError:
            pass

        # If nothing found, return the ideal path for the check to fail.
        return os.path.join(directory, tool_prefix)

OSMCONVERT_GITHUB_URL = "https://raw.githubusercontent.com/ahmedtq-1/Ortho-Vectors-Optimizer/main/osmconvert.exe"
OSMFILTER_GITHUB_URL = "https://raw.githubusercontent.com/ahmedtq-1/Ortho-Vectors-Optimizer/main/osmfilter.exe"

def check_and_install_dependencies():
    """Checks for all dependencies (Python and external tools) and prompts for installation if needed."""
    missing_items = {}

    # Define startupinfo here to be available for the helper functions below.
    startupinfo_no_window = None
    if sys.platform == 'win32':
        startupinfo_no_window = subprocess.STARTUPINFO()
        startupinfo_no_window.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    
    # Helper to check if a Python package is installed using pip show
    def is_python_package_installed(package_name):
        try:
            # Use sys.executable to ensure we query the pip for the current Python interpreter
            result = subprocess.run([sys.executable, "-m", "pip", "show", package_name],
                                    capture_output=True, text=True, check=False,
                                    startupinfo=startupinfo_no_window)
            # pip show returns 0 if package is found, non-zero otherwise
            return result.returncode == 0
        except Exception:
            return False

    # 1. Check for Python dependencies using pip show
    if not is_python_package_installed('Pillow'):
        missing_items['pillow'] = 'Python library for image processing'

    # 2. Check for external tools
    util_dir = util_path_var.get().strip()
    if not os.path.exists(find_tool_in_dir(util_dir, "osmconvert")):
        missing_items['osmconvert'] = 'OSM data conversion tool'
    if not os.path.exists(find_tool_in_dir(util_dir, "osmfilter")):
        missing_items['osmfilter'] = 'OSM data filtering tool'

    
    if not missing_items: # If no missing items, then we can proceed to import and set up PIL
        # Only import if not missing, to avoid ImportError if it's truly not there
        try:
            from PIL import Image
            if not hasattr(Image, 'LANCZOS'):
                try: Image.LANCZOS = Image.Resampling.LANCZOS
                except AttributeError: Image.LANCZOS = Image.ANTIALIAS
            return # All good, exit the check.
        except ImportError:
            # This should ideally not happen if is_python_package_installed('Pillow') was true,
            # but as a final safeguard, if import still fails, we treat it as missing.
            missing_items['pillow'] = 'Python library for image processing (import failed after check)'

    
    msg = "This application requires some additional components to function correctly. The following are missing:\n\n"
    for item, desc in missing_items.items():
        msg += f" • {item} ({desc})\n"

    if sys.platform == "win32":
        install_method_desc = "(This will use 'pip' for Python libraries and direct download for other tools)."
    elif sys.platform.startswith("linux"):
        install_method_desc = "(This will use 'pip' for Python libraries and attempt installation via 'apt-get' or source compilation for other tools, which may require a password)."
    else: # macOS and others
        install_method_desc = "(This will use 'pip' for Python libraries. Other tools may need manual installation.)"

    msg += f"\nWould you like to attempt to download and install them automatically?\n\n{install_method_desc}"
    
    if not messagebox.askyesno("Missing Dependencies", msg):
        messagebox.showerror("Aborted", "Cannot continue without required dependencies. The application will now exit.")
        sys.exit(1)

    
    progress_win = tk.Toplevel(root); progress_win.title("Installing Dependencies"); progress_win.geometry("450x150"); progress_win.resizable(False, False); progress_win.transient(root); progress_win.grab_set()
    ttk.Label(progress_win, text="Please wait while dependencies are installed...", font=("Arial", 10, "bold")).pack(pady=10)
    status_var_progress = tk.StringVar(value="Initializing..."); ttk.Label(progress_win, textvariable=status_var_progress).pack(pady=5, padx=10)
    progress_bar_install = ttk.Progressbar(progress_win, length=400, mode='determinate', maximum=len(missing_items)); progress_bar_install.pack(pady=10)
    root.update()

    
    installed_count = 0; errors = []
    def update_progress(status_text):
        nonlocal installed_count; installed_count += 1; status_var_progress.set(status_text); progress_bar_install['value'] = installed_count; root.update()
    
    def _download_file(url, dest_path, item_name):
        """Tries to download a file using multiple methods. Returns True on success, False on failure."""
        
        def _cleanup():
            if os.path.exists(dest_path):
                try: os.remove(dest_path)
                except OSError: pass
        
        _cleanup() # Clean up any previous attempts for this path

        # --- Attempt 1: Use curl (often most reliable, built into modern Windows) ---
        if shutil.which("curl"):
            status_var_progress.set(f"Downloading {item_name} (Attempt 1/3: curl)..."); root.update()
            try:
                subprocess.run(["curl", "-L", "--insecure", "-o", dest_path, "-sS", url],
                               check=True, startupinfo=startupinfo_no_window, timeout=90)
                if os.path.exists(dest_path): # Success is just existence, size check is done by caller
                    return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"curl failed for {item_name}: {e}")
                _cleanup()

        # --- Attempt 2: Use PowerShell (good fallback on Windows) ---
        if sys.platform == 'win32' and shutil.which("powershell"):
            status_var_progress.set(f"Downloading {item_name} (Attempt 2/3: PowerShell)..."); root.update()
            ps_command = (
                f"[System.Net.ServicePointManager]::SecurityProtocol = 3072; "
                f"[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {{$true}}; "
                f"Invoke-WebRequest -Uri \"{url}\" -OutFile \"{dest_path}\""
            )
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_command],
                               check=True, capture_output=True, text=True, startupinfo=startupinfo_no_window, timeout=90)
                if os.path.exists(dest_path):
                    return True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
                print(f"PowerShell failed for {item_name}: {e}")
                _cleanup()

        # --- Attempt 3: Use Python's native urllib (universal fallback) ---
        status_var_progress.set(f"Downloading {item_name} (Attempt 3/3: Python native)..."); root.update()
        try:
            import ssl
            context = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers={"User-Agent": "Ortho-Optimizer-Downloader/1.0"})
            with urllib.request.urlopen(req, context=context, timeout=90) as response, open(dest_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            if os.path.exists(dest_path):
                return True
        except Exception as e:
            print(f"Python native download failed for {item_name}: {e}")
            _cleanup()
            return False

        _cleanup()
        return False

    if 'pillow' in missing_items:
        status_var_progress.set("Installing 'Pillow' via pip..."); root.update()
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--user", "pillow"],
                           check=True, capture_output=True, text=True, startupinfo=startupinfo_no_window)
            update_progress("✓ 'Pillow' installed successfully.")
        except subprocess.CalledProcessError as e:
            errors.append(f"Failed to install Pillow: {e.stderr.strip()}")
        except Exception as e:
            errors.append(f"Failed to install Pillow: {e}")
    
    if 'osmconvert' in missing_items or 'osmfilter' in missing_items:
        target_dir = util_path_var.get().strip()
        if not target_dir or not os.path.isdir(target_dir):
            target_dir = _get_app_data_dir("OSM_Tools"); util_path_var.set(target_dir)
            status_var_progress.set(f"OSM Tools folder set to: {target_dir}"); root.update(); time.sleep(1)
        
        os.makedirs(target_dir, exist_ok=True) # Ensure target directory exists

        if sys.platform == "win32":
            if 'osmconvert' in missing_items:
                status_var_progress.set("Downloading osmconvert..."); root.update()
                dest_path = os.path.join(target_dir, 'osmconvert.exe')
                
                if _download_file(OSMCONVERT_GITHUB_URL, dest_path, "osmconvert.exe") and os.path.getsize(dest_path) > 10000:
                    update_progress("✓ osmconvert downloaded from GitHub.")
                else:
                    errors.append("Failed to download 'osmconvert' from GitHub. Please download it manually.")
            
            if 'osmfilter' in missing_items:
                status_var_progress.set("Downloading osmfilter..."); root.update()
                dest_path = os.path.join(target_dir, 'osmfilter.exe')

                if _download_file(OSMFILTER_GITHUB_URL, dest_path, "osmfilter.exe") and os.path.getsize(dest_path) > 10000:
                    update_progress("✓ osmfilter downloaded from GitHub.")
                else:
                    errors.append("Failed to download 'osmfilter' from GitHub. Please download it manually.")
        elif sys.platform.startswith("linux"):
            # On Linux, we first try the package manager, then fall back to compiling from source.
            if 'osmconvert' in missing_items or 'osmfilter' in missing_items:
                
                # --- Attempt 1: Use package manager (apt-get for Debian/Ubuntu) ---
                if shutil.which("apt-get"):
                    status_var_progress.set("Attempting to install 'osmctools' via apt..."); root.update()
                    try:
                        # Use pkexec for a graphical sudo prompt. Do not capture output.
                        subprocess.run(["pkexec", "apt-get", "update"], check=True, timeout=300)
                        subprocess.run(["pkexec", "apt-get", "install", "-y", "osmctools"], check=True, timeout=600)
                        
                        # Verify if the tools are now available in the system PATH
                        if shutil.which("osmconvert") and 'osmconvert' in missing_items:
                            update_progress("✓ 'osmconvert' installed via apt.")
                            missing_items.pop('osmconvert')
                        if shutil.which("osmfilter") and 'osmfilter' in missing_items:
                            update_progress("✓ 'osmfilter' installed via apt.")
                            missing_items.pop('osmfilter')
                        
                    except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as e:
                        print(f"apt-get install via pkexec failed: {e}. Falling back to source compilation for osmconvert.")
                        # Fall through to the compilation method.

                # --- Attempt 2: Compile osmconvert from source (if still missing) ---
                if 'osmconvert' in missing_items:
                    status_var_progress.set("Compiling 'osmconvert' from source..."); root.update()
                    compiler = shutil.which("cc") or shutil.which("gcc")
                    
                    if compiler:
                        try:
                            source_url = "https://m.m.i24.cc/osmconvert.c"
                            req = urllib.request.Request(source_url, headers={"User-Agent": "Ortho-Optimizer-Downloader/1.0"})
                            with urllib.request.urlopen(req, timeout=60) as response:
                                source_code_bytes = response.read()

                            output_path = os.path.join(target_dir, "osmconvert")

                            compile_cmd = [compiler, "-x", "c", "-", "-lz", "-O3", "-o", output_path]
                            proc = subprocess.run(compile_cmd, input=source_code_bytes, capture_output=True, check=True, timeout=120)
                            os.chmod(output_path, 0o755)

                            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                                update_progress("✓ 'osmconvert' compiled from source.")
                                missing_items.pop('osmconvert')
                            else:
                                raise Exception("Compiler ran but output file is missing or empty.")

                        except Exception as e:
                            err_details = e.stderr.decode(errors='ignore') if isinstance(e, subprocess.CalledProcessError) else ""
                            compile_error_msg = (f"Failed to compile 'osmconvert' from source.\nError: {e}\n{err_details}\n\n"
                                                 "This may be due to a missing 'zlib' development library (e.g., 'sudo apt-get install zlib1g-dev'). "
                                                 "Please install 'osmctools' using your package manager.")
                            errors.append(compile_error_msg)
                    else:
                        errors.append("Cannot compile 'osmconvert': 'gcc' or 'cc' not found in PATH.")

                # --- Final error reporting for anything still missing ---
                if 'osmfilter' in missing_items:
                    errors.append("Could not auto-install 'osmfilter'. Please install 'osmctools' using your package manager (e.g., apt, dnf, pacman).")
        else: # macOS, etc.
            errors.append("Automatic installation of osmconvert/osmfilter is not supported on Windows and Debian-based Linux. On macOS, please use Homebrew: 'brew install osmctools'")
    
    progress_win.destroy()
    if errors:
        error_summary = "Some dependencies could not be installed automatically:\n\n" + "\n".join(f"• {e}" for e in errors)
        error_summary += "\n\nPlease try installing them manually. The application will now exit."
        messagebox.showerror("Installation Failed", error_summary); sys.exit(1)
    else:
        # This block is reached only if dependencies were missing and were installed without error.
        # We must relaunch the application for the new modules to be imported correctly.
        messagebox.showinfo("Relaunch Required", "Dependencies installed successfully.\nThe application will now relaunch to apply the changes.")
        try:
            # Clean up the GUI before relaunching to avoid zombie windows
            root.destroy()
        except tk.TclError:
            pass # Window might already be gone
        # Relaunch the application. This replaces the current process.
        os.execv(sys.executable, [sys.executable] + sys.argv)

PRESETS = {
    "Full World Scan": {"lat_s": -85, "lat_n": 85, "lon_w": -180, "lon_e": 180, "file": ""},
    "AFRICA": {"lat_s": -35, "lat_n": 38, "lon_w": -18, "lon_e": 52, "file": "africa-latest.osm.pbf"},
    "ASIA & MALDIVES": {"lat_s": -12, "lat_n": 60, "lon_w": 26, "lon_e": 150, "file": "asia-latest.osm.pbf"},
    "EUROPE": {"lat_s": 34, "lat_n": 82, "lon_w": -32, "lon_e": 180, "file": "europe-latest.osm.pbf"},
    "NORTH AMERICA": {"lat_s": 14, "lat_n": 84, "lon_w": -170, "lon_e": -10, "file": "north-america-latest.osm.pbf"},
    "AUSTRALIA & NZ": {"lat_s": -55, "lat_n": -10, "lon_w": 110, "lon_e": 180, "file": "australia-oceania-latest.osm.pbf"},
    "SOUTH AMERICA": {"lat_s": -56, "lat_n": 13, "lon_w": -82, "lon_e": -34, "file": "south-america-latest.osm.pbf"},
    "CENTRAL AMERICA": {"lat_s": 7, "lat_n": 28, "lon_w": -93, "lon_e": -59, "file": "central-america-latest.osm.pbf"},
    "HAWAII & MICRONESIA": {"lat_s": -10, "lat_n": 30, "lon_w": 130, "lon_e": 180, "file": "australia-oceania-latest.osm.pbf"},
    "CUSTOM RANGE (MANUAL)": {"lat_s": "", "lat_n": "", "lon_w": "", "lon_e": "", "file": ""}
}

active_subprocesses = []
pool_executor = None
unique_pid = "master_cache" 
session_file_path = ""
master_region_path = ""
is_paused = False
resume_list = []
_is_loading_prefs = False
completed_lock = threading.Lock()
subprocess_lock = threading.Lock()

all_tiles_to_process_global = []
ortho_tiles_to_process_global = []

# === MAP SELECTOR STATE ===============================================
OSM_TILE_URL_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_TILE_USER_AGENT = "Ortho4XP-Vectors-Optimizer/1.3 (personal desktop utility)"
OSM_PRECACHE_ZOOM_MIN = 0
OSM_PRECACHE_ZOOM_MAX = 5
OSM_MIN_ZOOM = 0
OSM_MAP_MAX_ZOOM = 5
TILE_PIXELS = 256
OSM_TILE_DOWNLOAD_DELAY = 0.12

map_window_ref = {"win": None, "canvas": None}
map_view_state = {"lon_min": -180.0, "lon_max": 180.0, "lat_min": -85.0, "lat_max": 85.0}
map_selection_bounds = None
map_individual_selection = set()
map_temp_rect_id = None
map_drag_start = {"lon": None, "lat": None}
map_pan_start = {"x": None, "y": None, "last_x": None, "last_y": None, "view": None}
map_refresh_job = None
map_bg_photo_ref = {"photo": None, "for_view": None}
map_bg_request_id = {"id": 0}
_tile_memory_cache = {}
_tile_memory_cache_lock = threading.Lock()
xp_scenery_tiles = set()
xp_scenery_scan_dirs = []
xp_scenery_scan_lock = threading.Lock()
discovered_osm_tiles = set()
discovered_osm_lock = threading.Lock()
discovered_ortho_tiles = {}
discovered_ortho_lock = threading.Lock()

# === ORTHO4XP INTEGRATION STATE ========================================
ORTHO4XP_ZL_CHOICES = [str(z) for z in range(12, 20)]
ORTHO4XP_DEM_CHOICES = ["Default (Viewfinderpanoramas.org)", "USGS 1/3 arc-second", "SRTM / OpenTopography", "Copernicus GLO-30 (OpenTopography)", "Custom DEM File..."]
ortho4xp_is_paused = False
ortho4xp_stop_requested = False
ortho4xp_resume_list = []
ortho4xp_active_proc = {"proc": None}
ortho_log_text = None

ORTHO4XP_DEM_MAP = {
    "Default (Viewfinderpanoramas.org)": "Viewfinderpanoramas (J. de Ferranti) - mostly worldwide",
    "USGS 1/3 arc-second": "USGS 1/3 arc-second",
    "SRTM / OpenTopography": "SRTMGL1",
    "Copernicus GLO-30 (OpenTopography)": "COP30",
}


def _session_search_dirs():
    dirs = []
    try:
        u = util_path_var.get().strip()
        if u: dirs.append(u)
    except NameError:
        pass
    for p in (r"C:\Ortho_OSM", r"E:\Ortho4XP"):
        if p not in dirs:
            dirs.append(p)
    return dirs


def _get_app_data_dir(subfolder=None):
    if subfolder == "Temp":
        app_temp_dir = os.path.join(tempfile.gettempdir(), "Ortho_Optimizer_Temp")
        try:
            os.makedirs(app_temp_dir, exist_ok=True)
            return app_temp_dir
        except OSError as e:
            error_queue.put(("Fatal Temp Folder Error", f"Could not create or access the application temp directory: {app_temp_dir}\nError: {e}"))
            raise

    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    app_dir = os.path.join(base, "Ortho4XP_Optimizer")
    if subfolder:
        app_dir = os.path.join(app_dir, subfolder)

    try:
        os.makedirs(app_dir, exist_ok=True)
    except OSError:
        app_dir = os.path.join(tempfile.gettempdir(), "Ortho4XP_Optimizer")
        if subfolder:
            app_dir = os.path.join(app_dir, subfolder)
        os.makedirs(app_dir, exist_ok=True)
    return app_dir

def get_app_state_path():
    return os.path.join(_get_app_data_dir(), "osm_last_paths.json")

def get_global_scenery_path(xplane_version):
    steam_path_x86 = os.path.expandvars(rf"%ProgramFiles(x86)%\Steam\steamapps\common\X-Plane {xplane_version}")
    steam_path_x64 = os.path.expandvars(rf"%ProgramFiles%\Steam\steamapps\common\X-Plane {xplane_version}")
    direct_paths = [f"{letter}:\\X-Plane {xplane_version}" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]

    for base_path in [steam_path_x86, steam_path_x64] + direct_paths:
        if base_path and os.path.isdir(base_path):
            global_scenery_path = os.path.join(base_path, "Global Scenery", f"X-Plane {xplane_version} Global Scenery")
            if os.path.isdir(global_scenery_path):
                return global_scenery_path
    return None

def find_xplane_root_path():
    """Finds the root X-Plane directory by locating the global scenery and moving up."""
    for ver in ("12", "11"):
        global_scenery = get_global_scenery_path(ver)
        if global_scenery and os.path.isdir(global_scenery):
            # Path is .../X-Plane {ver}/Global Scenery/X-Plane {ver} Global Scenery
            # We want .../X-Plane {ver}
            return os.path.abspath(os.path.join(global_scenery, "..", ".."))
    return None

def find_ortho4xp_dynamically():
    search_bases = [os.path.expanduser("~"), os.path.join(os.path.expanduser("~"), "Desktop")]
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            search_bases.append(drive)

    ortho_dir_names = ["Ortho4XP", "Ortho4XP_v130", "Ortho4XP_v120", "Ortho4XP-v1.3.0"]

    for base in search_bases:
        for dirname in ortho_dir_names:
            candidate_dir = os.path.join(base, dirname)
            exe_path = os.path.join(candidate_dir, "Ortho4XP.exe")
            if os.path.exists(exe_path):
                return exe_path
    return None

def save_last_paths_checkpoint():
    if _is_loading_prefs:
        return
    try:
        def safe_get(widget_or_var):
            try: return widget_or_var.get().strip()
            except: return ""
        def safe_get_bool(var):
            try: return var.get()
            except: return False

        payload = {
            "util_path": safe_get(util_path_var), "file_path": safe_get(file_path_var), "dest_path": safe_get(dest_path_var),
            "mode_selection": safe_get(mode_combo), "preset_selection": safe_get(preset_combo),
            "lat_s": safe_get(lat_s_entry), "lat_n": safe_get(lat_n_entry), "lon_w": safe_get(lon_w_entry), "lon_e": safe_get(lon_e_entry),
            "ortho4xp_exe": safe_get(ortho4xp_exe_var), "ortho4xp_output": safe_get(ortho4xp_output_var),
            "ortho4xp_imagery": safe_get(ortho_imagery_var), "ortho4xp_zl": safe_get(ortho_zl_var), "ortho4xp_dem_choice": safe_get(ortho_dem_choice_var), "ortho4xp_dem_path": safe_get(ortho_dem_custom_path_var),
            "auto_run_ortho_after_step1": safe_get_bool(auto_run_ortho_var),
            "ortho4xp_overlay": safe_get(ortho4xp_overlay_var),
            "ot_api_key": safe_get(ot_api_key_var),
        }
        app_path = get_app_state_path()
        with open(app_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except (IOError, OSError): pass
    except Exception: pass

def is_windows_dark_mode():
    if not winreg:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except Exception:
        return False

def load_startup_preferences():
    global _is_loading_prefs
    all_candidates = []

    app_data_path = get_app_state_path()
    if os.path.exists(app_data_path) and os.path.getsize(app_data_path) > 10:
        try: all_candidates.append((os.path.getmtime(app_data_path), app_data_path))
        except Exception: pass

    std_session_path = os.path.join(_get_app_data_dir("Temp"), "osm_session.json")
    if os.path.exists(std_session_path) and os.path.getsize(std_session_path) > 10:
        try: all_candidates.append((os.path.getmtime(std_session_path), std_session_path))
        except Exception: pass

    for base in _session_search_dirs():
        p_last = os.path.join(base, "Temp", "osm_last_paths.json")
        if os.path.exists(p_last) and os.path.getsize(p_last) > 10:
            try: all_candidates.append((os.path.getmtime(p_last), p_last))
            except Exception: pass
        p_session = os.path.join(base, "Temp", "osm_session.json")
        if os.path.exists(p_session) and os.path.getsize(p_session) > 10:
            try: all_candidates.append((os.path.getmtime(p_session), p_session))
            except Exception: pass
    if not all_candidates:
        return None

    all_candidates.sort(reverse=True)
    chosen = all_candidates[0][1]
    _is_loading_prefs = True
    try:
        try:
            with open(chosen, "r", encoding="utf-8") as sf:
                state = json.load(sf)
        except Exception:
            return None

        if state.get("util_path"): util_path_var.set(state["util_path"])
        if state.get("file_path"): file_path_var.set(state["file_path"])
        if state.get("dest_path"): dest_path_var.set(state["dest_path"])
        
        if state.get("ortho4xp_exe"): ortho4xp_exe_var.set(state["ortho4xp_exe"])
        if state.get("ortho4xp_output"): ortho4xp_output_var.set(state["ortho4xp_output"])
        if state.get("ortho4xp_imagery"): ortho_imagery_var.set(state["ortho4xp_imagery"])
        if state.get("ortho4xp_zl"): ortho_zl_var.set(state["ortho4xp_zl"])
        if state.get("ortho4xp_dem_choice"): ortho_dem_choice_var.set(state["ortho4xp_dem_choice"])
        if state.get("ortho4xp_dem_path"): ortho_dem_custom_path_var.set(state["ortho4xp_dem_path"])
        if state.get("ot_api_key"): ot_api_key_var.set(state["ot_api_key"])
        if state.get("ortho4xp_overlay"):
            overlay_path = state["ortho4xp_overlay"]
            ortho4xp_overlay_var.set(overlay_path)
            check_and_warn_default_overlay_path(overlay_path)
        if "auto_run_ortho_after_step1" in state: auto_run_ortho_var.set(bool(state["auto_run_ortho_after_step1"]))

        if state.get("mode_selection"):
            mode_combo.set(state["mode_selection"])
        toggle_mode_widgets(None)

        selected_preset = state.get("preset_selection", "CUSTOM RANGE (MANUAL)")
        preset_combo.set(selected_preset)

        preset_data = PRESETS.get(selected_preset, {})
        if preset_data.get("file"):
            file_path_var.set(os.path.join(util_path_var.get(), preset_data["file"]))

        for widget in (lat_s_entry, lat_n_entry, lon_w_entry, lon_e_entry):
            widget.config(state='normal')
            widget.delete(0, tk.END)

        if selected_preset != "CUSTOM RANGE (MANUAL)":
            data = PRESETS.get(selected_preset, PRESETS["CUSTOM RANGE (MANUAL)"])
            lat_s_entry.insert(0, str(data["lat_s"]))
            lat_n_entry.insert(0, str(data["lat_n"]))
            lon_w_entry.insert(0, str(data["lon_w"]))
            lon_e_entry.insert(0, str(data["lon_e"]))
            for widget in (lat_s_entry, lat_n_entry, lon_w_entry, lon_e_entry):
                widget.config(state='disabled')
        else:
            lat_s_entry.insert(0, state.get("lat_s", ""))
            lat_n_entry.insert(0, state.get("lat_n", ""))
            lon_w_entry.insert(0, state.get("lon_w", ""))
            lon_e_entry.insert(0, state.get("lon_e", ""))
        return state
    finally:
        _is_loading_prefs = False

def stream_proc_output(proc, text_widget, log_file_handle):
    try:
        root.after(0, lambda: text_widget.delete('1.0', tk.END))
        for line in iter(proc.stdout.readline, b''):
            if not line:
                break
            decoded_line = line.decode('utf-8', errors='ignore')
            root.after(0, lambda l=decoded_line: (text_widget.insert(tk.END, l), text_widget.see(tk.END)))
            if log_file_handle:
                log_file_handle.write(decoded_line)
    except Exception:
        pass
    finally:
        if proc.stdout:
            proc.stdout.close()

def parse_ortho4xp_tile_name(folder_name):
    if not folder_name.lower().startswith("zortho4xp_"):
        return None
    tile = folder_name[10:]
    if len(tile) != 7 or tile[0] not in "+-" or tile[3] not in "+-":
        return None
    try:
        int(tile[1:3])
        int(tile[4:7])
    except ValueError:
        return None
    return tile

def ortho4xp_tile_folder_is_valid(tile_path):
    if not os.path.isdir(tile_path):
        return False
    for sub in ("Earth nav data", "Earth Nav data", "textures", "terrain", "scenery"):
        if os.path.isdir(os.path.join(tile_path, sub)):
            return True
    try:
        for name in os.listdir(tile_path):
            low = name.lower()
            if low.endswith(".dsf") or low.endswith(".ter"):
                return True
            full = os.path.join(tile_path, name)
            if os.path.isfile(full) and os.path.getsize(full) > 0:
                return True
    except Exception:
        return False
    return False

def discover_xplane_custom_scenery_dirs():
    found = []
    seen = set()

    def add(path):
        norm = os.path.normcase(os.path.normpath(path))
        if norm in seen or not os.path.isdir(path):
            return
        seen.add(norm)
        found.append(path)

    env_home = os.path.expanduser("~")
    prog_files = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    roots = [env_home, "C:\\", "D:\\", "E:\\", "F:\\"] + [p for p in prog_files if p]
    for ver in ("12", "11"):
        for root in roots:
            if not root:
                continue
            add(os.path.join(root, f"X-Plane {ver}", "Custom Scenery"))
            add(os.path.join(root, f"X-Plane{ver}", "Custom Scenery"))
        add(os.path.expandvars(rf"%ProgramFiles(x86)%\Steam\steamapps\common\X-Plane {ver}\Custom Scenery"))
        add(os.path.expandvars(rf"%ProgramFiles%\Steam\steamapps\common\X-Plane {ver}\Custom Scenery"))

    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if not os.path.exists(drive):
            continue
        try:
            for entry in os.listdir(drive):
                if not entry.lower().startswith("x-plane"):
                    continue
                add(os.path.join(drive, entry, "Custom Scenery"))
        except (PermissionError, OSError):
            pass
    return found

def scan_xplane_ortho_tiles_async():
    def worker():
        try:
            tiles, dirs = scan_xplane_ortho_tiles()
        except Exception:
            tiles, dirs = set(), []
        def apply():
            global xp_scenery_tiles, xp_scenery_scan_dirs
            with xp_scenery_scan_lock:
                xp_scenery_tiles = tiles
                xp_scenery_scan_dirs = dirs
            redraw_map_canvas()
        try:
            root.after(0, apply)
        except Exception:
            pass
    threading.Thread(target=worker, daemon=True).start()

def scan_osm_output_dir_async():
    def worker():
        path = dest_path_var.get().strip()
        ortho_dir = get_ortho4xp_dir()

        paths_to_scan = []
        if path and os.path.isdir(path):
            paths_to_scan.append(path)
        if ortho_dir:
            osm_data_path = os.path.join(ortho_dir, "OSM_data")
            if os.path.isdir(osm_data_path) and osm_data_path not in paths_to_scan:
                paths_to_scan.append(osm_data_path)

        if not paths_to_scan:
            with discovered_osm_lock:
                if discovered_osm_tiles:
                    discovered_osm_tiles.clear()
                    try: root.after(0, redraw_map_canvas)
                    except: pass
            return
        tiles = set()
        try:
            for scan_path in paths_to_scan:
                for group_folder in os.listdir(scan_path):
                    group_path = os.path.join(scan_path, group_folder)
                    if not os.path.isdir(group_path): continue
                    for tile_folder in os.listdir(group_path):
                        if _tile_name_to_lat_lon(tile_folder) is None: continue
                        tile_path = os.path.join(group_path, tile_folder)
                        if not os.path.isdir(tile_path): continue
                        is_valid = os.path.exists(os.path.join(tile_path, f"{tile_folder}_coastline.osm.bz2"))
                        if is_valid:
                            tiles.add(tile_folder)
        except (PermissionError, OSError):
            pass

        def apply():
            with discovered_osm_lock:
                global discovered_osm_tiles
                discovered_osm_tiles = tiles
            redraw_map_canvas()
        try: root.after(0, apply)
        except: pass
    threading.Thread(target=worker, daemon=True).start()

def scan_ortho_output_dir_async():
    def worker():
        path = ortho4xp_output_var.get().strip()
        if not path or not os.path.isdir(path):
            with discovered_ortho_lock:
                if discovered_ortho_tiles:
                    discovered_ortho_tiles.clear()
                    try: root.after(0, redraw_map_canvas)
                    except: pass
            return

        tiles = {}
        try:
            for folder_name in os.listdir(path):
                tile_name = parse_ortho4xp_tile_name(folder_name)
                if not tile_name: continue
                tile_path = os.path.join(path, folder_name)
                if not ortho4xp_tile_folder_is_valid(tile_path): continue

                zl = '??'
                cfg_path = os.path.join(tile_path, f"Ortho4XP_{tile_name}.cfg")
                found_zl = read_ortho4xp_cfg_value(cfg_path, "default_zl")
                if found_zl:
                    zl = found_zl
                tiles[tile_name] = zl
        except (PermissionError, OSError):
            pass

        def apply():
            with discovered_ortho_lock:
                global discovered_ortho_tiles
                discovered_ortho_tiles = tiles
            redraw_map_canvas()
        try: root.after(0, apply)
        except: pass
    threading.Thread(target=worker, daemon=True).start()

def _clamp(v, lo, hi): return max(lo, min(hi, v))

def get_tile_cache_dir():
    return _get_app_data_dir("Cache")

def _tile_cache_path(z, x, y, cache_dir=None):
    cd = cache_dir if cache_dir else get_tile_cache_dir()
    return os.path.join(cd, str(z), str(x), f"{y}.png")

def is_osm_tile_cached(z, x, y, cache_dir=None):
    p = _tile_cache_path(z, x, y, cache_dir)
    return os.path.exists(p) and os.path.getsize(p) > 100

def iter_baseline_precache_tiles():
    for z in range(OSM_PRECACHE_ZOOM_MIN, OSM_PRECACHE_ZOOM_MAX + 1):
        n = 2 ** z
        for tx in range(n):
            for ty in range(n):
                yield z, tx, ty

def download_osm_tile_to_cache(z, x, y, cache_dir=None):
    cd = cache_dir if cache_dir else get_tile_cache_dir()
    tile_dir = os.path.join(cd, str(z), str(x))
    cache_path = _tile_cache_path(z, x, y, cd)
    if is_osm_tile_cached(z, x, y, cd):
        return True
    try:
        os.makedirs(tile_dir, exist_ok=True)
        req = urllib.request.Request(OSM_TILE_URL_TEMPLATE.format(z=z, x=x, y=y), headers={"User-Agent": OSM_TILE_USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()
        with open(cache_path, "wb") as f:
            f.write(raw)
        return True
    except Exception:
        return False

def get_osm_tile_image(z, x, y, allow_network=False):
    z = int(_clamp(z, OSM_MIN_ZOOM, OSM_MAP_MAX_ZOOM))
    key = (z, x, y)
    with _tile_memory_cache_lock:
        if key in _tile_memory_cache:
            return _tile_memory_cache[key]
    cache_path = _tile_cache_path(z, x, y)
    img = None
    if is_osm_tile_cached(z, x, y):
        try: img = Image.open(cache_path).convert("RGB")
        except Exception: img = None
    if img is None and allow_network:
        if download_osm_tile_to_cache(z, x, y):
            try: img = Image.open(cache_path).convert("RGB")
            except Exception: img = None
    if img is None:
        img = Image.new("RGB", (TILE_PIXELS, TILE_PIXELS), "#d8e8f5")
    with _tile_memory_cache_lock:
        _tile_memory_cache[key] = img
    return img

def run_startup_map_cache_prefetch_async(parent_window):
    try:
        cache_dir = get_tile_cache_dir()
        all_tiles = list(iter_baseline_precache_tiles())
        missing = [(z, x, y) for z, x, y in all_tiles if not is_osm_tile_cached(z, x, y, cache_dir)]
        cached_count = len(all_tiles) - len(missing)
    except Exception:
        return

    if not missing:
        return

    splash = tk.Toplevel(parent_window)
    splash.title("Preparing Offline Map Cache")
    splash.geometry("460x170")
    splash.resizable(False, False)
    splash.transient(parent_window)
    splash.grab_set()
    ttk.Label(splash, text="Building offline OpenStreetMap cache (zoom 0-5)...", font=("Arial", 10, "bold")).pack(pady=(16, 6))
    ttk.Label(splash, text="First run downloads ~1365 tiles; later runs skip cached files.", font=("Arial", 8)).pack(pady=(0, 4))
    ttk.Label(splash, text=f"Folder: {cache_dir}", font=("Arial", 8), wraplength=420, justify="left").pack(padx=12)
    status_lbl = ttk.Label(splash, text="Initializing download...", font=("Arial", 9))
    status_lbl.pack(pady=6)
    pf = ttk.Progressbar(splash, orient="horizontal", length=400, mode="determinate", maximum=len(missing))
    pf.pack(pady=8)
    ttk.Label(splash, text="Already cached tiles are skipped. Delete the folder above to refresh.", font=("Arial", 8, "italic"), wraplength=420).pack(padx=12)

    def worker():
        downloaded = 0
        try:
            for idx, (z, x, y) in enumerate(missing, start=1):
                status_text = f"Downloading zoom {z} tile {x},{y}  ({idx}/{len(missing)} new, {cached_count} cached)"
                
                def update_ui(s=status_text, i=idx):
                    try:
                        if splash.winfo_exists():
                            status_lbl.config(text=s)
                            pf.config(value=i)
                    except tk.TclError: pass
                
                parent_window.after(0, update_ui)

                if download_osm_tile_to_cache(z, x, y, cache_dir):
                    get_osm_tile_image(z, x, y, allow_network=False)
                    downloaded += 1
                
                if idx < len(missing):
                    time.sleep(OSM_TILE_DOWNLOAD_DELAY)
        finally:
            def close_splash():
                try:
                    if splash.winfo_exists():
                        splash.grab_release()
                        splash.destroy()
                except tk.TclError: pass
            parent_window.after(0, close_splash)

    threading.Thread(target=worker, daemon=True).start()

def lonlat_to_tile_xy_float(lon, lat, zoom):
    lat = _clamp(lat, -85.05112878, 85.05112878)
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return x, y

def tile_xy_to_lonlat(x, y, zoom):
    n = 2.0 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    return lon, math.degrees(lat_rad)

def map_lonlat_to_xy(lon, lat, w, h):
    # This function converts a geographic coordinate (lon, lat) to a pixel coordinate (x, y) on the canvas.
    # It uses the Mercator projection for the Y-axis to match the OpenStreetMap tile projection,
    # ensuring that overlays align perfectly with the background map at all zoom levels.
    view = map_view_state
    # Get the Mercator "Y" coordinate for the view's top and bottom latitudes.
    _, m_y1 = lonlat_to_tile_xy_float(0, view["lat_max"], 0)
    _, m_y2 = lonlat_to_tile_xy_float(0, view["lat_min"], 0)
    # Get the Mercator "Y" for the point to plot.
    _, m_y = lonlat_to_tile_xy_float(0, lat, 0)
    # Longitude is linear in Mercator, so a simple linear interpolation is correct for X.
    x = (lon - view["lon_min"]) / ((view["lon_max"] - view["lon_min"]) or 1) * w
    # For Y, we interpolate based on the non-linear Mercator coordinates.
    y = (m_y - m_y1) / ((m_y2 - m_y1) or 1) * h
    return x, y

def map_xy_to_lonlat(x, y, w, h):
    # This function performs the inverse of map_lonlat_to_xy, converting a pixel coordinate
    # back to a geographic coordinate, correctly handling the Mercator projection.
    view = map_view_state
    # Get the Mercator "Y" coordinate for the view's top and bottom latitudes.
    _, m_y1 = lonlat_to_tile_xy_float(0, view["lat_max"], 0)
    _, m_y2 = lonlat_to_tile_xy_float(0, view["lat_min"], 0)
    # Longitude is linear, so we can find it by inverting the linear interpolation.
    lon = view["lon_min"] + (x / max(w, 1)) * (view["lon_max"] - view["lon_min"])
    # For latitude, we find the corresponding Mercator Y by interpolating in pixel space...
    y_frac = y / max(h, 1)
    m_y = m_y1 + y_frac * (m_y2 - m_y1)
    # ...and then convert that Mercator Y back to a latitude.
    _, lat = tile_xy_to_lonlat(0, m_y, 0)
    return lon, lat

def choose_zoom_for_view(canvas_w, view):
    lon_span = max(view["lon_max"] - view["lon_min"], 0.0001)
    best_z = OSM_MIN_ZOOM
    for z in range(OSM_MIN_ZOOM, OSM_MAP_MAX_ZOOM + 1):
        tiles_across = lon_span / 360.0 * (2 ** z)
        px_width = tiles_across * TILE_PIXELS
        best_z = z
        if px_width >= canvas_w:
            break
    return best_z

def build_map_background_image(canvas_w, canvas_h, view):
    zoom = choose_zoom_for_view(canvas_w, view)
    while True:
        x1f, y1f = lonlat_to_tile_xy_float(view["lon_min"], view["lat_max"], zoom)
        x2f, y2f = lonlat_to_tile_xy_float(view["lon_max"], view["lat_min"], zoom)
        tile_x_min, tile_x_max = int(math.floor(x1f)), int(math.floor(x2f))
        tile_y_min, tile_y_max = int(math.floor(y1f)), int(math.floor(y2f))
        n = 2 ** zoom
        tile_x_min, tile_x_max = max(0, tile_x_min), min(n - 1, tile_x_max)
        tile_y_min, tile_y_max = max(0, tile_y_min), min(n - 1, tile_y_max)
        cols, rows = tile_x_max - tile_x_min + 1, tile_y_max - tile_y_min + 1
        if cols * rows <= 400 or zoom <= OSM_MIN_ZOOM:
            break
        zoom -= 1
    composite = Image.new("RGB", (cols * TILE_PIXELS, rows * TILE_PIXELS), "#d8e8f5")
    for tx in range(tile_x_min, tile_x_max + 1):
        for ty in range(tile_y_min, tile_y_max + 1):
            composite.paste(get_osm_tile_image(zoom, tx, ty), ((tx - tile_x_min) * TILE_PIXELS, (ty - tile_y_min) * TILE_PIXELS))
    # Correctly calculate the crop box using Mercator projection math, not linear interpolation of lat/lon.
    # The composite image's top-left corner corresponds to the top-left of tile (tile_x_min, tile_y_min).
    # We use the fractional tile coordinates (x1f, y1f, x2f, y2f) calculated earlier.

    # Pixel coordinate of the view's top-left corner within the composite image
    cx1 = (x1f - tile_x_min) * TILE_PIXELS
    cy1 = (y1f - tile_y_min) * TILE_PIXELS

    # Pixel coordinate of the view's bottom-right corner within the composite image
    cx2 = (x2f - tile_x_min) * TILE_PIXELS
    cy2 = (y2f - tile_y_min) * TILE_PIXELS

    comp_w_px, comp_h_px = composite.size
    cx1, cx2 = max(0, cx1), min(comp_w_px, cx2)
    cy1, cy2 = max(0, cy1), min(comp_h_px, cy2)
    if cx2 <= cx1 or cy2 <= cy1:
        return Image.new("RGB", (max(1, canvas_w), max(1, canvas_h)), "#d8e8f5")
    cropped = composite.crop((int(cx1), int(cy1), int(cx2), int(cy2)))
    return cropped.resize((max(1, canvas_w), max(1, canvas_h)), Image.LANCZOS)

def request_map_background_update():
    canvas = map_window_ref["canvas"]
    if not canvas or not canvas.winfo_exists(): return
    map_bg_request_id["id"] += 1
    my_id = map_bg_request_id["id"]
    w, h = canvas.winfo_width() or 960, canvas.winfo_height() or 600
    view_snapshot = dict(map_view_state)
    def worker():
        try:
            img = build_map_background_image(w, h, view_snapshot)
        except Exception:
            img = Image.new("RGB", (w, h), "#d8e8f5")
        def apply():
            if my_id != map_bg_request_id["id"]:
                return
            map_bg_photo_ref["photo"] = ImageTk.PhotoImage(img)
            map_bg_photo_ref["for_view"] = view_snapshot
            redraw_map_canvas()
        try: canvas.after(0, apply)
        except Exception: pass
    threading.Thread(target=worker, daemon=True).start()

def _tile_name_to_lat_lon(tile_name):
    if len(tile_name) != 7:
        return None
    try:
        t_lat = int(tile_name[1:3]) * (1 if tile_name[0] == '+' else -1)
        t_lon = int(tile_name[4:7]) * (1 if tile_name[3] == '+' else -1)
        return t_lat, t_lon
    except (ValueError, IndexError):
        return None

def _draw_map_tile_highlight(canvas, w, h, tile_name, fill, label=None, outline="", stipple="gray50"):
    coords = _tile_name_to_lat_lon(tile_name)
    if coords is None:
        return
    t_lat, t_lon = coords
    x1, y1 = map_lonlat_to_xy(t_lon, t_lat + 1, w, h)
    x2, y2 = map_lonlat_to_xy(t_lon + 1, t_lat, w, h)
    canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=outline, width=1 if outline else 0, stipple=stipple, tags="mapitem")
    if label:
        canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label, fill="#4a148c", font=("Arial", 9, "bold"), tags="mapitem")

def redraw_map_canvas():
    canvas = map_window_ref["canvas"]
    if not canvas or not canvas.winfo_exists(): return
    w, h = canvas.winfo_width() or 960, canvas.winfo_height() or 600
    canvas.delete("all")
    if map_bg_photo_ref["photo"] is not None:
        canvas.create_image(0, 0, anchor='nw', image=map_bg_photo_ref["photo"], tags="mapitem")
    else:
        canvas.create_rectangle(0, 0, w, h, fill="#d8e8f5", outline="", tags="mapitem")
        canvas.create_text(w // 2, h // 2, text="Loading map tiles...", fill="#888888", font=("Arial", 12), tags="mapitem")
    view = map_view_state
    lon_start, lon_end = int(math.floor(max(view["lon_min"], -180))), int(math.ceil(min(view["lon_max"], 180)))
    lat_start, lat_end = int(math.floor(max(view["lat_min"], -90))), int(math.ceil(min(view["lat_max"], 90)))
    for lon in range(lon_start, lon_end + 1):
        x, _ = map_lonlat_to_xy(lon, 0, w, h)
        canvas.create_line(x, 0, x, h, fill="#ff8c00", width=1, tags="mapitem")
    for lat in range(lat_start, lat_end + 1):
        _, y = map_lonlat_to_xy(0, lat, w, h)
        canvas.create_line(0, y, w, y, fill="#ff8c00", width=1, tags="mapitem")

    with xp_scenery_scan_lock:
        xp_tiles_snapshot = set(xp_scenery_tiles)
    with completed_lock:
        session_osm_tiles_snapshot = set(resume_list)
    with discovered_osm_lock:
        discovered_osm_snapshot = set(discovered_osm_tiles)
    with discovered_ortho_lock:
        discovered_ortho_snapshot = dict(discovered_ortho_tiles)

    for tile_name in xp_tiles_snapshot:
        _draw_map_tile_highlight(canvas, w, h, tile_name, fill="#ce93d8", label="XP", stipple="gray50")
    for tile_name in discovered_osm_snapshot:
        _draw_map_tile_highlight(canvas, w, h, tile_name, fill="#a5d6a7", label="OSM", stipple="gray25")
    for tile_name, zl in discovered_ortho_snapshot.items():
        _draw_map_tile_highlight(canvas, w, h, tile_name, fill="#4caf50", label=f"ZL{zl}", outline="#1b5e20", stipple="gray50")
    for tile_name in session_osm_tiles_snapshot:
        _draw_map_tile_highlight(canvas, w, h, tile_name, fill="#00e676", label="OSM", outline="#00c853", stipple="gray75")

    if map_individual_selection:
        for tile_name in map_individual_selection:
            coords = _tile_name_to_lat_lon(tile_name)
            if coords is None: continue
            t_lat, t_lon = coords
            x1, y1 = map_lonlat_to_xy(t_lon, t_lat + 1, w, h)
            x2, y2 = map_lonlat_to_xy(t_lon + 1, t_lat, w, h)
            canvas.create_rectangle(x1, y1, x2, y2, outline="#e53935", width=2, fill="#ffcdd2", stipple="gray50", tags="mapitem")
        count_text = f"{len(map_individual_selection)} tile(s) selected"
        canvas.create_text(10, h - 10, anchor='sw', text=count_text, fill="#e53935", font=("Arial", 9, "bold"), tags="mapitem")
    elif map_selection_bounds:
        lat_s, lat_n, lon_w, lon_e = map_selection_bounds
        x1, y1 = map_lonlat_to_xy(lon_w, lat_n + 1, w, h)
        x2, y2 = map_lonlat_to_xy(lon_e + 1, lat_s, w, h)
        canvas.create_rectangle(x1, y1, x2, y2, outline="red", width=2, tags="mapitem")
        count = (lat_n - lat_s + 1) * (lon_e - lon_w + 1)
        count_text = f"{count} tile(s) in rectangular selection"
        canvas.create_text(10, h - 10, anchor='sw', text=count_text, fill="#e53935", font=("Arial", 9, "bold"), tags="mapitem")
    canvas.create_text(w - 6, h - 6, anchor='se', text="(c) OpenStreetMap contributors", fill="#333333", font=("Arial", 8), tags="mapitem")

def apply_map_selection_to_main(lat_s, lat_n, lon_w, lon_e):
    preset_combo.set("CUSTOM RANGE (MANUAL)")
    for widget in (lat_s_entry, lat_n_entry, lon_w_entry, lon_e_entry):
        widget.config(state='normal'); widget.delete(0, tk.END)
    lat_s_entry.insert(0, str(lat_s)); lat_n_entry.insert(0, str(lat_n))
    lon_w_entry.insert(0, str(lon_w)); lon_e_entry.insert(0, str(lon_e))

def on_map_shift_click(event):
    global map_selection_bounds, map_individual_selection
    canvas = map_window_ref["canvas"]
    w, h = canvas.winfo_width(), canvas.winfo_height()
    lon, lat = map_xy_to_lonlat(event.x, event.y, w, h)
    if map_selection_bounds:
        map_selection_bounds = None
    lat_i, lon_i = int(math.floor(lat)), int(math.floor(lon))
    tile_id = _ortho4xp_tile_id(lat_i, lon_i)
    if tile_id in map_individual_selection:
        map_individual_selection.remove(tile_id)
    else:
        map_individual_selection.add(tile_id)
    if not map_individual_selection:
        apply_map_selection_to_main("", "", "", "")
    else:
        lats = {c[0] for t in map_individual_selection if (c := _tile_name_to_lat_lon(t))}
        lons = {c[1] for t in map_individual_selection if (c := _tile_name_to_lat_lon(t))}
        min_lat, max_lat, min_lon, max_lon = min(lats), max(lats), min(lons), max(lons)
        apply_map_selection_to_main(min_lat, max_lat, min_lon, max_lon)
    redraw_map_canvas()

def on_map_left_press(event):
    if event.state & 0x0001: # Shift key
        on_map_shift_click(event)
        return
    global map_temp_rect_id
    canvas = map_window_ref["canvas"]
    w, h = canvas.winfo_width(), canvas.winfo_height()
    lon, lat = map_xy_to_lonlat(event.x, event.y, w, h)
    map_drag_start["lon"], map_drag_start["lat"] = lon, lat
    if map_temp_rect_id:
        try: canvas.delete(map_temp_rect_id)
        except: pass
    map_temp_rect_id = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=2, dash=(4, 2))
    if map_individual_selection:
        map_individual_selection.clear()
        map_selection_bounds = None
        apply_map_selection_to_main("", "", "", "")
        redraw_map_canvas()

def on_map_left_drag(event):
    canvas = map_window_ref["canvas"]
    if map_temp_rect_id is None: return
    try:
        cur = canvas.coords(map_temp_rect_id)
        canvas.coords(map_temp_rect_id, cur[0], cur[1], event.x, event.y)
    except Exception: pass

def on_map_left_release(event):
    global map_selection_bounds, map_temp_rect_id
    if map_drag_start["lon"] is None: return
    canvas = map_window_ref["canvas"]
    w, h = canvas.winfo_width(), canvas.winfo_height()
    end_lon, end_lat = map_xy_to_lonlat(event.x, event.y, w, h)
    start_lon, start_lat = map_drag_start["lon"], map_drag_start["lat"]
    map_drag_start["lon"] = None
    lon_w_raw, lon_e_raw = sorted([start_lon, end_lon])
    lat_s_raw, lat_n_raw = sorted([start_lat, end_lat])
    lon_w_i = int(math.floor(_clamp(lon_w_raw, -180, 179.999)))
    lon_e_i = int(math.floor(_clamp(lon_e_raw - 1e-9, -180, 179.999)))
    lat_s_i = int(math.floor(_clamp(lat_s_raw, -90, 89.999)))
    lat_n_i = int(math.floor(_clamp(lat_n_raw - 1e-9, -90, 89.999)))
    if lon_e_i < lon_w_i: lon_e_i = lon_w_i
    if lat_n_i < lat_s_i: lat_n_i = lat_s_i
    map_selection_bounds = (lat_s_i, lat_n_i, lon_w_i, lon_e_i)
    if map_temp_rect_id:
        try: canvas.delete(map_temp_rect_id)
        except: pass
        map_temp_rect_id = None
    apply_map_selection_to_main(lat_s_i, lat_n_i, lon_w_i, lon_e_i)
    redraw_map_canvas()

def on_map_right_press(event):
    map_pan_start["x"], map_pan_start["y"] = event.x, event.y
    map_pan_start["last_x"], map_pan_start["last_y"] = event.x, event.y
    map_pan_start["view"] = dict(map_view_state)

def on_map_right_drag(event):
    canvas = map_window_ref["canvas"]
    if map_pan_start["x"] is None: return
    dx, dy = event.x - map_pan_start["last_x"], event.y - map_pan_start["last_y"]
    canvas.move("mapitem", dx, dy)
    map_pan_start["last_x"], map_pan_start["last_y"] = event.x, event.y

def on_map_right_release(event):
    if map_pan_start["x"] is None: return
    canvas = map_window_ref["canvas"]
    w, h = canvas.winfo_width(), canvas.winfo_height()
    base = map_pan_start["view"]
    dx, dy = event.x - map_pan_start["x"], event.y - map_pan_start["y"]
    lon_span, lat_span = base["lon_max"] - base["lon_min"], base["lat_max"] - base["lat_min"]
    shift_lon, shift_lat = -(dx / w) * lon_span, (dy / h) * lat_span
    new_lon_min, new_lon_max = base["lon_min"] + shift_lon, base["lon_max"] + shift_lon
    new_lat_min, new_lat_max = base["lat_min"] + shift_lat, base["lat_max"] + shift_lat
    if new_lon_min < -180: new_lon_min, new_lon_max = -180, -180 + lon_span
    if new_lon_max > 180: new_lon_max, new_lon_min = 180, 180 - lon_span
    if new_lat_min < -90: new_lat_min, new_lat_max = -90, -90 + lat_span
    if new_lat_max > 90: new_lat_max, new_lat_min = 90, 90 - lat_span
    map_view_state.update(lon_min=new_lon_min, lon_max=new_lon_max, lat_min=new_lat_min, lat_max=new_lat_max)
    map_pan_start["x"] = None
    redraw_map_canvas()
    request_map_background_update()

def on_map_mousewheel(event):
    factor = 0.8 if event.delta > 0 else 1.25
    zoom_map(factor, cursor_xy=(event.x, event.y))

def zoom_map(factor, cursor_xy=None):
    canvas = map_window_ref["canvas"]
    w, h = canvas.winfo_width(), canvas.winfo_height()
    view = map_view_state
    if cursor_xy:
        anchor_lon, anchor_lat = map_xy_to_lonlat(cursor_xy[0], cursor_xy[1], w, h)
    else:
        anchor_lon = (view["lon_min"] + view["lon_max"]) / 2
        anchor_lat = (view["lat_min"] + view["lat_max"]) / 2
    lon_ratio = (anchor_lon - view["lon_min"]) / (view["lon_max"] - view["lon_min"])
    lat_ratio = (view["lat_max"] - anchor_lat) / (view["lat_max"] - view["lat_min"])
    new_lon_span = _clamp((view["lon_max"] - view["lon_min"]) * factor, 0.05, 360.0)
    new_lat_span = _clamp((view["lat_max"] - view["lat_min"]) * factor, 0.05, 180.0)
    new_lon_min = anchor_lon - lon_ratio * new_lon_span
    new_lon_max = new_lon_min + new_lon_span
    new_lat_max = anchor_lat + lat_ratio * new_lat_span
    new_lat_min = new_lat_max - new_lat_span
    if new_lon_min < -180: new_lon_min, new_lon_max = -180, -180 + new_lon_span
    if new_lon_max > 180: new_lon_max, new_lon_min = 180, 180 - new_lon_span
    if new_lat_min < -90: new_lat_min, new_lat_max = -90, -90 + lat_span
    if new_lat_max > 90: new_lat_max, new_lat_min = 90, 90 - lat_span
    map_view_state.update(lon_min=new_lon_min, lon_max=new_lon_max, lat_min=new_lat_min, lat_max=new_lat_max)
    redraw_map_canvas()
    request_map_background_update()

def reset_map_view():
    map_view_state.update(lon_min=-180.0, lon_max=180.0, lat_min=-85.0, lat_max=85.0)
    redraw_map_canvas()
    request_map_background_update()

def toggle_map_fullscreen():
    win = map_window_ref["win"]
    if not win: return
    is_fs = bool(win.attributes("-fullscreen"))
    win.attributes("-fullscreen", not is_fs)
    win.after(60, lambda: (redraw_map_canvas(), request_map_background_update()))

def toggle_main_fullscreen(event=None):
    is_fs = bool(root.attributes("-fullscreen"))
    root.attributes("-fullscreen", not is_fs)

def close_map_window():
    global map_refresh_job
    win = map_window_ref["win"]
    if map_refresh_job and win:
        try: win.after_cancel(map_refresh_job)
        except: pass
    map_refresh_job = None
    if win:
        try: win.destroy()
        except: pass
    map_window_ref["win"], map_window_ref["canvas"] = None, None

def refresh_map_progress():
    global map_refresh_job
    win = map_window_ref["win"]
    if not win or not win.winfo_exists():
        map_refresh_job = None
        return
    redraw_map_canvas()
    map_refresh_job = win.after(1500, refresh_map_progress)

def open_map_window():
    if map_window_ref["win"] and map_window_ref["win"].winfo_exists():
        map_window_ref["win"].lift(); map_window_ref["win"].focus_force(); return
    win = tk.Toplevel(root)
    win.title("Ortho4XP Tile Map Selector (OpenStreetMap)")
    win.geometry("1000x650")
    map_window_ref["win"] = win
    toolbar = ttk.Frame(win); toolbar.pack(side='top', fill='x')
    ttk.Button(toolbar, text="Zoom In (+)", command=lambda: zoom_map(0.6)).pack(side='left', padx=4, pady=4)
    ttk.Button(toolbar, text="Zoom Out (-)", command=lambda: zoom_map(1.6)).pack(side='left', padx=4, pady=4)
    ttk.Button(toolbar, text="Reset View", command=reset_map_view).pack(side='left', padx=4, pady=4)
    ttk.Button(toolbar, text="Fullscreen (F11)", command=toggle_map_fullscreen).pack(side='left', padx=4, pady=4)
    info_frame = ttk.Frame(toolbar)
    info_frame.pack(side='left', padx=10, fill='x', expand=True)
    ttk.Label(info_frame, text="Left Drag = Select Rectangle | Shift+Click = Select/Deselect Single Tile", font=("Arial", 8, "italic")).pack(anchor='w')
    ttk.Label(info_frame, text="Legend: Bright Green=OSM Session | Dark Green=Ortho ZL | Light Green=OSM Output | Purple=X-Plane", font=("Arial", 8)).pack(anchor='w')
    ttk.Button(toolbar, text="Close Map", command=close_map_window).pack(side='right', padx=4, pady=4)
    canvas = tk.Canvas(win, bg="#d8e8f5", highlightthickness=0)
    canvas.pack(fill='both', expand=True)
    map_window_ref["canvas"] = canvas
    canvas.bind("<ButtonPress-1>", on_map_left_press)
    canvas.bind("<B1-Motion>", on_map_left_drag)
    canvas.bind("<ButtonRelease-1>", on_map_left_release)
    canvas.bind("<ButtonPress-3>", on_map_right_press)
    canvas.bind("<B3-Motion>", on_map_right_drag)
    canvas.bind("<ButtonRelease-3>", on_map_right_release)
    canvas.bind("<MouseWheel>", on_map_mousewheel)
    canvas.bind("<Configure>", lambda e: (redraw_map_canvas(), request_map_background_update()))
    win.bind("<F11>", lambda e: toggle_map_fullscreen())
    win.bind("<Escape>", lambda e: (win.attributes("-fullscreen", False), redraw_map_canvas()))
    win.protocol("WM_DELETE_WINDOW", close_map_window)
    win.after(100, lambda: (redraw_map_canvas(), request_map_background_update()))
    scan_xplane_ortho_tiles_async()
    refresh_map_progress()

# === END MAP SELECTOR STATE ============================================

def download_ot_dem(lat, lon, dem_type, api_key, cache_dir):
    """Downloads a DEM from OpenTopography, with retries on timeout and cleanup."""
    if not api_key:
        return None, "OpenTopography API Key is missing."

    tile_name = f"{dem_type}_{lat:+03d}{lon:+04d}.tif"
    dem_cache_dir = os.path.join(cache_dir, "DEM_Cache")
    os.makedirs(dem_cache_dir, exist_ok=True)
    dem_path = os.path.join(dem_cache_dir, tile_name)

    def cleanup_failed_download():
        """Removes a partial/corrupted file if it exists."""
        if os.path.exists(dem_path):
            try:
                os.remove(dem_path)
            except OSError as e:
                # This is not a fatal error, the main error message is more important.
                print(f"Warning: Could not clean up failed DEM download {dem_path}: {e}")

    # If a valid file exists, use it.
    if os.path.exists(dem_path) and os.path.getsize(dem_path) > 1000:
        return dem_path, "Using cached DEM."
    # If an invalid/partial file exists from a previous failed run, clean it up before trying to download.
    elif os.path.exists(dem_path):
        cleanup_failed_download()

    url = (f"https://portal.opentopography.org/API/globaldem?demtype={dem_type}"
           f"&south={lat}&north={lat+1}&west={lon}&east={lon+1}"
           f"&outputFormat=GTiff&API_Key={api_key}")

    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # --- Attempt 1: Use curl (cross-platform and reliable) ---
            if shutil.which("curl"):
                result = subprocess.run(["curl", "-L", "-o", dem_path, "-sS", url],
                                        check=False, startupinfo=startupinfo, timeout=120,
                                        capture_output=True, text=True)
                if result.returncode == 0:
                    if os.path.exists(dem_path) and os.path.getsize(dem_path) > 1000:
                        return dem_path, "Downloaded successfully via curl."
                else:
                    if "401" in result.stderr and "Unauthorized" in result.stderr:
                        cleanup_failed_download()
                        return None, "curl download failed: HTTP Error 401 (Unauthorized). Please double-check your API key."
                    # If curl fails for another reason, we'll print the error and fall through to the Python method.
                    print(f"curl failed for DEM {tile_name}: {result.stderr.strip()}")
                    cleanup_failed_download()

            # --- Attempt 2: Use Python's native urllib (universal fallback) ---
            import ssl
            context = ssl._create_unverified_context()
            req = urllib.request.Request(url, headers={"User-Agent": "Ortho-Optimizer-Downloader/1.0"})
            with urllib.request.urlopen(req, context=context, timeout=120) as response:
                if response.status != 200:
                    if response.status == 401:
                        return None, f"Python download failed: HTTP Error {response.status} (Unauthorized). Please double-check your API key."
                    raise urllib.error.HTTPError(url, response.status, "Server returned non-200 status", response.headers, None)
                with open(dem_path, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
            
            if os.path.exists(dem_path) and os.path.getsize(dem_path) > 1000:
                return dem_path, "Downloaded successfully via Python native."
            else:
                raise IOError("Downloaded file is missing or empty.")

        except (subprocess.TimeoutExpired, urllib.error.URLError) as e:
            import socket
            if isinstance(e, urllib.error.URLError) and not isinstance(e.reason, socket.timeout):
                cleanup_failed_download()
                return None, f"A network error occurred: {e}"

            cleanup_failed_download()
            if attempt < max_retries - 1:
                # ... (user prompt logic)
                # I will copy this logic from the original function.
                should_retry = False
                if threading.current_thread() is not threading.main_thread():
                    response_queue = queue.Queue()
                    def do_prompt():
                        try:
                            answer = messagebox.askyesno("DEM Download Timeout",
                                                         f"Downloading DEM for tile {lat},{lon} timed out during batch processing.\n\n"
                                                         f"Attempt {attempt + 1} of {max_retries} failed. Retry?")
                            response_queue.put(answer)
                        except Exception:
                            response_queue.put(False)
                    root.after(0, do_prompt)
                    try:
                        should_retry = response_queue.get(timeout=60)
                    except queue.Empty:
                        should_retry = False
                else:
                    should_retry = messagebox.askyesno("DEM Download Timeout",
                                                       f"Downloading DEM for tile {lat},{lon} timed out.\n\n"
                                                       f"Attempt {attempt + 1} of {max_retries} failed. Retry?")

                if should_retry:
                    status_update_msg = f"DEM download for {lat},{lon} timed out. Retrying in 10 seconds..."
                    if threading.current_thread() is not threading.main_thread():
                        root.after(0, lambda s=status_update_msg: ortho_status_var.set(s))
                    time.sleep(10)
                    continue
                else:
                    return None, "The download command timed out and user chose not to retry."
            else:
                return None, f"The download command timed out after {max_retries} attempts."

        except urllib.error.HTTPError as e:
            cleanup_failed_download()
            if e.code == 401:
                return None, f"Python download failed: HTTP Error {e.code} (Unauthorized). Please double-check your API key."
            return None, f"An HTTP error occurred during download: {e}"

        except Exception as e:
            cleanup_failed_download()
            return None, f"An unexpected error occurred during download: {e}"

    cleanup_failed_download()
    return None, f"The download command failed after {max_retries} attempts."

# === ORTHO4XP INTEGRATION HELPERS ======================================
def get_ortho4xp_dir():
    exe = ortho4xp_exe_var.get().strip()
    return os.path.dirname(os.path.abspath(exe)) if exe else ""

def get_xplane12_default_overlay_path():
    """Finds the path to the default X-Plane 12 dsf_earth_overlays directory."""
    xp_root = find_xplane_root_path()
    if xp_root and "X-Plane 12" in os.path.basename(xp_root):
        return os.path.join(xp_root, "Global Scenery", "X-Plane 12 Global Scenery", "dsf_earth_overlays")
    return None

def check_and_warn_default_overlay_path(path_to_check):
    """Shows a warning if the provided path matches the default XP12 overlay path."""
    if not path_to_check:
        return

    xp12_overlay_path = get_xplane12_default_overlay_path()
    if not xp12_overlay_path:
        return  # Can't find XP12, so can't warn.

    try:
        # Most reliable check, works on case-insensitive filesystems.
        is_same_path = os.path.samefile(path_to_check, xp12_overlay_path)
    except (FileNotFoundError, OSError):
        # Fallback to string comparison if one path doesn't exist.
        is_same_path = os.path.normcase(os.path.abspath(path_to_check)) == os.path.normcase(os.path.abspath(xp12_overlay_path))

    if is_same_path:
        messagebox.showwarning(
            "Warning: Default Overlay Folder Selected",
            "You have selected the default X-Plane 12 global scenery overlay folder:\n\n"
            f"{path_to_check}\n\n"
            "It is NOT recommended to have Ortho4XP write directly into this folder. "
            "Doing so can overwrite default scenery files and may cause issues with X-Plane updates.\n\n"
            "Please consider choosing a different, empty folder for your custom overlays."
        )

def get_ortho4xp_cfg_path():
    d = get_ortho4xp_dir()
    return os.path.join(d, "Ortho4XP.cfg") if d else ""

def discover_ortho4xp_providers():
    fallback_providers = ["BI", "GO2", "Arc", "Arc@", "EOX", "EOX2", "Here", "Mapbox", "Maxar", "USA2", "OSM", "SEA", "NAIP", "SP"]
    
    ortho_dir = get_ortho4xp_dir()
    if not ortho_dir:
        return fallback_providers
    
    providers_dir = os.path.join(ortho_dir, "Providers")
    if not os.path.isdir(providers_dir):
        return fallback_providers
    
    providers = []
    try:
        for f in os.listdir(providers_dir):
            if f.lower().endswith(".py") and not f.startswith('_'):
                providers.append(os.path.splitext(f)[0])
    except OSError:
        return fallback_providers
    
    return sorted(providers) if providers else fallback_providers

def read_ortho4xp_cfg_value(cfg_path, key):
    if not cfg_path or not os.path.exists(cfg_path):
        return None
    try:
        with open(cfg_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s.startswith(key) and "=" in s:
                    k, v = s.split("=", 1)
                    if k.strip() == key:
                        return v.strip().strip("'\"")
    except Exception:
        pass
    return None

def read_ortho4xp_hierarchical_cfg_value(ortho_dir, key):
    if not ortho_dir:
        return None

    # Check user-specific config first, as it takes precedence.
    user_cfg_path = os.path.join(ortho_dir, "Ortho4XP.cfg")
    value = read_ortho4xp_cfg_value(user_cfg_path, key)
    if value is not None:
        return value

    # If not in user config, check the base/internal config.
    base_cfg_path = os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "Ortho4XP.cfg")
    value = read_ortho4xp_cfg_value(base_cfg_path, key)
    if value is not None:
        return value
            
    return None

def sync_ortho4xp_defaults_from_cfg():
    ortho_dir = get_ortho4xp_dir()
    if not ortho_dir:
        return
    scenery_dir = read_ortho4xp_hierarchical_cfg_value(ortho_dir, "custom_scenery_dir") or read_ortho4xp_hierarchical_cfg_value(ortho_dir, "custom_build_dir")
    if not ortho4xp_output_var.get().strip():
        # 1. Attempt to find X-Plane's Custom Scenery folder first
        xp_root = find_xplane_root_path()
        if xp_root:
            xp_custom_scenery = os.path.join(xp_root, "Custom Scenery")
            if os.path.isdir(xp_custom_scenery):
                ortho4xp_output_var.set(xp_custom_scenery)
            else:
                # If Custom Scenery path doesn't exist, fall back to Ortho4XP's configured scenery_dir
                if scenery_dir and os.path.isdir(scenery_dir):
                    ortho4xp_output_var.set(scenery_dir)
                else:
                    # Final fallback to Ortho4XP's default Tiles folder
                    ortho4xp_output_var.set(os.path.join(ortho_dir, "Tiles"))
        elif scenery_dir and os.path.isdir(scenery_dir):
            # If no X-Plane root found, but Ortho4XP's config has a valid scenery_dir, use that.
            ortho4xp_output_var.set(scenery_dir)
        else:
            # Final fallback if neither X-Plane Custom Scenery nor Ortho4XP's configured scenery_dir is found.
            ortho4xp_output_var.set(os.path.join(ortho_dir, "Tiles"))
    web = read_ortho4xp_hierarchical_cfg_value(ortho_dir, "default_website")
    zl = read_ortho4xp_hierarchical_cfg_value(ortho_dir, "default_zl")
    dem = read_ortho4xp_hierarchical_cfg_value(ortho_dir, "custom_dem")
    if web:
        ortho_imagery_var.set(web)
    if zl:
        ortho_zl_var.set(zl)
    if dem:
        ortho_dem_choice_var.set("Custom DEM File...")
        ortho_dem_custom_path_var.set(dem)

    # NEW: Logic for overlay_dir
    if not ortho4xp_overlay_var.get().strip():
        cfg_overlay_dir = read_ortho4xp_hierarchical_cfg_value(ortho_dir, "custom_overlay_src")
        if cfg_overlay_dir and os.path.isdir(cfg_overlay_dir):
            ortho4xp_overlay_var.set(cfg_overlay_dir)
            check_and_warn_default_overlay_path(cfg_overlay_dir)
        elif ortho_dir:  # Default to Ortho4XP's internal overlay folder
            default_overlay_path = os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "yOrtho4XP_Overlays")
            ortho4xp_overlay_var.set(default_overlay_path)


def ensure_ortho4xp_cfg_synced():
    exe = ortho4xp_exe_var.get().strip()
    if not exe or not os.path.exists(exe):
        return (False, "Ortho4XP.exe path is not set or invalid.")

    ortho_dir = get_ortho4xp_dir()

    # Find X-Plane path if not already set in Ortho4XP's config
    xp_root_from_cfg = read_ortho4xp_hierarchical_cfg_value(ortho_dir, "xp_path")
    xp_root_to_write = xp_root_from_cfg
    if not xp_root_from_cfg or not os.path.isdir(xp_root_from_cfg):
        xp_root_to_write = find_xplane_root_path()

    current = {
        "xp_path": xp_root_from_cfg,
        "default_website": read_ortho4xp_hierarchical_cfg_value(ortho_dir, "default_website"),
        "default_zl": read_ortho4xp_hierarchical_cfg_value(ortho_dir, "default_zl"),
        "custom_scenery_dir": read_ortho4xp_hierarchical_cfg_value(ortho_dir, "custom_scenery_dir") or read_ortho4xp_hierarchical_cfg_value(ortho_dir, "custom_build_dir"),
        "custom_dem": read_ortho4xp_hierarchical_cfg_value(ortho_dir, "custom_dem"),
        "dem_source": read_ortho4xp_hierarchical_cfg_value(ortho_dir, "dem_source"),
        "custom_overlay_src": read_ortho4xp_hierarchical_cfg_value(ortho_dir, "custom_overlay_src"),  # NEW
    }
    desired = {
        "xp_path": xp_root_to_write,
        "default_website": ortho_imagery_var.get().strip() or current["default_website"] or "BI",
        "default_zl": ortho_zl_var.get().strip() or current["default_zl"] or "16",
        "custom_scenery_dir": ortho4xp_output_var.get().strip() or current["custom_scenery_dir"] or os.path.join(ortho_dir, "Tiles"),
        "custom_dem": get_ortho4xp_dem_value() or current["custom_dem"] or "",
        "dem_source": get_ortho4xp_dem_source_value() or current["dem_source"] or "",
        "custom_overlay_src": ortho4xp_overlay_var.get().strip() or current["custom_overlay_src"] or os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "yOrtho4XP_Overlays"),  # NEW
    }

    final_custom_dem_for_global_sync = desired["custom_dem"]
    if final_custom_dem_for_global_sync in ("COP30", "SRTMGL1"):
        final_custom_dem_for_global_sync = "" # Don't write these specific identifiers to the global config.

    if any((current[k] or "") != (desired[k] or "") for k in desired):
        ok, info = write_ortho4xp_main_panel_settings(
            imagery=desired["default_website"],
            zl=desired["default_zl"],
            scenery_dir=desired["custom_scenery_dir"],
            custom_dem=final_custom_dem_for_global_sync,
            custom_build_dir=desired["custom_scenery_dir"],
            dem_source=desired["dem_source"],
            xp_path=desired["xp_path"],
            custom_overlay_src=desired["custom_overlay_src"]
        )
        if ok:
            return (True, f"Settings synced to Ortho4XP config file(s).")
        else:
            return (False, f"Failed to write settings:\n{info}")

    return (True, "Settings are already in sync.")

def manual_sync_with_ortho4xp():
    ok, info = ensure_ortho4xp_cfg_synced()
    if ok:
        if "already in sync" in info:
            messagebox.showinfo("Sync", info)
        else:
            messagebox.showinfo("Sync Complete", info)
    else:
        messagebox.showerror("Sync Error", info)

def browse_ortho4xp_exe():
    f_name = filedialog.askopenfilename(
        title="Select Ortho4XP launcher",
        filetypes=(("Ortho4XP launcher", "Ortho4XP*.exe"), ("Python entrypoint", "Ortho4XP.py"), ("All", "*.*"))
    )
    if f_name:
        ortho4xp_exe_var.set(f_name)
        update_ortho4xp_providers_list()
        sync_ortho4xp_defaults_from_cfg()
        ok, info = ensure_ortho4xp_cfg_synced()
        if not ok:
            messagebox.showwarning("Sync Warning", f"Could not automatically sync settings with new Ortho4XP path:\n{info}")
        save_last_paths_checkpoint()

def update_ortho4xp_providers_list():
    providers = discover_ortho4xp_providers()
    current_val = ortho_imagery_var.get()
    ortho_imagery_combo['values'] = providers
    if current_val in providers:
        ortho_imagery_var.set(current_val)

def browse_ortho4xp_output():
    d_name = filedialog.askdirectory(title="Select Ortho4XP Tile Output Destination (separate from the OSM Output Destination)")
    if d_name:
        ortho4xp_output_var.set(d_name)
        save_last_paths_checkpoint()

def get_ortho4xp_dem_value():
    choice = ortho_dem_choice_var.get()
    if choice.startswith("Custom"):
        return ortho_dem_custom_path_var.get().strip()
    else:
        return ORTHO4XP_DEM_MAP.get(choice, "")

ORTHO4XP_DEM_SOURCE_MAP = {
    "Default (Viewfinderpanoramas.org)": "", 
    "USGS 1/3 arc-second": "usgs",
    "SRTM / OpenTopography": "srtm",
    "Copernicus GLO-30 (OpenTopography)": "custom",
    "Custom DEM File...": "custom"
}

def get_ortho4xp_dem_source_value():
    choice = ortho_dem_choice_var.get()
    return ORTHO4XP_DEM_SOURCE_MAP.get(choice, "")

def on_dem_choice_change(event=None):
    if ortho_dem_choice_var.get().startswith("Custom"):
        f = filedialog.askopenfilename(
            title="Select Custom DEM File (raster, EPSG:4326 - requires Gdal)",
            filetypes=(("Raster files", "*.tif *.tiff *.hgt *.dem *.asc"), ("All files", "*.*"))
        )
        if f:
            ortho_dem_custom_path_var.set(f); ortho_dem_path_label.config(text=f); save_last_paths_checkpoint()
        else:
            ortho_dem_choice_var.set("Default (Viewfinderpanoramas.org)")
            ortho_dem_custom_path_var.set("")
            ortho_dem_path_label.config(text="(using Ortho4XP's default elevation data)")
            save_last_paths_checkpoint()

# NEW: Function to browse for overlay folder
def browse_ortho4xp_overlay():
    d_name = filedialog.askdirectory(title="Select Ortho4XP Overlay Folder")
    if d_name:
        check_and_warn_default_overlay_path(d_name)
        ortho4xp_overlay_var.set(d_name)
        save_last_paths_checkpoint()

def _format_cfg_value(key, value):
    """Helper to format config values for Ortho4XP.cfg files."""
    if isinstance(value, bool):
        return "True" if value else "False"
    
    formatted_value = str(value).replace('\\', '/')
    
    # Ortho4XP doesn't like quotes around paths or simple values in its config
    if formatted_value.startswith("'") and formatted_value.endswith("'"):
        formatted_value = formatted_value.strip("'")
    elif formatted_value.startswith('"') and formatted_value.endswith('"'):
        formatted_value = formatted_value.strip('"')

    return formatted_value

def read_full_hierarchical_cfg(ortho_dir):
    """Reads the full Ortho4XP config, merging the base and user files."""
    base_cfg = {}
    user_cfg = {}

    base_cfg_path = os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "Ortho4XP.cfg")
    user_cfg_path = os.path.join(ortho_dir, "Ortho4XP.cfg")

    if os.path.exists(base_cfg_path):
        try:
            with open(base_cfg_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    stripped_line = line.strip()
                    if not stripped_line or '=' not in stripped_line or stripped_line.startswith('#'):
                        continue
                    key, value = stripped_line.split('=', 1)
                    base_cfg[key.strip()] = value.strip().strip("'\"")
        except Exception:
            pass # Ignore errors reading base config

    if os.path.exists(user_cfg_path):
        try:
            with open(user_cfg_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    stripped_line = line.strip()
                    if not stripped_line or '=' not in stripped_line or stripped_line.startswith('#'):
                        continue
                    key, value = stripped_line.split('=', 1)
                    user_cfg[key.strip()] = value.strip().strip("'\"")
        except Exception:
            pass # Ignore errors reading user config

    # Merge them, with user config taking precedence
    merged_cfg = {**base_cfg, **user_cfg}
    return merged_cfg

def write_ortho4xp_main_panel_settings(imagery=None, zl=None, scenery_dir=None, custom_dem=None, custom_build_dir=None, dem_source=None, ot_api_key=None, xp_path=None, custom_overlay_src=None):
    ortho_dir = get_ortho4xp_dir()
    if not ortho_dir:
        return False, "Ortho4XP.exe path is not set."

    # Define both possible config paths to ensure compatibility with different Ortho4XP versions.
    user_cfg_path = os.path.join(ortho_dir, "Ortho4XP.cfg")
    base_cfg_path = os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "Ortho4XP.cfg")

    # 1. Read the full hierarchical config to get a complete starting point.
    current_cfg_dict = read_full_hierarchical_cfg(ortho_dir)

    # 2. Update specific keys with new values from the UI/arguments.
    if imagery is not None: current_cfg_dict["default_website"] = imagery
    if zl is not None: current_cfg_dict["default_zl"] = zl
    if scenery_dir is not None:
        current_cfg_dict["custom_scenery_dir"] = scenery_dir # Ensure this is always set if provided
        # Ortho4XP often uses custom_build_dir for the same purpose, ensure consistency
        current_cfg_dict["custom_build_dir"] = scenery_dir # Always set custom_build_dir to scenery_dir if scenery_dir is provided
    if custom_build_dir is not None: current_cfg_dict["custom_build_dir"] = custom_build_dir
    
    # Special handling for custom_dem in the GLOBAL config:
    # The global custom_dem should only be a file path. DEM types are for per-tile configs.
    if custom_dem is not None:
        if custom_dem in ("COP30", "SRTMGL1", "Viewfinderpanoramas (J. de Ferranti) - mostly worldwide", "USGS 1/3 arc-second"):
            # If a DEM type is passed, do NOT write it to the global custom_dem.
            # Instead, ensure the global custom_dem is empty or unset.
            if "custom_dem" in current_cfg_dict:
                del current_cfg_dict["custom_dem"]
        else:
            current_cfg_dict["custom_dem"] = custom_dem
    
    if dem_source is not None: current_cfg_dict["dem_source"] = dem_source
    if ot_api_key is not None: current_cfg_dict["ot_api_key"] = ot_api_key
    if xp_path is not None: current_cfg_dict["xp_path"] = xp_path

    if custom_overlay_src is not None: current_cfg_dict["custom_overlay_src"] = custom_overlay_src  # NEW

    # Ensure boolean values are correctly represented in the dictionary before writing
    for key in CANONICAL_KEYS:
        if key in current_cfg_dict and isinstance(current_cfg_dict[key], bool):
            current_cfg_dict[key] = "True" if current_cfg_dict[key] else "False"

    # 3. Build the new file content in canonical order.
    new_content = []
    for key in CANONICAL_KEYS:
        if key in current_cfg_dict:
            formatted_value = _format_cfg_value(key, current_cfg_dict[key])

            # Don't write empty API key
            if key == 'ot_api_key' and not formatted_value:
                continue
            
            # Don't write empty xp_path
            if key == 'xp_path' and not formatted_value:
                continue
            
            # Don't write empty xp_path
            if key == 'xp_path' and not formatted_value:
                continue
            
            new_content.append(f"{key}={formatted_value}\n")

    # 4. Write to BOTH config file locations to ensure compatibility.
    # This is slightly redundant for modern versions but guarantees settings are applied for older ones.
    error_messages = []
    # We write to the base config first, then the user config. This is just a preference.
    for path in [base_cfg_path, user_cfg_path]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(new_content)
        except Exception as e:
            error_messages.append(f"Could not write to {os.path.basename(path)}:\n{e}")

    if error_messages:
        return False, "\n".join(error_messages)

    return True, "Config files updated."

def write_ortho4xp_last_gui_params(lat, lon, imagery, zl):
    d = get_ortho4xp_dir()
    if not d:
        return
    try:
        with open(os.path.join(d, ".last_gui_params.txt"), "w", encoding="utf-8") as f:
            f.write(f"{lat} {lon} {imagery} {zl}\n")
            f.write("\n")
    except Exception:
        pass

def _ortho4xp_default_tile_dir(ortho_dir, tile_id):
    return os.path.join(ortho_dir, "Tiles", f"zOrtho4XP_{tile_id}")

def write_ortho4xp_tile_config(ortho_dir, tile_id, imagery, zl, custom_dem, custom_build_dir=None, dem_source=None):
    tile_dir = _ortho4xp_default_tile_dir(ortho_dir, tile_id)
    
    # Ensure custom_dem is correctly formatted for the tile config
    formatted_custom_dem = ""
    if custom_dem:
        formatted_custom_dem = _format_cfg_value("custom_dem", custom_dem)

    try:
        os.makedirs(tile_dir, exist_ok=True)
        cfg_path = os.path.join(tile_dir, f"Ortho4XP_{tile_id}.cfg")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(f"default_website = {imagery}\n")
            f.write(f"default_zl = {zl}\n")
            f.write("skip_osm_download = True\n")
            if formatted_custom_dem:
                f.write(f"custom_dem = {formatted_custom_dem}\n")
            if dem_source:
                f.write(f"dem_source = {dem_source}\n")
            if custom_build_dir:
                f.write(f"custom_build_dir = '{custom_build_dir.replace('\\', '/')}'\n")
        return True
    except Exception:
        return False

def _locate_ortho4xp_tile_folder(ortho_dir, tile_id, dest_dir=None):
    folder_name = f"zOrtho4XP_{tile_id}"

    cfg_path = get_ortho4xp_cfg_path()
    configured_build_dir = read_ortho4xp_cfg_value(cfg_path, "custom_scenery_dir") or read_ortho4xp_cfg_value(cfg_path, "custom_build_dir")
    
    candidates = []
    if dest_dir:
        candidates.append(os.path.join(dest_dir, folder_name))
    if configured_build_dir:
        candidates.append(os.path.join(configured_build_dir, folder_name))
    if ortho_dir:
        candidates.append(os.path.join(ortho_dir, "Tiles", folder_name))
        candidates.append(os.path.join(ortho_dir, "Ortho4XP_Data", "Tiles", folder_name))
        candidates.append(os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "Tiles", folder_name))

    unique_candidates = []
    seen_paths = set()
    for c in candidates:
        if not c: continue
        try:
            abs_c = os.path.abspath(c)
            if abs_c not in seen_paths:
                unique_candidates.append(c)
                seen_paths.add(abs_c)
        except Exception:
            continue

    valid_candidates = []
    for c in unique_candidates:
        if ortho4xp_tile_folder_is_valid(c):
            valid_candidates.append(c)

    if not valid_candidates:
        return None

    if len(valid_candidates) == 1:
        return valid_candidates[0]

    best_candidate = None
    max_textures = -1
    for c in valid_candidates:
        tex_count = _count_tile_textures(c)
        if tex_count > max_textures:
            max_textures = tex_count
            best_candidate = c
    
    return best_candidate

def _count_tile_textures(tile_folder):
    if not tile_folder:
        return 0
    tex_dir = os.path.join(tile_folder, "textures")
    if not os.path.isdir(tex_dir):
        return 0
    try:
        return len([f for f in os.listdir(tex_dir) if f.lower().endswith((".dds", ".jpg", ".jpeg", ".png"))])
    except Exception:
        return 0

def check_ortho4xp_provider_available(ortho_dir, imagery):
    prov_dir = os.path.join(ortho_dir, "Providers")
    if not os.path.isdir(prov_dir):
        return None
    try:
        names = [os.path.splitext(f)[0].lower() for f in os.listdir(prov_dir)]
        return imagery.lower() in names
    except Exception:
        return None

def _ortho4xp_log_path(tile_id):
    log_dir = _get_app_data_dir("Ortho4XP_Logs")
    return os.path.join(log_dir, f"Ortho4XP_{tile_id}_{int(time.time())}.log")


def _get_ortho4xp_launch_command(ortho_dir, exe_path):
    if not ortho_dir:
        return None
    py_script = os.path.join(ortho_dir, "Ortho4XP.py")
    if os.path.exists(py_script) and sys.executable:
        return [sys.executable, py_script]
    if exe_path and os.path.exists(exe_path):
        return [exe_path]
    return None


def relocate_finished_ortho4xp_tile(ortho_dir, dest_dir, tile_id):
    if not dest_dir:
        return None
    src = _locate_ortho4xp_tile_folder(ortho_dir, tile_id, dest_dir)
    if not src:
        return None
    try:
        os.makedirs(dest_dir, exist_ok=True)
        target = os.path.join(dest_dir, os.path.basename(src))
        if os.path.abspath(target) == os.path.abspath(src):
            return src
        if os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True)
        shutil.move(src, target)
        return target
    except Exception:
        return None

def _ortho4xp_tile_id(lat, lon):
    l_p = "+" if lat >= 0 else "-"
    o_p = "+" if lon >= 0 else "-"
    return f"{l_p}{str(abs(lat)).zfill(2)}{o_p}{str(abs(lon)).zfill(3)}"

def _ortho4xp_session_path():
    d = get_ortho4xp_dir()
    return os.path.join(d, "OSM_Creator_Ortho4XP_Batch_Session.json") if d else ""

def _load_ortho4xp_session():
    global ortho4xp_resume_list
    p = _ortho4xp_session_path()
    ortho4xp_resume_list = []
    if p and os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                ortho4xp_resume_list = json.load(f).get("completed", [])
        except Exception:
            ortho4xp_resume_list = []


def cleanup_selected_tile_batch():
    exe_path = ortho4xp_exe_var.get().strip()
    if not exe_path or not os.path.exists(exe_path):
        messagebox.showerror("Validation Error", "Please select a valid Ortho4XP launcher first.")
        return
    dest_dir = ortho4xp_output_var.get().strip()

    tile_ids_to_remove = []
    if map_individual_selection:
        tile_ids_to_remove = list(map_individual_selection)
    else:
        try:
            S_LAT, E_LAT = int(lat_s_entry.get().strip()), int(lat_n_entry.get().strip())
            S_LON, E_LON = int(lon_w_entry.get().strip()), int(lon_e_entry.get().strip())
            if S_LAT > E_LAT or S_LON > E_LON:
                messagebox.showerror("Logic Error", "Starting coordinates must be lower than ending limits!")
                return
            tile_ids_to_remove = [_ortho4xp_tile_id(lat, lon) for lat in range(S_LAT, E_LAT + 1) for lon in range(S_LON, E_LON + 1)]
        except (ValueError, TypeError):
            messagebox.showerror("Format Error", "Coordinates parameters must use whole integers only and must not be empty!")
            return

    if not tile_ids_to_remove:
        messagebox.showinfo("Cleanup Complete", "No selected tiles were found to remove.")
        return

    tile_folders_to_remove = [f"zOrtho4XP_{tile_id}" for tile_id in tile_ids_to_remove]
    if not messagebox.askyesno("Confirm Tile Cleanup", f"This will permanently delete {len(tile_folders_to_remove)} selected Ortho4XP tile folders from their output locations.\n\nThis action cannot be undone. Are you sure?"):
        return

    removed_count = 0
    failed_count = 0
    ortho_dir = get_ortho4xp_dir()
    search_dirs_for_tiles = []
    if dest_dir and os.path.isdir(dest_dir):
        search_dirs_for_tiles.append(dest_dir)
    default_tile_root = os.path.join(ortho_dir, "Tiles") if ortho_dir else None
    if default_tile_root and os.path.isdir(default_tile_root) and default_tile_root not in search_dirs_for_tiles:
        search_dirs_for_tiles.append(default_tile_root)
    internal_tile_root = os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "Tiles") if ortho_dir else None
    if internal_tile_root and os.path.isdir(internal_tile_root) and internal_tile_root not in search_dirs_for_tiles:
        search_dirs_for_tiles.append(internal_tile_root)

    for tile_folder in tile_folders_to_remove:
        for base_dir in search_dirs_for_tiles:
            full_path = os.path.join(base_dir, tile_folder)
            if os.path.isdir(full_path):
                try:
                    shutil.rmtree(full_path)
                    removed_count += 1
                except Exception:
                    failed_count += 1    

    _load_ortho4xp_session()
    removed_ids_set = set(tile_ids_to_remove)
    global ortho4xp_resume_list
    ortho4xp_resume_list = [tile for tile in ortho4xp_resume_list if tile not in removed_ids_set]
    _save_ortho4xp_session()
    
    summary = f"Cleanup finished.\n\nRemoved {removed_count} tile folder(s).\n"
    if failed_count > 0:
        summary += f"Failed to remove {failed_count} items due to permissions or other errors."
    messagebox.showinfo("Cleanup Complete", summary)
    scan_ortho_output_dir_async()
    redraw_map_canvas()

def cleanup_osm_data():
    global resume_list
    dest_dir = dest_path_var.get().strip()
    if not dest_dir or not os.path.isdir(dest_dir):
        messagebox.showerror("Destination Required", "Please choose a valid OSM Tile Data Output Folder before cleaning.")
        return

    tiles_to_remove = []
    if map_individual_selection:
        tiles_to_remove = list(map_individual_selection)
    else:
        try:
            S_LAT, E_LAT = int(lat_s_entry.get().strip()), int(lat_n_entry.get().strip())
            S_LON, E_LON = int(lon_w_entry.get().strip()), int(lon_e_entry.get().strip())
            if S_LAT > E_LAT or S_LON > E_LON:
                messagebox.showerror("Logic Error", "Starting coordinates must be lower than ending limits!")
                return
            tiles_to_remove = [_ortho4xp_tile_id(lat, lon) for lat in range(S_LAT, E_LAT + 1) for lon in range(S_LON, E_LON + 1)]
        except (ValueError, TypeError):
            messagebox.showerror("Format Error", "Coordinates parameters must use whole integers only and must not be empty!")
            return

    if not tiles_to_remove:
        messagebox.showinfo("Cleanup", "No tiles selected to clean up.")
        return

    if not messagebox.askyesno("Confirm OSM Data Cleanup", f"This will permanently delete {len(tiles_to_remove)} selected OSM tile folders and mark them as incomplete for the current session.\n\nThis action cannot be undone. Are you sure?"):
        return

    removed_count = 0
    for tile_id in tiles_to_remove:
        coords = _tile_name_to_lat_lon(tile_id)
        if not coords: continue
        t_lat, t_lon = (coords[0] // 10) * 10, (coords[1] // 10) * 10
        group_folder_name = f"{'+' if t_lat >= 0 else '-'}{str(abs(t_lat)).zfill(2)}{'+' if t_lon >= 0 else '-'}{str(abs(t_lon)).zfill(3)}"
        tile_folder_path = os.path.join(dest_dir, group_folder_name, tile_id)
        if os.path.isdir(tile_folder_path):
            try:
                shutil.rmtree(tile_folder_path)
                removed_count += 1
            except Exception:
                pass

    with completed_lock:
        tiles_to_remove_set = set(tiles_to_remove)
        resume_list = [tile for tile in resume_list if tile not in tiles_to_remove_set]
    
    _save_osm_session_file()

    messagebox.showinfo("Cleanup Complete", f"Successfully removed {removed_count} OSM tile folder(s) and updated session state.")
    scan_osm_output_dir_async()


def cleanup_app_temp_folder():
    temp_dir = _get_app_data_dir("Temp")
    if not os.path.isdir(temp_dir):
        messagebox.showinfo("Cleanup", "No temporary folder found to clean.")
        return

    if not messagebox.askyesno("Confirm Cache Cleanup", 
        f"This will permanently delete the application's temporary data folder:\n\n{temp_dir}\n\n"
        "This is useful for clearing out old session files or corrupted data from a failed run. This action cannot be undone. Are you sure?"):
        return

    try:
        shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        messagebox.showinfo("Cleanup Complete", "The temporary data folder has been cleared.")
    except Exception as e:
        messagebox.showerror("Cleanup Error", f"Could not clear the temporary folder:\n{e}")


def _save_ortho4xp_session():
    p = _ortho4xp_session_path()
    if not p:
        return
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"completed": ortho4xp_resume_list}, f)
    except Exception:
        pass

def trigger_ortho4xp_pause():
    global ortho4xp_is_paused
    ortho4xp_is_paused = True
    ortho_btn_pause.pack_forget(); ortho_btn_resume.pack(side='left', padx=10, pady=10)
    ortho_status_var.set("Status: Paused. Current tile keeps building; the next one waits.")

def trigger_ortho4xp_resume():
    global ortho4xp_is_paused
    ortho4xp_is_paused = False
    ortho_btn_resume.pack_forget(); ortho_btn_pause.pack(side='left', padx=10, pady=10)
    ortho_status_var.set("Status: Resuming Ortho4XP batch...")

def _restore_ortho_panel():
    # Reset progress UI elements to their initial state
    ortho_status_var.set("Status: Awaiting Ortho4XP batch start...")
    ortho_metrics_var.set("Completed: 0  |  Remaining: 0  |  Total Tiles: 0")
    ortho_progress_bar['value'] = 0
    ortho_log_text.delete('1.0', tk.END)

    ortho_progress_frame.pack_forget()
    # Restore the main UI frames in their correct original order
    input_frame.pack(fill='x', expand=True, padx=10, pady=5)
    step2_outer_frame.pack(fill='x', expand=True, padx=10, pady=5)
    link_container.pack(fill='x', expand=True, padx=10, pady=(5,0))
    dem_link_container.pack(fill='x', expand=True, padx=10, pady=(0,5))

def test_ortho4xp_single_tile():
    exe_path = ortho4xp_exe_var.get().strip()
    if not exe_path or not os.path.exists(exe_path):
        messagebox.showerror("Validation Error", "Please select a valid Ortho4XP launcher first."); return
    try:
        lat, lon = int(lat_s_entry.get().strip()), int(lon_w_entry.get().strip())
    except ValueError:
        messagebox.showerror("Format Error", "Set valid whole-number Start Latitude / Start Longitude first."); return
    imagery = ortho_imagery_var.get().strip() or "BI"
    zl = ortho_zl_var.get().strip() or "16"
    custom_dem = get_ortho4xp_dem_value()
    dem_source = get_ortho4xp_dem_source_value()
    dest_dir = ortho4xp_output_var.get().strip()
    ok, info = ensure_ortho4xp_cfg_synced()
    if not ok:
        if not messagebox.askyesno("Sync Warning", f"Could not sync settings to Ortho4XP config before test run:\n{info}\n\nThis may cause the test to use old settings. Continue anyway?"):
            return
    write_ortho4xp_last_gui_params(lat, lon, imagery, zl)
    cwd = get_ortho4xp_dir()
    tile_id = _ortho4xp_tile_id(lat, lon)

    write_ortho4xp_last_gui_params(lat, lon, imagery, zl) # Always remember last tile
    final_custom_dem = custom_dem
    final_dem_source = dem_source
    dem_choice = ortho_dem_choice_var.get()
    ot_dem_type = ORTHO4XP_DEM_MAP.get(dem_choice)

    if ot_dem_type in ("COP30", "SRTMGL1"):
        if not ot_api_key_var.get().strip():
            messagebox.showerror("API Key Required", f"An OpenTopography API key is required to download {dem_choice} DEMs.")
            return
        ortho_status_var.set(f"Downloading {ot_dem_type} DEM for tile {lat},{lon}...")
        root.update_idletasks()
        dem_cache_dir = os.path.join(get_ortho4xp_dir(), "DEMs")
        downloaded_dem_path, msg = download_ot_dem(lat, lon, ot_dem_type, ot_api_key_var.get().strip(), dem_cache_dir)
        if downloaded_dem_path:
            final_custom_dem = downloaded_dem_path
            final_dem_source = "custom"
        else:
            messagebox.showerror("DEM Download Failed", f"Could not download {ot_dem_type} DEM for tile {lat},{lon}.\n\nReason: {msg}")
            return

    prov_ok = check_ortho4xp_provider_available(cwd, imagery)
    if prov_ok is False and not messagebox.askyesno(
        "Provider Not Found",
        f"No provider file matching '{imagery}' was found in:\n{os.path.join(cwd, 'Providers')}\n\n"
        "This usually means imagery/texture download will fail. Continue anyway?"
    ):
        return
    # Always sync main panel settings before a test run
    write_ortho4xp_main_panel_settings(imagery=imagery, zl=zl, scenery_dir=dest_dir or None, custom_dem=final_custom_dem, custom_build_dir=dest_dir or None, dem_source=final_dem_source, custom_overlay_src=ortho4xp_overlay_var.get().strip() or None)
    write_ortho4xp_tile_config(cwd, tile_id, imagery, zl, final_custom_dem, dest_dir or None, dem_source=final_dem_source) # Write tile-specific config
    cmd = _get_ortho4xp_launch_command(cwd, exe_path)
    if cmd is None:
        messagebox.showerror("Launch Error", "Could not find a runnable Ortho4XP launcher."); return
    cmd.extend([str(lat), str(lon), imagery, zl])
    log_path = _ortho4xp_log_path(tile_id)

    def worker():
        try:
            def show_log_panel():
                input_frame.pack_forget()
                step2_outer_frame.pack_forget()
                link_container.pack_forget()
                dem_link_container.pack_forget()
                ortho_progress_frame.pack(fill='both', expand=True, padx=10, pady=20)
                ortho_status_var.set(f"Running test for tile {tile_id}...")
            root.after(0, show_log_panel)

            with open(log_path, "w", encoding="utf-8", errors="ignore") as logf:
                proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=False, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                output_thread = threading.Thread(target=stream_proc_output, args=(proc, ortho_log_text, logf), daemon=True)
                output_thread.start()
                proc.wait()
        except Exception as e:
            root.after(0, lambda: messagebox.showerror("Launch Error", f"Could not launch Ortho4XP.exe:\n{e}"))
            return
        tile_folder = _locate_ortho4xp_tile_folder(cwd, tile_id, dest_dir)
        tex_count = _count_tile_textures(tile_folder)
        crashed = False
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                log_tail = f.read()[-1500:]
            crashed = "Crash!" in log_tail or "Traceback" in log_tail
        except Exception:
            log_tail = ""
        moved_to = relocate_finished_ortho4xp_tile(cwd, dest_dir, tile_id) if dest_dir else None
        def done():
            msg = f"Ortho4XP ran for tile {tile_id} (imagery={imagery}, ZL={zl}).\n\nCommand used: {' '.join(cmd)}\n"
            if tex_count > 0:
                msg += f"\n✔ {tex_count} imagery/texture file(s) found in the tile's textures folder - the satellite download worked."
            else:
                msg += ("\n⚠ No imagery/texture files were found in the tile's textures folder - the satellite "
                        "download did NOT happen. Check the log below for the actual cause "
                        f"(network, provider mismatch, missing Gdal, etc.):\n{log_path}")
            if crashed:
                msg += "\n\n⚠ Ortho4XP's own log shows a crash/error - see the log file above for details."
            if dest_dir:
                msg += f"\n\nFinished tile moved to:\n{moved_to}" if moved_to else \
                       f"\n\nCould not find the finished 'zOrtho4XP_{tile_id}' folder to move - check manually under:\n{os.path.join(cwd, 'Tiles')}"
            messagebox.showinfo("Test Tile Complete", msg)
            _restore_ortho_panel()
        root.after(0, done)

    messagebox.showinfo(
        "Test Tile Started",
        f"Building tile {tile_id} now with imagery={imagery}, ZL={zl}.\n\n"
        "This runs Ortho4XP's full pipeline (vector data + mesh + imagery download) and can take a "
        "few minutes. A confirmation popup will appear when it's done, including whether textures actually downloaded."
    )
    threading.Thread(target=worker, daemon=True).start()

def run_ortho4xp_batch():
    global ortho4xp_is_paused, ortho_tiles_to_process_global
    exe_path = ortho4xp_exe_var.get().strip()
    if not exe_path or not os.path.exists(exe_path):
        messagebox.showerror("Validation Error", "Please select a valid Ortho4XP.exe first."); return
    dest_dir = ortho4xp_output_var.get().strip()
    if not dest_dir:
        messagebox.showerror("Destination Required", "Please choose an Ortho4XP Tile Output Destination before starting a batch build - this is required so finished tiles land in a predictable place."); return

    tiles_to_process = []
    if map_individual_selection:
        for tile_id in sorted(list(map_individual_selection)):
            coords = _tile_name_to_lat_lon(tile_id)
            if coords:
                tiles_to_process.append((coords[0], coords[1]))
    else:
        try:
            S_LAT, E_LAT = int(lat_s_entry.get().strip()), int(lat_n_entry.get().strip())
            S_LON, E_LON = int(lon_w_entry.get().strip()), int(lon_e_entry.get().strip())
            if S_LAT > E_LAT or S_LON > E_LON:
                messagebox.showerror("Logic Error", "Starting coordinates must be lower than ending limits!"); return
            tiles_to_process = [(lat, lon) for lat in range(S_LAT, E_LAT + 1) for lon in range(S_LON, E_LON + 1)]
        except (ValueError, TypeError):
            messagebox.showerror("Format Error", "Coordinates parameters must use whole integers only and must not be empty!"); return

    ortho_tiles_to_process_global = tiles_to_process

    if not tiles_to_process:
        messagebox.showinfo("No Tiles Selected", "There are no tiles in the current selection to process.")
        return

    imagery = ortho_imagery_var.get().strip() or "BI"
    zl = ortho_zl_var.get().strip() or "16"
    custom_dem = get_ortho4xp_dem_value()
    dem_source = get_ortho4xp_dem_source_value()
    ok, info = ensure_ortho4xp_cfg_synced()
    if not ok:
        if not messagebox.askyesno("Sync Warning", f"Could not sync settings to Ortho4XP config before batch run:\n{info}\n\nThis may cause the batch to use old settings. Continue anyway?"):
            return
    write_ortho4xp_last_gui_params(tiles_to_process[0][0], tiles_to_process[0][1], imagery, zl)
    write_ortho4xp_last_gui_params(tiles_to_process[0][0], tiles_to_process[0][1], imagery, zl) # Always remember last tile
    ortho_dir = get_ortho4xp_dir()

    prov_ok = check_ortho4xp_provider_available(ortho_dir, imagery)
    if prov_ok is False and not messagebox.askyesno(
        "Provider Not Found",
        f"No provider file matching '{imagery}' was found in:\n{os.path.join(ortho_dir, 'Providers')}\n\n"
        "This usually means imagery/texture download will fail for every tile in this batch. Continue anyway?"
    ):
        return
    if len(tiles_to_process) > 25 and not messagebox.askyesno(
        "Confirm Large Batch",
        f"This will sequentially build {len(tiles_to_process)} tile(s) in Ortho4XP, one full Ortho4XP run per tile.\n"
        "This can take a very long time (hours to days depending on ZL). Continue?"
    ):
        return
    # Always sync main panel settings before a batch run
    ok, info = write_ortho4xp_main_panel_settings(imagery=imagery, zl=zl, scenery_dir=dest_dir, custom_dem=custom_dem, custom_build_dir=dest_dir, ot_api_key=ot_api_key_var.get().strip(), dem_source=dem_source, custom_overlay_src=ortho4xp_overlay_var.get().strip() or None)
    if not ok:
        messagebox.showerror("Config Error", info); return
    ortho4xp_is_paused = False
    _load_ortho4xp_session()
    input_frame.pack_forget(); step2_outer_frame.pack_forget(); link_container.pack_forget(); dem_link_container.pack_forget()
    ortho_progress_frame.pack(fill='both', expand=True, padx=10, pady=20)
    threading.Thread(target=ortho4xp_worker_process, args=(tiles_to_process, exe_path, imagery, zl, custom_dem, dest_dir, dem_source), daemon=True).start()

def ortho4xp_worker_process(tiles, exe_path, imagery, zl, custom_dem, dest_dir, dem_source):
    global ortho4xp_resume_list, ortho4xp_active_proc
    cwd = get_ortho4xp_dir()
    total = len(tiles)
    already_done = set(ortho4xp_resume_list)
    completed = len([t for t in tiles if _ortho4xp_tile_id(*t) in already_done])
    failed_tiles = [] # For tiles with no textures
    crashed_tiles = [] # For tiles that crashed Ortho4XP
    ortho_progress_bar["maximum"] = total
    root.after(0, lambda p=completed: ortho_progress_bar.config(value=p))
    start_time = time.time()
    for lat, lon in tiles:
        tile_id = _ortho4xp_tile_id(lat, lon)
        while ortho4xp_is_paused:
            root.after(0, lambda: ortho_status_var.set("Status: Paused - click Resume to continue.")); time.sleep(0.3)
        if tile_id in already_done:
            continue
        elapsed_so_far = int(time.time() - start_time)

        final_custom_dem = custom_dem
        final_dem_source = dem_source
        dem_choice = ortho_dem_choice_var.get()
        ot_dem_type = ORTHO4XP_DEM_MAP.get(dem_choice)

        if ot_dem_type in ("COP30", "SRTMGL1"):
            status_text = f"Downloading {ot_dem_type} DEM for {tile_id}..."
            root.after(0, lambda s=status_text: ortho_status_var.set(s))
            dem_cache_dir = os.path.join(get_ortho4xp_dir(), "DEMs")
            downloaded_dem_path, msg = download_ot_dem(lat, lon, ot_dem_type, ot_api_key_var.get().strip(), dem_cache_dir)
            if downloaded_dem_path:
                final_custom_dem = downloaded_dem_path
                final_dem_source = "custom"
            else:
                failed_tiles.append(f"{tile_id} (DEM: {msg})")
                completed += 1
                continue

        status_text = f"Building tile {tile_id} ({completed + 1}/{total}) | Imagery={imagery} ZL={zl} | Downloading imagery + building mesh... | Elapsed: {elapsed_so_far // 60}m {elapsed_so_far % 60}s"
        root.after(0, lambda s=status_text: ortho_status_var.set(s))
        
        write_ortho4xp_tile_config(cwd, tile_id, imagery, zl, final_custom_dem, dest_dir, final_dem_source)
        cmd = _get_ortho4xp_launch_command(cwd, exe_path)
        if cmd is None:
            err_text = f"Error: could not find a runnable Ortho4XP launcher for tile {tile_id}"
            root.after(0, lambda e=err_text: ortho_status_var.set(e)); time.sleep(2.0)
            continue
        cmd.extend([str(lat), str(lon), imagery, str(zl)])
        log_path = _ortho4xp_log_path(tile_id)
        try:
            with open(log_path, "w", encoding="utf-8", errors="ignore") as logf:
                proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=False, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                ortho4xp_active_proc["proc"] = proc
                output_thread = threading.Thread(target=stream_proc_output, args=(proc, ortho_log_text, logf), daemon=True)
                output_thread.start()
                proc.wait()
        except Exception as e:
            root.after(0, lambda: ortho_status_var.set(f"Error launching Ortho4XP for tile {tile_id}: {e}"))
        ortho4xp_active_proc["proc"] = None

        built_folder = _locate_ortho4xp_tile_folder(cwd, tile_id, dest_dir)
        tex_count = _count_tile_textures(built_folder)

        crashed = False
        if tex_count == 0: # Only check for crash if the primary success metric (textures) fails
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    log_content = f.read()
                crashed = "Crash!" in log_content or "Traceback" in log_content
            except Exception:
                pass # Log file might not exist or be readable, etc.

            if crashed:
                crashed_tiles.append(tile_id)
            else:
                # This is for cases where it ran but didn't download imagery (e.g., provider error)
                failed_tiles.append(tile_id)
        
        moved_path = None
        if dest_dir and built_folder:
            root.after(0, lambda: ortho_status_var.set(f"Moving finished tile {tile_id} to Ortho4XP Tile Output Destination..."))
            moved_path = relocate_finished_ortho4xp_tile(cwd, dest_dir, tile_id)

        tile_is_successfully_placed = (moved_path is not None) or (not dest_dir and built_folder is not None)
        
        if tex_count > 0 and tile_is_successfully_placed:
            already_done.add(tile_id)
            ortho4xp_resume_list = list(already_done)
            _save_ortho4xp_session()

        completed += 1
        elapsed = int(time.time() - start_time)
        metrics_text = f"Completed: {completed} | Remaining: {total - completed} | Total: {total} | Failed: {len(failed_tiles) + len(crashed_tiles)}\nElapsed: {elapsed // 60}m {elapsed % 60}s"
        root.after(0, lambda m=metrics_text, p=completed: (ortho_metrics_var.set(m), ortho_progress_bar.config(value=p)))
    root.after(0, lambda: _handle_ortho4xp_worker_completion(completed, total, failed_tiles, crashed_tiles, start_time))

# === END ORTHO4XP INTEGRATION HELPERS ==================================
CANONICAL_KEYS = [
    "xp_path", "apt_smoothing_pix", "road_level", "road_banking_limit", "lane_width", "max_levelled_segs",
    "water_simplification", "min_area", "max_area", "clean_bad_geometries", "mesh_zl",
    "curvature_tol", "apt_curv_tol", "apt_curv_ext", "coast_curv_tol", "coast_curv_ext",
    "limit_tris", "min_angle", "sea_smoothing_mode", "water_smoothing", "iterate",
    "mask_zl", "masks_width", "masking_mode", "use_masks_for_inland", "imprint_masks_to_dds",
    "distance_masks_too", "masks_use_DEM_too", "masks_custom_extent",
    "cover_airports_with_highres", "cover_extent", "cover_zl", "sea_texture_blur",
    "water_tech", "ratio_water", "ratio_bathy", "normal_map_strength",
    "terrain_casts_shadows", "overlay_lod", "use_decal_on_terrain",
    "fill_nodata", "verbosity", "cleaning_level", "overpass_server_choice",
    "skip_downloads", "skip_converts", "max_download_slots",
    "max_convert_slots", "check_tms_response", "http_timeout", "ot_api_key",
    "max_connect_retries", "max_baddata_retries", "ovl_exclude_pol", "ovl_exclude_net", "custom_dem",
    "custom_scenery_dir",
    "default_website", "default_zl", "dem_source",
    "custom_build_dir",
    # "overlay_dir", # Removed as custom_overlay_src is the correct key
    "custom_overlay_src",
]

def open_ortho4xp_global_settings_window():
    ortho_dir = get_ortho4xp_dir()
    if not ortho_dir:
        messagebox.showerror("Ortho4XP Path Missing", "Please set the Ortho4XP.exe location first.")
        return

    # The file we will write to is the user-level config.
    user_cfg_path = os.path.join(ortho_dir, "Ortho4XP.cfg")
    base_cfg_path = os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "Ortho4XP.cfg")

    # Check if at least one config file exists.
    if not os.path.exists(user_cfg_path) and not os.path.exists(base_cfg_path):
        if not messagebox.askyesno("Config Not Found", f"No Ortho4XP.cfg found in the Ortho4XP directory.\n\nDo you want to create a new one with default values?"):
            return

    settings_win = tk.Toplevel(root)
    settings_win.title("Ortho4XP Global Configuration")
    settings_win.transient(root)
    settings_win.grab_set()

    # Main frame for layout
    main_frame = ttk.Frame(settings_win)
    main_frame.pack(fill="both", expand=True)

    # --- Button at the bottom ---
    button_frame = ttk.Frame(main_frame)
    button_frame.pack(side="bottom", fill='x', pady=5)

    # --- Scrollable area for settings ---
    canvas_frame = ttk.Frame(main_frame)
    canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
    canvas = tk.Canvas(canvas_frame, highlightthickness=0) # This is the widget that needs its background set
    if is_dark:
        # Explicitly set the canvas background color for dark mode
        canvas.configure(bg=dark_bg)
    scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)

    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    def _on_mousewheel_cfg(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    settings_win.bind("<MouseWheel>", _on_mousewheel_cfg)

    # --- Read and display settings ---
    # Read the full merged configuration.
    current_cfg = read_full_hierarchical_cfg(ortho_dir)

    keys_to_hide = {
        "custom_scenery_dir", "default_website", "default_zl", "dem_source", "custom_build_dir", "custom_dem",
        "ot_api_key", "custom_overlay_src"
    }

    boolean_keys = {
        "clean_bad_geometries", "use_masks_for_inland", "imprint_masks_to_dds",
        "distance_masks_too", "masks_use_DEM_too",
        "cover_airports_with_highres", "terrain_casts_shadows", "use_decal_on_terrain",
        "fill_nodata", "skip_downloads", "skip_converts", "check_tms_response"
    }

    ui_vars = {}
    row_idx = 0
    for key in CANONICAL_KEYS:
        if key in keys_to_hide:
            continue

        if key in boolean_keys:
            var = tk.BooleanVar(value=str(current_cfg.get(key, 'False')).lower() in ('true', '1', 't', 'y', 'yes'))
            ui_vars[key] = var
            ttk.Label(scrollable_frame, text=f"{key}:").grid(row=row_idx, column=0, sticky="w", padx=5, pady=2)
            chk = ttk.Checkbutton(scrollable_frame, variable=var)
            chk.grid(row=row_idx, column=1, sticky="w", padx=5, pady=2)
        else:
            var = tk.StringVar(value=current_cfg.get(key, ''))
            ui_vars[key] = var
            ttk.Label(scrollable_frame, text=f"{key}:").grid(row=row_idx, column=0, sticky="w", padx=5, pady=2)
            entry = ttk.Entry(scrollable_frame, textvariable=var, width=60)
            entry.grid(row=row_idx, column=1, sticky="ew", padx=5, pady=2)
        row_idx += 1

    scrollable_frame.grid_columnconfigure(1, weight=1)

    # --- Save function ---
    def save_and_sync_settings():
        try:
            # 1. Collect updated values from the UI.
            updated_values = {key: var.get() for key, var in ui_vars.items()}

            # 2. Start with the full hierarchical configuration.
            final_cfg = current_cfg.copy()
            # 3. Overwrite with the new values from the UI. This preserves all other keys.
            final_cfg.update(updated_values)

            # 4. Build the new file content in the correct order.
            new_content = []
            for key in CANONICAL_KEYS:
                if key in final_cfg:
                    formatted_value = _format_cfg_value(key, final_cfg.get(key, ''))
                    new_content.append(f"{key}={formatted_value}\n")

            # 5. Write the complete, updated configuration back to BOTH files for compatibility.
            error_messages = []
            for path in [base_cfg_path, user_cfg_path]:
                try:
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, 'w', encoding='utf-8') as f:
                        f.writelines(new_content)
                except Exception as e:
                    error_messages.append(f"Could not write to {os.path.basename(path)}:\n{e}")
            if error_messages:
                raise Exception("\n".join(error_messages))

            messagebox.showinfo("Success", "Ortho4XP.cfg has been updated.", parent=settings_win)
            settings_win.destroy()
            # Re-sync the main panel UI with the new settings.
            sync_ortho4xp_defaults_from_cfg()

        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to write to config file(s):\n{e}", parent=settings_win)

    ttk.Button(button_frame, text="Sync to Ortho4XP", command=save_and_sync_settings, style="Success.TButton").pack(pady=5)

    # --- Auto-adjust window size ---
    settings_win.update_idletasks()

    content_height = scrollable_frame.winfo_reqheight()
    button_height = button_frame.winfo_reqheight()

    # Define max height based on screen, e.g., 85%
    max_height = int(settings_win.winfo_screenheight() * 0.85)

    # Padding for window chrome, internal frames, etc.
    total_padding = 60 

    required_height = content_height + button_height + total_padding

    final_height = min(required_height, max_height)

    # Set geometry. Keep width fixed, adjust height.
    settings_win.geometry(f"700x{final_height}")
    settings_win.minsize(600, 400) # Set a reasonable minimum size


def _show_step1_summary_and_restore_ui(total_tiles, final_elapsed, failed_tiles):
    msg = (f"Step 1: OSM Data Creation Complete\n\n"
           f"• Total Tiles Processed: {total_tiles}\n"
           f"• Total Time: {final_elapsed // 60}m {final_elapsed % 60}s")
    if failed_tiles:
        msg += f"\n\n⚠ {len(failed_tiles)} tile(s) failed to process due to errors with osmconvert/osmfilter:\n" + ", ".join(failed_tiles[:20])
        if len(failed_tiles) > 20: msg += "\n..."
    messagebox.showinfo("Process Complete", msg)

    # Reset progress UI elements to their initial state
    status_var.set("Status: Awaiting execution initialization...")
    metrics_var.set("Completed: 0  |  Remaining: 0  |  Total Tiles: 0")
    progress_bar['value'] = 0

    progress_frame.pack_forget()
    # Restore the main UI frames in their correct original order
    input_frame.pack(fill='x', expand=True, padx=10, pady=5)
    step2_outer_frame.pack(fill='x', expand=True, padx=10, pady=5)
    link_container.pack(fill='x', expand=True, padx=10, pady=(5,0))
    dem_link_container.pack(fill='x', expand=True, padx=10, pady=(0,5))

def _handle_ortho4xp_worker_completion(completed, total, failed_tiles, crashed_tiles, start_time):
    elapsed = int(time.time() - start_time)
    ortho_status_var.set(f"Status: Ortho4XP batch finished! Total time: {elapsed // 60}m {elapsed % 60}s")
    summary = f"Finished building {completed}/{total} tile(s) with Ortho4XP."
    if crashed_tiles:
        summary += f"\n\n⚠ {len(crashed_tiles)} tile(s) appear to have crashed Ortho4XP:\n" + ", ".join(crashed_tiles[:10])
        if len(crashed_tiles) > 10: summary += "..."
    if failed_tiles:
        summary += f"\n\n⚠ {len(failed_tiles)} tile(s) completed but had NO texture files (imagery download likely failed):\n" + ", ".join(failed_tiles[:10])
        if len(failed_tiles) > 10: summary += "..."
    if failed_tiles or crashed_tiles:
        summary += f"\n\nCheck the individual log files for details in:\n{_get_app_data_dir('Ortho4XP_Logs')}"
    messagebox.showinfo("Ortho4XP Batch Complete", summary)
    _restore_ortho_panel()

def on_preset_change(event):
    selected = preset_combo.get()
    data = PRESETS[selected]
    for widget in (lat_s_entry, lat_n_entry, lon_w_entry, lon_e_entry):
        widget.config(state='normal')
        widget.delete(0, tk.END)
    lat_s_entry.insert(0, str(data["lat_s"]))
    lat_n_entry.insert(0, str(data["lat_n"]))
    lon_w_entry.insert(0, str(data["lon_w"]))
    lon_e_entry.insert(0, str(data["lon_e"]))
    if data.get("file"):
        file_path_var.set(os.path.join(util_path_var.get().strip(), data["file"]))
    elif selected != "CUSTOM RANGE (MANUAL)":
        file_path_var.set("")
    if selected != "CUSTOM RANGE (MANUAL)":
        for widget in (lat_s_entry, lat_n_entry, lon_w_entry, lon_e_entry):
            widget.config(state='disabled')
    save_last_paths_checkpoint()

def toggle_mode_widgets(event=None):
    active_mode = mode_combo.get().strip()
    trig_state = "normal" if active_mode == "Create Real OSM Data Mesh" else "disabled"
    util_entry.config(state=trig_state)
    pbf_entry.config(state=trig_state)
    for child in util_btn_frame.winfo_children():
        child.config(state=trig_state)
    save_last_paths_checkpoint()
def browse_utils():
    f_dir = filedialog.askdirectory(initialdir=util_path_var.get(), title="Select Utilities Folder")
    if f_dir:
        util_path_var.set(os.path.normpath(f_dir))
        save_last_paths_checkpoint()

def browse_file():
    f_name = filedialog.askopenfilename(initialdir=util_path_var.get(), title="Select OSM PBF File", filetypes=(("OSM PBF", "*.osm.pbf"), ("All", "*.*")))
    if f_name:
        file_path_var.set(f_name)
        save_last_paths_checkpoint()

def browse_destination():
    f_dir = filedialog.askdirectory(initialdir=dest_path_var.get(), title="Select Output Folder")
    if f_dir:
        dest_path_var.set(os.path.normpath(f_dir))
        save_last_paths_checkpoint()

def open_path_in_explorer(path_var):
    """Opens the given path or its parent directory in the system's file explorer."""
    path = path_var.get().strip()
    if not path:
        messagebox.showwarning("Path Not Set", "The path is not set.")
        return

    target_path = path
    if os.path.isfile(path):
        target_path = os.path.dirname(path)
    
    if not os.path.isdir(target_path):
        messagebox.showwarning("Path Not Found", f"The folder does not exist:\n{target_path}")
        return

    try:
        if sys.platform == "win32":
            os.startfile(os.path.normpath(target_path))
        elif sys.platform == "darwin":
            subprocess.run(["open", os.path.normpath(target_path)])
        else:
            subprocess.run(["xdg-open", os.path.normpath(target_path)])
    except Exception as e:
        messagebox.showerror("Error", f"Could not open folder:\n{e}")

def open_geofabrik_link(event):
    webbrowser.open_new("https://geofabrik.de")

def open_osmconvert_link(event):
    webbrowser.open_new("https://wiki.openstreetmap.org/wiki/Osmconvert#Windows")

def open_osmfilter_link(event):
    webbrowser.open_new("https://wiki.openstreetmap.org/wiki/Osmfilter#Windows_Binaries")

def open_opentopo_link(event):
    webbrowser.open_new("https://portal.opentopography.org/datasets")

def open_ot_api_key_link(event):
    webbrowser.open_new("https://portal.opentopography.org/myopentopo/")

def cleanup_incomplete_osm_data():
    dest_dir = dest_path_var.get().strip()
    if not dest_dir or not os.path.isdir(dest_dir):
        return

    with completed_lock:
        completed_set = set(resume_list)
    
    all_tile_ids = [_ortho4xp_tile_id(lat, lon) for lat, lon in all_tiles_to_process_global]
    
    tiles_to_remove = [tile_id for tile_id in all_tile_ids if tile_id not in completed_set]

    if not tiles_to_remove:
        return

    for tile_id in tiles_to_remove:
        coords = _tile_name_to_lat_lon(tile_id)
        if not coords: continue
        t_lat, t_lon = (coords[0] // 10) * 10, (coords[1] // 10) * 10
        group_folder_name = f"{'+' if t_lat >= 0 else '-'}{str(abs(t_lat)).zfill(2)}{'+' if t_lon >= 0 else '-'}{str(abs(t_lon)).zfill(3)}"
        tile_folder_path = os.path.join(dest_dir, group_folder_name, tile_id)
        if os.path.isdir(tile_folder_path):
            try:
                shutil.rmtree(tile_folder_path)
            except Exception:
                pass

def cleanup_incomplete_ortho_data():
    dest_dir = ortho4xp_output_var.get().strip()
    ortho_dir = get_ortho4xp_dir()

    completed_set = set(ortho4xp_resume_list)
    all_tile_ids = [_ortho4xp_tile_id(lat, lon) for lat, lon in ortho_tiles_to_process_global]
    tiles_to_remove = [tile_id for tile_id in all_tile_ids if tile_id not in completed_set]
    
    if not tiles_to_remove:
        return

    tile_folders_to_remove = [f"zOrtho4XP_{tile_id}" for tile_id in tiles_to_remove]

    search_dirs_for_tiles = []
    if dest_dir and os.path.isdir(dest_dir):
        search_dirs_for_tiles.append(dest_dir)
    default_tile_root = os.path.join(ortho_dir, "Tiles") if ortho_dir else None
    if default_tile_root and os.path.isdir(default_tile_root) and default_tile_root not in search_dirs_for_tiles:
        search_dirs_for_tiles.append(default_tile_root)
    internal_tile_root = os.path.join(ortho_dir, "_internal", "Ortho4XP_Data", "Tiles") if ortho_dir else None
    if internal_tile_root and os.path.isdir(internal_tile_root) and internal_tile_root not in search_dirs_for_tiles:
        search_dirs_for_tiles.append(internal_tile_root)

    for tile_folder in tile_folders_to_remove:
        for base_dir in search_dirs_for_tiles:
            full_path = os.path.join(base_dir, tile_folder)
            if os.path.isdir(full_path):
                try:
                    shutil.rmtree(full_path)
                except Exception:
                    pass

def on_close_requested():
    is_osm_running = progress_frame.winfo_ismapped()
    is_ortho_running = ortho_progress_frame.winfo_ismapped()

    if is_osm_running or is_ortho_running:
        if messagebox.askyesno("Process Running", 
                               "A batch process is currently running. Closing now will stop it.\n\n"
                               "All incomplete tile data will be deleted. Are you sure you want to exit and clean up?"):
            if is_osm_running:
                cleanup_incomplete_osm_data()
            if is_ortho_running:
                cleanup_incomplete_ortho_data()
            
            on_close_purge(complete_success=False)
        # else: user cancelled, do nothing
    else:
        save_last_paths_checkpoint()
        on_close_purge(complete_success=False)

def on_close_purge(complete_success=False):
    global active_subprocesses, pool_executor
    close_map_window()
    if pool_executor:
        try: pool_executor.shutdown(wait=False, cancel_futures=True)
        except: pass
    with subprocess_lock:
        for proc in active_subprocesses:
            try: proc.terminate()
            except: pass
            try: proc.kill()
            except: pass
    t_dir = _get_app_data_dir("Temp")
    if os.path.exists(t_dir):
        time.sleep(0.5)
        # Always clear temp on exit unless it was a fully successful run.
        if not complete_success:
            try: shutil.rmtree(t_dir, ignore_errors=True)
            except Exception: pass
    try: root.destroy()
    except: pass

def _save_osm_session_file():
    if not session_file_path: return
    with completed_lock:
        completed_snapshot = list(resume_list)
    
    try:
        with open(session_file_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (IOError, json.JSONDecodeError):
        state = {}
    
    state["completed_checklist"] = completed_snapshot
    
    try:
        with open(session_file_path, "w", encoding="utf-8") as sf:
            json.dump(state, sf, indent=4)
    except IOError:
        pass

def _handle_bg_worker_completion(total_tiles, loop_start_time, failed_tiles):
    final_elapsed = int(time.time() - loop_start_time)
    status_var.set("Status: OSM data creation complete!")

    if pool_executor:
        try: pool_executor.shutdown(wait=False, cancel_futures=True)
        except: pass
    if master_region_path and os.path.exists(master_region_path):
        try: os.remove(master_region_path)
        except: pass
    if session_file_path and os.path.exists(session_file_path):
        try: os.remove(session_file_path)
        except: pass

    if auto_run_ortho_var.get():
        ok, info = ensure_ortho4xp_cfg_synced()
        if not ok:
            if not messagebox.askyesno("Sync Warning", f"Could not sync settings to Ortho4XP config before auto-starting Step 2:\n{info}\n\nThis may cause the batch to use old settings. Continue anyway?"): # pragma: no cover
                _show_step1_summary_and_restore_ui(total_tiles, final_elapsed, failed_tiles)
                return

        progress_frame.pack_forget()
        
        countdown_win = tk.Toplevel(root)
        countdown_win.title("Auto-Starting Step 2")
        countdown_win.geometry("400x120")
        countdown_win.resizable(False, False)
        countdown_win.transient(root)
        
        countdown_label_var = tk.StringVar()
        ttk.Label(countdown_win, text="Step 1: OSM data creation is finished.", font=("Arial", 10, "bold")).pack(pady=(10, 5))
        ttk.Label(countdown_win, textvariable=countdown_label_var, font=("Arial", 10)).pack(pady=5)
        
        def countdown_and_start(seconds_left):
            if not countdown_win.winfo_exists(): return # pragma: no cover
            if seconds_left > 0:
                countdown_label_var.set(f"Automatically starting Ortho4XP batch build in {seconds_left} seconds...")
                countdown_win.after(1000, lambda: countdown_and_start(seconds_left - 1))
            else:
                countdown_win.destroy()
                run_ortho4xp_batch()

        countdown_and_start(5)
    else:
        _show_step1_summary_and_restore_ui(total_tiles, final_elapsed, failed_tiles)

def check_for_non_ascii_paths(paths_dict):
    has_issue = False
    for name, path in paths_dict.items():
        if not path: continue
        try:
            path.encode('ascii')
        except UnicodeEncodeError:
            has_issue = True
            messagebox.showwarning(
                "Potential Path Issue",
                f"The path for '{name}' contains non-English (non-ASCII) characters:\n\n{path}\n\n"
                "Command-line tools can sometimes fail with these paths. If you experience errors, "
                "please move the relevant files/folders to a simple path (e.g., C:\\OSM_Data) and try again."
            )
            break
    if has_issue:
        return messagebox.askyesno(
            "Continue with Warning?",
            "A potential issue with file paths was detected. This may cause the process to fail.\n\n"
            "Do you want to attempt to continue anyway?"
        )
    return True

def run_matrix_pipeline():
    global session_file_path, master_region_path, unique_pid, resume_list, map_individual_selection, all_tiles_to_process_global
    # Reset session state for a new run.
    with completed_lock:
        resume_list.clear()
    # Generate a unique ID for this run to avoid reusing temp files from previous runs.
    unique_pid = f"session_{int(time.time())}"

    sel_file, out_dir, bin_dir = file_path_var.get().strip(), dest_path_var.get().strip(), util_path_var.get().strip()

    paths_to_check = {
        "OSM Tools Folder": bin_dir,
        "Master OSM Data File": sel_file,
        "OSM Tile Data Output Folder": out_dir
    }
    if not check_for_non_ascii_paths(paths_to_check):
        return

    mode_selection = mode_combo.get()
    if not out_dir:
        messagebox.showerror("Validation Error", "Output parameters folder destination path is missing!"); return
    osmconv, osmfilt = find_tool_in_dir(bin_dir, "osmconvert"), find_tool_in_dir(bin_dir, "osmfilter")

    if mode_selection == "Create Real OSM Data Mesh":
        if not bin_dir or not sel_file:
            messagebox.showerror("Validation Error", "Required path parameters are missing!"); return
        if not os.path.exists(sel_file):
            messagebox.showerror("Execution Error", "Missing target master PBF input asset for real data compile!"); return
        if not os.path.exists(osmconv) or not os.path.exists(osmfilt):
            messagebox.showerror("Utility Error", "Missing osmconvert.exe or osmfilter.exe binaries!"); return

    all_tiles_to_process = []
    is_individual_selection = bool(map_individual_selection)
    if map_individual_selection:
        for tile_id in sorted(list(map_individual_selection)):
            coords = _tile_name_to_lat_lon(tile_id)
            if coords:
                all_tiles_to_process.append((coords[0], coords[1]))
    else:
        try:
            S_LAT, E_LAT = int(lat_s_entry.get().strip()), int(lat_n_entry.get().strip())
            S_LON, E_LON = int(lon_w_entry.get().strip()), int(lon_e_entry.get().strip())
            if S_LAT > E_LAT or S_LON > E_LON:
                messagebox.showerror("Logic Error", "Starting coordinates must be lower than ending limits!"); return
            for lat in range(S_LAT, E_LAT + 1):
                for lon in range(S_LON, E_LON + 1):
                    all_tiles_to_process.append((lat, lon))
        except (ValueError, TypeError):
            messagebox.showerror("Format Error", "Coordinates parameters must use whole integers only and must not be empty!"); return

    all_tiles_to_process_global = all_tiles_to_process

    if not all_tiles_to_process:
        messagebox.showinfo("No Tiles Selected", "There are no tiles in the current selection to process.")
        return

    temp_dir = _get_app_data_dir("Temp")
    session_file_path = os.path.abspath(os.path.join(temp_dir, "osm_session.json"))
    master_region_path = os.path.abspath(os.path.join(temp_dir, f"temp_region_{unique_pid}.o5m"))

    input_frame.pack_forget(); step2_outer_frame.pack_forget(); link_container.pack_forget(); dem_link_container.pack_forget()
    progress_frame.pack(fill='x', expand=True, padx=10, pady=20)
    root.geometry("650x820")
    threading.Thread(target=bg_worker_process, args=(all_tiles_to_process, bin_dir, out_dir, sel_file, osmconv, osmfilt, resume_list, mode_selection, is_individual_selection), daemon=True).start()

def _renumber_osm_ids(input_path, output_path):
    try:
        tree = ET.parse(input_path)
        root = tree.getroot()

        # Map to store (original_id, element_type) -> new_id
        # This ensures uniqueness even if original IDs collide across types.
        new_id_map = {}
        
        # Keep track of new IDs to assign, starting from -1
        current_new_id = -1

        # First pass: Assign new unique IDs to all elements and build the map

        for elem in root:
            if elem.tag not in ('node', 'way', 'relation'): continue
            
            original_id = elem.attrib.get('id')
            
            # Create a unique key for the element based on its type and original ID
            # This handles cases where a node and a way might have the same original ID
            element_key = (elem.tag, original_id) 
            
            # Assign a new unique ID
            new_id_str = str(current_new_id)
            current_new_id -= 1
            
            # Store the mapping from the original key to the new ID
            new_id_map[element_key] = new_id_str
            
            # Update the element's ID attribute in place
            elem.set('id', new_id_str)
            elem.set('version', '1') # Ensure version is set

        # Second pass: Update references (nd ref, member ref)

        for elem in root:
            if elem.tag not in ('node', 'way', 'relation'): continue
            
            if elem.tag == 'way':
                # Create a list of nd elements to remove to avoid modifying while iterating
                nds_to_remove = []
                for nd in elem.findall('nd'):
                    original_ref_id = nd.attrib.get('ref')
                    # A way's 'nd ref' must point to a node.
                    node_key = ("node", original_ref_id)
                    if node_key in new_id_map:
                        nd.set('ref', new_id_map[node_key])
                    else:
                        # If a node reference points to something that isn't a node, or a non-existent ID,
                        # this is an error in the input data or filtering. Remove it.
                        nds_to_remove.append(nd)
                        # print(f"Warning: Removed problematic nd ref='{original_ref_id}' in way id='{elem.attrib.get('id')}' as it does not refer to a known node.", file=sys.stderr)
                # Remove collected invalid nd elements
                for nd in nds_to_remove:
                    elem.remove(nd)

            elif elem.tag == 'relation':
                # Create a list of member elements to remove
                members_to_remove = []
                for member in elem.findall('member'):
                    original_ref_id = member.attrib.get('ref')
                    member_type = member.attrib.get('type') # member type can be node, way, or relation
                    
                    if member_type and (member_type, original_ref_id) in new_id_map:
                        member.set('ref', new_id_map[(member_type, original_ref_id)])
                    else:
                        # If a member reference points to a non-existent element or has no type, remove it.
                        members_to_remove.append(member)
                        # print(f"Warning: Removed problematic member ref='{original_ref_id}' (type='{member_type}') in relation id='{elem.attrib.get('id')}' as it does not refer to a known element.", file=sys.stderr)
                # Remove collected invalid member elements
                for member in members_to_remove:
                    elem.remove(member)
        
        root.set('generator', 'Ortho4XP')
        bounds_elem = root.find('bounds')
        if bounds_elem is not None:
            root.remove(bounds_elem)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
            f.write('<osm version="0.6" generator="Ortho4XP">\n')
            for elem in root:
                if elem.tag not in ('node', 'way', 'relation'): # Skip non-OSM elements like bounds if they somehow remained
                    continue
                
                attr_parts = []
                for k, v_str in sorted(elem.attrib.items()):
                    if k in ('lat', 'lon'):
                        try:
                            v_formatted = f"{float(v_str):.7f}"
                            attr_parts.append(f'{k}="{v_formatted}"')
                        except (ValueError, TypeError):
                            attr_parts.append(f'{k}="{v_str}"')
                    else:
                        attr_parts.append(f'{k}="{v_str}"')
                attrs = ' '.join(attr_parts)

                if not list(elem):
                    f.write(f'  <{elem.tag} {attrs}/>\n')
                else:
                    f.write(f'  <{elem.tag} {attrs}>\n')
                    for child in elem:
                        child_attrs = ' '.join(f'{k}="{v}"' for k, v in sorted(child.attrib.items()))
                        f.write(f'    <{child.tag} {child_attrs}/>\n')
                    f.write(f'  </{elem.tag}>\n')
            f.write('</osm>\n')
        return True, None
    except Exception as e:
        return False, str(e)

def _sanitize_osm_for_ortho4xp(file_path):
    """
    Reads an OSM XML file, replaces special characters (Turkish, Cyrillic, etc.)
    with their ASCII equivalents, and overwrites the file. This is to prevent
    issues with downstream tools that may not handle certain Unicode characters
    correctly.
    """
    # Mapping of potentially problematic Unicode characters to their simpler ASCII equivalents.
    # This covers Turkish, Cyrillic, and common European diacritics.
    char_map = {
        # Turkish
        'İ': 'I', 'ı': 'i',
        'Ş': 'S', 'ş': 's',
        'Ğ': 'G', 'ğ': 'g',
        'Ç': 'C', 'ç': 'c',
        'Ö': 'O', 'ö': 'o',
        'Ü': 'U', 'ü': 'u',

        # Cyrillic (Russian, Ukrainian, etc.) - basic transliteration
        'А': 'A', 'а': 'a',
        'Б': 'B', 'б': 'b',
        'В': 'V', 'в': 'v',
        'Г': 'G', 'г': 'g',
        'Д': 'D', 'д': 'd',
        'Е': 'E', 'е': 'e',
        'Ё': 'E', 'ё': 'e',
        'Ж': 'Zh', 'ж': 'zh',
        'З': 'Z', 'з': 'z',
        'И': 'I', 'и': 'i',
        'Й': 'Y', 'й': 'y',
        'К': 'K', 'к': 'k',
        'Л': 'L', 'л': 'l',
        'М': 'M', 'м': 'm',
        'Н': 'N', 'н': 'n',
        'О': 'O', 'о': 'o',
        'П': 'P', 'п': 'p',
        'Р': 'R', 'р': 'r',
        'С': 'S', 'с': 's',
        'Т': 'T', 'т': 't',
        'У': 'U', 'у': 'u',
        'Ф': 'F', 'ф': 'f',
        'Х': 'Kh', 'х': 'kh',
        'Ц': 'Ts', 'ц': 'ts',
        'Ч': 'Ch', 'ч': 'ch',
        'Ш': 'Sh', 'ш': 'sh',
        'Щ': 'Shch', 'щ': 'shch',
        'Ъ': '', 'ъ': '',
        'Ы': 'Y', 'ы': 'y',
        'Ь': '', 'ь': '',
        'Э': 'E', 'э': 'e',
        'Ю': 'Yu', 'ю': 'yu',
        'Я': 'Ya', 'я': 'ya',
        'Є': 'Ye', 'є': 'ye',
        'І': 'I', 'і': 'i',
        'Ї': 'Yi', 'ї': 'yi',
        'Ґ': 'G', 'ґ': 'g',

        # Common European Diacritics
        'á': 'a', 'Á': 'A', 'à': 'a', 'À': 'A', 'â': 'a', 'Â': 'A', 'ä': 'a', 'Ä': 'A',
        'ã': 'a', 'Ã': 'A', 'å': 'a', 'Å': 'A', 'æ': 'ae', 'Æ': 'AE', 'ç': 'c', 'Ç': 'C',
        'é': 'e', 'É': 'E', 'è': 'e', 'È': 'E', 'ê': 'e', 'Ê': 'E', 'ë': 'e', 'Ë': 'E',
        'í': 'i', 'Í': 'I', 'ì': 'i', 'Ì': 'I', 'î': 'i', 'Î': 'I', 'ï': 'i', 'Ï': 'I',
        'ñ': 'n', 'Ñ': 'N', 'ó': 'o', 'Ó': 'O', 'ò': 'o', 'Ò': 'O', 'ô': 'o', 'Ô': 'O',
        'õ': 'o', 'Õ': 'O', 'ø': 'o', 'Ø': 'O', 'ú': 'u', 'Ú': 'U', 'ù': 'u', 'Ù': 'U',
        'û': 'u', 'Û': 'U', 'ý': 'y', 'Ý': 'Y', 'ÿ': 'y', 'Ÿ': 'Y', 'ß': 'ss',
        'Č': 'C', 'č': 'c', 'Š': 'S', 'š': 's', 'Ž': 'Z', 'ž': 'z', 'Đ': 'D', 'đ': 'd', 'Ł': 'L', 'ł': 'l',
    }

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        if not any(key in content for key in char_map):
            return True, "No special characters found, skipping."

        for special_char, ascii_char in char_map.items():
            content = content.replace(special_char, ascii_char)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return True, "File sanitized successfully."
    except Exception as e:
        return False, f"Failed to sanitize file {file_path}: {e}"

def bg_worker_process(all_tiles, util_dir, storage_dir, selected_file, osmconvert_path, osmfilter_path, resume_list, mode_selection, is_individual_selection=False):
    global unique_pid, active_subprocesses, pool_executor, session_file_path, master_region_path, is_paused
    start_time = time.time()
    t_scratch = _get_app_data_dir("Temp")

    sub_env = os.environ.copy()
    sub_env["TEMP"] = t_scratch
    sub_env["TMP"] = t_scratch

    num_workers = max(1, int(multiprocessing.cpu_count() * 0.75))
    startupinfo = None
    if sys.platform == 'win32':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    total_tiles = len(all_tiles)
    progress_bar["maximum"] = total_tiles
    with completed_lock:
        completed_tiles = len(resume_list)
    failed_osm_tiles = []
    loop_start_time = time.time()


    def process_single_tile_thread(worker_args):
        global unique_pid, active_subprocesses, session_file_path
        (lat_coord, lon_coord), chunk_master_path, custom_env = worker_args
        l_p = "+" if lat_coord >= 0 else "-"
        o_p = "+" if lon_coord >= 0 else "-"
        base_folder_name = f"{l_p}{str(abs(lat_coord)).zfill(2)}{o_p}{str(abs(lon_coord)).zfill(3)}"
        if base_folder_name in resume_list: return "SKIPPED", base_folder_name

        scr_dir = None
        try:
            suffixes = ["_airports.osm", "_big_roads.osm", "_small_roads.osm", "_coastline.osm", "_water.osm"]
            t_lat = (int(lat_coord) // 10) * 10
            t_lon = (int(lon_coord) // 10) * 10
            group_folder_name = f"{'+' if t_lat >= 0 else '-'}{str(abs(t_lat)).zfill(2)}{'+' if t_lon >= 0 else '-'}{str(abs(t_lon)).zfill(3)}"
            tile_folder = os.path.abspath(os.path.join(storage_dir, group_folder_name, base_folder_name))
            os.makedirs(tile_folder, exist_ok=True)
        
            if mode_selection == "Place 1 KB Bypass Holders Only":
                xml_lines = [b"<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6' generator='osmfilter'>\n"]
                for idx in range(65):
                    xml_lines.append(f"<node id='{9000000000+idx}' lat='{float(lat_coord)+0.5}' lon='{float(lon_coord)+0.5}' version='1'/>\n".encode('utf-8'))
                xml_lines.append(b"</osm>")
                dummy_xml = b"".join(xml_lines)
                for suffix in suffixes:
                    final_bz2 = os.path.abspath(os.path.join(tile_folder, f"{base_folder_name}{suffix}.bz2"))
                    if os.path.exists(final_bz2): continue
                    try:
                        with bz2.open(final_bz2, 'wb', compresslevel=3) as f_out: f_out.write(dummy_xml)
                    except: pass
                with completed_lock:
                    if base_folder_name not in resume_list:
                        resume_list.append(base_folder_name)
                return "SUCCESS", base_folder_name
            all_protected = True
            for suffix in suffixes:
                if not (os.path.exists(os.path.join(tile_folder, f"{base_folder_name}{suffix}.bz2")) and os.path.getsize(os.path.join(tile_folder, f"{base_folder_name}{suffix}.bz2")) > 2000):
                    all_protected = False; break
            if all_protected:
                with completed_lock:
                    if base_folder_name not in resume_list: resume_list.append(base_folder_name)
                return "SUCCESS", base_folder_name

            scr_dir = os.path.abspath(os.path.join(t_scratch, f"tscratch_{l_p}{abs(lat_coord)}_{o_p}{abs(lon_coord)}_{unique_pid}"))
            os.makedirs(scr_dir, exist_ok=True)
            loc_tile = os.path.abspath(os.path.join(scr_dir, "temp_tile.osm"))
            cmd_cut = [osmconvert_path, os.path.abspath(chunk_master_path), f"-b={float(lon_coord)},{float(lat_coord)},{float(lon_coord)+1.0},{float(lat_coord)+1.0}", f"-t={os.path.abspath(os.path.join(scr_dir, 'osmconvert_thread.tmp'))}"]
            cmd_cut.extend(["--complete-ways", "--drop-author", "--fake-version", "--emulate-pbf2osm", "--drop-broken-refs", f"-o={loc_tile}"])
            
            log_cut_path = os.path.join(scr_dir, "log_cut.txt")
            p_cut = None
            try:
                with open(log_cut_path, "wb") as log_fh:
                    with subprocess_lock:
                        p_cut = subprocess.Popen(cmd_cut, startupinfo=startupinfo, env=custom_env, stdin=subprocess.DEVNULL, stdout=log_fh, stderr=subprocess.STDOUT, cwd=util_dir)
                        active_subprocesses.append(p_cut)
                    p_cut.wait()
                    with subprocess_lock:
                        try: active_subprocesses.remove(p_cut)
                        except: pass
            except Exception as e:
                print(f"[Tile {base_folder_name}] Failed to launch osmconvert (cut): {e}")
                try: shutil.rmtree(scr_dir, ignore_errors=True)
                except: pass
                return "FAILED", base_folder_name
            except Exception as e: # pragma: no cover
                print(f"[Tile {base_folder_name}] Failed to launch osmconvert (cut): {e}") # pragma: no cover
                try: shutil.rmtree(scr_dir, ignore_errors=True) # pragma: no cover
                except: pass # pragma: no cover
                return "FAILED", base_folder_name # pragma: no cover

            # Check if osmconvert succeeded. A non-zero return code is an error.
            # However, for empty tiles (e.g., all sea), osmconvert might exit non-zero
            # but report "no data". This is an expected outcome, not a failure.
            # The primary success metric is the creation of a non-empty output file.
            # If the file doesn't exist or is empty, we investigate why. This handles cases
            # where older tool versions might fail silently (exit 0) without creating a file.
            if not os.path.exists(loc_tile) or os.path.getsize(loc_tile) == 0:
                log_content = ""
                try:
                    with open(log_cut_path, "r", encoding="utf-8", errors="ignore") as f:
                        log_content = f.read()
                except OSError:
                    pass
                
                # If the tool failed for a reason other than "no data", it's a real error.
                if "no data" not in log_content.lower():
                    print(f"[Tile {base_folder_name}] osmconvert (cut) failed with code {p_cut.returncode}. Log: {log_content}")
                    try: shutil.rmtree(scr_dir, ignore_errors=True)
                    except: pass
                    return "FAILED", base_folder_name
                # If it was a "no data" error, we proceed. The next block will handle the empty file.

            # If osmconvert reported "no data" or produced an empty file for any other reason,
            # we create a minimal, valid OSM file. This ensures that downstream osmfilter
            # processes don't fail and correctly produce empty .bz2 archives for the tile.
            if not os.path.exists(loc_tile) or os.path.getsize(loc_tile) == 0:
                try:
                    with open(loc_tile, "w", encoding="utf-8") as f:
                        f.write("<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6' generator='Ortho_Optimizer_dummy_tile'>\n</osm>\n")
                except OSError as file_err:
                    print(f"[Tile {base_folder_name}] CRITICAL: Failed to create dummy tile file after osmconvert reported no data: {file_err}")
                    try: shutil.rmtree(scr_dir, ignore_errors=True)
                    except: pass
                    return "FAILED", base_folder_name
                # The key indicator of an empty tile is the "no data" message in the log,
                # regardless of the exit code, which can vary between tool versions.
                is_expected_empty_tile = "no data" in log_content.lower()

                if is_expected_empty_tile:
                    # This is the expected case for an empty sea tile. Create a valid dummy file.
                    try:
                        with open(loc_tile, "w", encoding="utf-8") as f:
                            f.write("<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6' generator='Ortho_Optimizer_dummy_tile'>\n</osm>\n")
                    except OSError as file_err: # pragma: no cover
                        print(f"[Tile {base_folder_name}] CRITICAL: Failed to create dummy tile file for empty tile: {file_err}") # pragma: no cover
                        try: shutil.rmtree(scr_dir, ignore_errors=True) # pragma: no cover
                        except: pass # pragma: no cover
                        return "FAILED", base_folder_name # pragma: no cover
                else:
                    # The file is missing, but the log does not indicate it was an empty tile. This is a real failure.
                    print(f"[Tile {base_folder_name}] osmconvert (cut) failed. Output file was not created and log did not report 'no data'.") # pragma: no cover
                    print(f"Return code: {p_cut.returncode}. Log snippet: {log_content[-500:]}") # pragma: no cover
                    try: shutil.rmtree(scr_dir, ignore_errors=True) # pragma: no cover
                    except: pass # pragma: no cover
                    return "FAILED", base_folder_name # pragma: no cover

            filters = {
                "_airports.osm": 'aeroway=airport =aerodrome =apron =runway =taxiway =helipad',
                "_big_roads.osm": 'highway=motorway =motorway_link =trunk =trunk_link =primary =primary_link =secondary =secondary_link',
                "_small_roads.osm": 'highway=tertiary =tertiary_link =unclassified =residential',
                "_coastline.osm": 'natural=coastline boundary=administrative maritime=yes place=sea water=sea',
                "_water.osm": 'natural=water water=polygon =lake =river =reservoir waterway=riverbank =dock'
            }
            for suffix, query in filters.items():
                final_bz2 = os.path.abspath(os.path.join(tile_folder, f"{base_folder_name}{suffix}.bz2"))
                if os.path.exists(final_bz2) and os.path.getsize(final_bz2) > 2000: continue
                r_out = os.path.abspath(os.path.join(scr_dir, f"raw_{suffix}"))
                temp_file_prefix = f"osmfilter_{base_folder_name}_{unique_pid}"
                p_file = os.path.abspath(os.path.join(t_scratch, f"filter_args_global_{suffix}_{base_folder_name}.txt"))
                with open(p_file, "w", encoding="utf-8") as pf: pf.write(f"--keep={query} --keep-ways-from-relations --keep-nodes-from-ways\n")
                cmd_filt = [osmfilter_path, loc_tile, "--parameter-file=" + p_file, f"-t={temp_file_prefix}", f"-o={r_out}"]
                
                log_filt_path = os.path.join(scr_dir, f"log_filter_{suffix}.txt")
                p_filt = None
                try:
                    with open(log_filt_path, "wb") as log_fh:
                        with subprocess_lock:
                            p_filt = subprocess.Popen(cmd_filt, startupinfo=startupinfo, env=custom_env, stdin=subprocess.DEVNULL, stdout=log_fh, stderr=subprocess.STDOUT, cwd=util_dir)
                            active_subprocesses.append(p_filt)
                        p_filt.wait()
                        with subprocess_lock:
                            try: active_subprocesses.remove(p_filt)
                            except: pass
                except (OSError, ValueError) as e:
                    print(f"[Tile {base_folder_name}] Failed to launch osmfilter for {suffix}: {e}")
                    return "FAILED", base_folder_name
            
                if not p_filt or p_filt.returncode != 0:
                    output_text = ""
                    try:
                        with open(log_filt_path, "r", encoding='utf-8', errors='replace') as f:
                            output_text = f.read().strip()
                    except OSError:
                        pass
                    print(f"[Tile {base_folder_name}] osmfilter ({suffix}) failed. Code: {p_filt.returncode if p_filt else 'N/A'}. Output:\n{output_text}")
                    try: shutil.rmtree(scr_dir, ignore_errors=True)
                    except: pass
                    return "FAILED", base_folder_name
                try: os.remove(p_file)
                except: pass

                current_source_file = r_out
                temp_files_to_delete = []

                if not os.path.exists(current_source_file) or os.path.getsize(current_source_file) == 0:
                    with open(current_source_file, "w", encoding="utf-8") as f: f.write("<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6' generator='osmfilter'>\n</osm>\n")

                # Sanitize file for special characters before re-numbering
                sanitized_ok, sanitize_msg = _sanitize_osm_for_ortho4xp(current_source_file)
                if not sanitized_ok:
                    # If sanitization fails, it's a file I/O error, which is serious.
                    print(f"[Tile {base_folder_name}] CRITICAL: {sanitize_msg}")
                    try: shutil.rmtree(scr_dir, ignore_errors=True)
                    except: pass
                    return "FAILED", base_folder_name

                renumbered_source_file = os.path.abspath(os.path.join(scr_dir, f"renumbered_{suffix}"))
                success, error_msg = _renumber_osm_ids(current_source_file, renumbered_source_file)

                if success:
                    source_for_compression = renumbered_source_file
                    temp_files_to_delete.append(current_source_file)
                else:
                    print(f"[Tile {base_folder_name}] XML re-numbering failed for {suffix}, compressing original. Error: {error_msg}")
                    source_for_compression = current_source_file

                try:
                    with open(source_for_compression, 'rb') as f_in, bz2.open(final_bz2, 'wb', compresslevel=6) as f_out:
                        shutil.copyfileobj(f_in, f_out)
                except Exception as e:
                    print(f"[Tile {base_folder_name}] Final compression failed for {suffix}: {e}")
            
                temp_files_to_delete.append(source_for_compression)
                for f_path in set(temp_files_to_delete):
                    if os.path.exists(f_path):
                        try: os.remove(f_path)
                        except: pass

            try: shutil.rmtree(scr_dir, ignore_errors=True)
            except: pass
            with completed_lock:
                if base_folder_name not in resume_list: resume_list.append(base_folder_name)
            gc.collect(); return "SUCCESS", base_folder_name
        except OSError as tile_err:
            if scr_dir:
                try: shutil.rmtree(scr_dir, ignore_errors=True)
                except: pass
            print(f"[Tile {base_folder_name}] Temp/file access error - marking FAILED: {tile_err}")
            return "FAILED", base_folder_name
    
    # If it's an individual (potentially non-contiguous) selection, we process each tile as its own chunk
    # to avoid creating a massive intermediate data file from a huge bounding box.
    if mode_selection == "Create Real OSM Data Mesh" and is_individual_selection:
        chunk_count = total_tiles
    elif total_tiles < 500: chunk_count = 1
    elif total_tiles < 1500: chunk_count = 3
    elif total_tiles < 3500: chunk_count = 5
    else: chunk_count = 10
    c_size = max(1, -(-total_tiles // chunk_count))
    t_chunks = [all_tiles[i:i + c_size] for i in range(0, total_tiles, c_size)]

    for chunk_idx, current_chunk in enumerate(t_chunks):
        chunk_ready = True
        for c_lat, c_lon in current_chunk:
            t_chk = f"{'+' if c_lat >= 0 else '-'}{str(abs(c_lat)).zfill(2)}{'+' if c_lon >= 0 else '-'}{str(abs(c_lon)).zfill(3)}"
            if t_chk not in resume_list: chunk_ready = False; break
        if chunk_ready: completed_tiles = len(resume_list); continue
        if mode_selection == "Create Real OSM Data Mesh":
            c_lats = [lat for lat, lon in current_chunk]
            c_lons = [lon for lat, lon in current_chunk]
            chunk_master_path = os.path.abspath(os.path.join(t_scratch, f"temp_region_{unique_pid}_chunk{chunk_idx}.o5m"))

            try:
                os.makedirs(t_scratch, exist_ok=True)
            except OSError as dir_err:
                error_message = (f"FATAL: Could not access the Temp scratch folder:\n{t_scratch}\n\n"
                                 f"Details: {dir_err}\n\n"
                                 "This is usually caused by antivirus/cloud-sync locking the folder, "
                                 "or insufficient permissions. Skipping this chunk.")
                root.after(0, lambda msg=error_message: (status_var.set(msg), messagebox.showerror("Temp Folder Access Error", msg)))
                continue

            try:
                chunk_already_cut = os.path.exists(chunk_master_path) and os.path.getsize(chunk_master_path) > 0
            except OSError:
                chunk_already_cut = False

            if chunk_already_cut:
                pass
            else:
                try:
                    for stale_name in os.listdir(t_scratch):
                        if stale_name.startswith(f"temp_region_{unique_pid}_chunk") and stale_name != os.path.basename(chunk_master_path):
                            try: os.remove(os.path.join(t_scratch, stale_name))
                            except OSError: pass
                except OSError:
                    pass
                def _build_cmd_master(include_tempfile):
                    cmd = [osmconvert_path, os.path.abspath(selected_file), f"-b={chunk_bbox}"]
                    if include_tempfile:
                        osmconvert_temp_path = os.path.abspath(os.path.join(t_scratch, f"osmconvert_master_temp_{chunk_idx}.tmp"))
                        cmd.append(f"-t={osmconvert_temp_path}")
                    cmd.extend(["--complete-ways", "--drop-author", "--drop-version", f"-o={os.path.abspath(chunk_master_path)}"])
                    return cmd

                def _run_cmd_master(cmd, attempt_idx):
                    log_path = os.path.abspath(os.path.join(t_scratch, f"osmconvert_master_chunk{chunk_idx}_log{attempt_idx}.txt"))
                    log_fh = None
                    try:
                        with subprocess_lock:
                            log_fh = open(log_path, "wb")
                            p = subprocess.Popen(cmd, startupinfo=startupinfo, env=sub_env, stdout=log_fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, cwd=util_dir)
                            active_subprocesses.append(p)
                        m_start = time.time()
                        while p.poll() is None:
                            status_text = f"Package {chunk_idx + 1}/{len(t_chunks)} Scan... [Elapsed: {int(time.time() - m_start)}s]"
                            root.after(0, lambda s=status_text: status_var.set(s))
                            time.sleep(0.5)
                        with subprocess_lock:
                            try: active_subprocesses.remove(p)
                            except: pass
                    finally:
                        try:
                            if log_fh: log_fh.close()
                        except: pass
                    output_text = ""
                    try:
                        with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                            output_text = lf.read().strip()
                    except OSError:
                        pass
                    try: os.remove(log_path)
                    except OSError: pass
                    return p, output_text

                chunk_bbox = f"{int(min(c_lons))},{int(min(c_lats))},{int(max(c_lons))+1},{int(max(c_lats))+1}"
                try:
                    proc, tool_output = _run_cmd_master(_build_cmd_master(True), 1)
                except OSError as launch_err:
                    error_message = (f"FATAL: Could not launch osmconvert for data chunk {chunk_idx + 1}.\n\n"
                                     f"Details: {launch_err}\n\nSkipping this chunk.")
                    root.after(0, lambda msg=error_message: (status_var.set(msg), messagebox.showerror("OSM Chunking Error", msg)))
                    continue

                if proc.returncode != 0:
                    tool_output_snippet = tool_output[-1500:] if tool_output else "(osmconvert produced no console output - this points to the process being killed, e.g. out of memory, rather than a reported error.)"
                    error_message = (f"FATAL: osmconvert failed to create data chunk {chunk_idx + 1} (exit code {proc.returncode}).\n\n"
                                     f"--- osmconvert output ---\n{tool_output_snippet}\n--- end output ---\n\n"
                                     "Common causes:\n"
                                     "1. A corrupt or inaccessible .pbf file.\n"
                                     "2. Non-English (non-ASCII) characters in the file path.\n"
                                     "3. The Temp scratch folder being locked/inaccessible.\n"
                                     "4. Out of memory/disk space cutting a large region from a big .pbf.\n\nSkipping this chunk.")
                    root.after(0, lambda msg=error_message: (status_var.set(msg), messagebox.showerror("OSM Chunking Error", msg)))
                    try:
                        if os.path.exists(chunk_master_path):
                            os.remove(chunk_master_path)
                    except OSError: pass
                    continue

                time.sleep(0.5)
        
        worker_args = [(coords, chunk_master_path if mode_selection == "Create Real OSM Data Mesh" else "", sub_env) for coords in current_chunk]
        pool_executor = ThreadPoolExecutor(max_workers=num_workers if mode_selection == "Create Real OSM Data Mesh" else max(4, num_workers))
        
        for status, tile_name in pool_executor.map(process_single_tile_thread, worker_args):
            if status == "FAILED":
                failed_osm_tiles.append(tile_name)
            with completed_lock:
                completed_tiles = len(resume_list)
            rem_t = total_tiles - completed_tiles; l_elap = int(time.time() - loop_start_time)
            avg_t = l_elap / completed_tiles if completed_tiles > 0 else 0.0
            raw_etc = int(rem_t * (avg_t / num_workers)) if mode_selection == "Create Real OSM Data Mesh" else int(rem_t * 0.0001)
            status_text = f"Package {chunk_idx + 1}/{len(t_chunks)} | Compiling: {tile_name}"
            metrics_text = f"Completed: {completed_tiles} | Remaining: {rem_t} | Total: {total_tiles}\nElapsed: {l_elap // 60}m {l_elap % 60}s | Avg/Tile: {round(avg_t, 2)}s\nETC: {raw_etc // 60}m {raw_etc % 60}s"
            root.after(0, lambda s=status_text, m=metrics_text, p=completed_tiles: (status_var.set(s), metrics_var.set(m), progress_bar.config(value=p)))
        pool_executor.shutdown(wait=True)        
        _save_osm_session_file()
        gc.collect()
    root.after(0, lambda: _handle_bg_worker_completion(total_tiles, loop_start_time, failed_osm_tiles))

root = tk.Tk(); root.title("Ortho4XP Vector & Batch Helper"); root.minsize(780, 500)

style = ttk.Style(root)
is_dark = is_windows_dark_mode()
if is_dark:
    dark_bg = "#2b2b2b"
    dark_fg = "#dcdcdc"
    dark_select_bg = "#4b4b4b"
    dark_select_fg = "white"
    
    style.configure("Success.TButton", background="#27ae60", foreground="white")
    style.map("Success.TButton", background=[('active', '#2ecc71')])
    style.configure("Warning.TButton", background="#f39c12", foreground="white")
    style.map("Warning.TButton", background=[('active', '#f1c40f')])
    style.configure("Danger.TButton", background="#c0392b", foreground="white")
    style.map("Danger.TButton", background=[('active', '#e74c3c')])
    style.configure("Save.TButton", background="#d35400", foreground="white")
    style.map("Save.TButton", background=[('active', '#e67e22')])
    style.configure("LightSuccess.TButton", background="#81c784", foreground="black")
    style.map("LightSuccess.TButton", background=[('active', '#a5d6a7')])
    style.configure("LightDanger.TButton", background="#e57373", foreground="black")
    style.map("LightDanger.TButton", background=[('active', '#ef9a9a')])

    root.configure(bg=dark_bg)
    style.theme_use('clam')
    style.configure('.', background=dark_bg, foreground=dark_fg, fieldbackground=dark_select_bg, selectbackground=dark_select_bg, selectforeground=dark_select_fg, troughcolor=dark_select_bg)
    style.configure("TFrame", background=dark_bg)
    style.configure("TLabel", background=dark_bg, foreground=dark_fg)
    style.configure("TCheckbutton", background=dark_bg, foreground=dark_fg)
    style.configure("TRadiobutton", background=dark_bg, foreground=dark_fg)
    style.configure("TLabelframe", background=dark_bg, bordercolor="#555555")
    style.configure("TLabelframe.Label", background=dark_bg, foreground=dark_fg)
    style.map('TCombobox', fieldbackground=[('readonly', dark_select_bg)])
    style.map('TCombobox', selectbackground=[('readonly', dark_select_bg)])
    style.map('TCombobox', selectforeground=[('readonly', dark_select_fg)])
else:
    try:
        # Use 'clam' on Windows to ensure custom button colors are applied.
        # The default 'vista' theme ignores background color settings for buttons.
        if sys.platform == "win32":
            style.theme_use('clam')
        elif sys.platform == "darwin": style.theme_use('aqua')
        else: style.theme_use('clam')
    except tk.TclError:
        style.theme_use('default')
    style.configure("Success.TButton", background="#2ecc71", foreground="white")
    style.map("Success.TButton", background=[('active', '#27ae60')])
    style.configure("Warning.TButton", background="#f39c12", foreground="white")
    style.map("Warning.TButton", background=[('active', '#f1c40f')])
    style.configure("Danger.TButton", background="#e74c3c", foreground="white")
    style.map("Danger.TButton", background=[('active', '#c0392b')])
    style.configure("Save.TButton", background="#d35400", foreground="white")
    style.map("Save.TButton", background=[('active', '#e67e22')])
    style.configure("LightSuccess.TButton", background="#66bb6a", foreground="white")
    style.map("LightSuccess.TButton", background=[('active', '#4caf50')])
    style.configure("LightDanger.TButton", background="#ef5350", foreground="white")
    style.map("LightDanger.TButton", background=[('active', '#e53935')])


container = ttk.Frame(root)
canvas = tk.Canvas(container, highlightthickness=0)
scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
scrollable_frame = ttk.Frame(canvas)

scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)
if is_dark:
    canvas.configure(bg=dark_bg)

container.pack(fill="both", expand=True)
canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

def _on_mousewheel(event):
    scroll_speed = -1 if sys.platform == 'darwin' else int(-1*(event.delta/120))
    canvas.yview_scroll(scroll_speed, "units")
root.bind_all("<MouseWheel>", _on_mousewheel)

root.protocol("WM_DELETE_WINDOW", on_close_requested)
file_path_var, dest_path_var, util_path_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
ortho4xp_exe_var, ortho_imagery_var, ortho_zl_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
ortho4xp_output_var, ortho4xp_overlay_var = tk.StringVar(), tk.StringVar()
ot_api_key_var = tk.StringVar()
ortho_dem_choice_var = tk.StringVar(value="Default (Viewfinderpanoramas.org)")
ortho_dem_custom_path_var = tk.StringVar()
auto_run_ortho_var = tk.BooleanVar(value=False) # This variable is still used for auto-starting Step 2
for var in (util_path_var, file_path_var, dest_path_var, ortho4xp_exe_var, ortho4xp_output_var, ot_api_key_var, ortho_imagery_var, ortho_zl_var, ortho_dem_choice_var, ortho_dem_custom_path_var, auto_run_ortho_var, ortho4xp_overlay_var):
    var.trace_add("write", lambda *args: save_last_paths_checkpoint())
dest_path_var.trace_add("write", lambda *a: scan_osm_output_dir_async())
ortho4xp_output_var.trace_add("write", lambda *a: scan_ortho_output_dir_async())
input_frame = ttk.Frame(scrollable_frame); input_frame.pack(fill='x', expand=True, padx=10, pady=5)
input_frame.grid_columnconfigure(1, weight=1)
input_frame.grid_columnconfigure(2, weight=0)

ttk.Label(input_frame, text="Step 1: OSM Data Processing", font=("Arial", 11, "bold")).grid(row=0, column=0, columnspan=3, sticky='w', pady=(4, 8))
ttk.Label(input_frame, text="Target Region Preset:").grid(row=1, column=0, pady=6, sticky='w')
preset_combo = ttk.Combobox(input_frame, values=list(PRESETS.keys()), width=40, state="readonly"); preset_combo.grid(row=1, column=1, padx=10, pady=6, sticky='w')
preset_combo.bind("<<ComboboxSelected>>", on_preset_change)
preset_combo.bind("<<ComboboxSelected>>", lambda e: save_last_paths_checkpoint())

ttk.Label(input_frame, text="OSM Output Mode:").grid(row=2, column=0, pady=6, sticky='w')
mode_combo = ttk.Combobox(input_frame, values=["Place 1 KB Bypass Holders Only", "Create Real OSM Data Mesh"], width=40, state="readonly"); mode_combo.grid(row=2, column=1, padx=10, pady=6, sticky='w')
mode_combo.bind("<<ComboboxSelected>>", toggle_mode_widgets)
ttk.Label(input_frame, text="Coordinates must be whole numbers (e.g., 27 or -35).", font=("Arial", 8, "italic")).grid(row=3, column=0, columnspan=3, pady=(8, 2), sticky='w')
ttk.Label(input_frame, text="Start Latitude (South):").grid(row=4, column=0, pady=4, sticky='w')
lat_s_entry = ttk.Entry(input_frame, width=15); lat_s_entry.grid(row=4, column=1, padx=10, pady=4, sticky='w')
ttk.Label(input_frame, text="End Latitude (North):").grid(row=5, column=0, pady=4, sticky='w')
lat_n_entry = ttk.Entry(input_frame, width=15); lat_n_entry.grid(row=5, column=1, padx=10, pady=4, sticky='w')
ttk.Button(input_frame, text="\U0001F5FA Show Map Selector", command=open_map_window, width=20).grid(row=5, column=1, padx=145, pady=4, sticky='w')
ttk.Label(input_frame, text="Start Longitude (West):").grid(row=6, column=0, pady=4, sticky='w')
lon_w_entry = ttk.Entry(input_frame, width=15); lon_w_entry.grid(row=6, column=1, padx=10, pady=4, sticky='w')
ttk.Label(input_frame, text="End Longitude (East):").grid(row=7, column=0, pady=4, sticky='w')
lon_e_entry = ttk.Entry(input_frame, width=15); lon_e_entry.grid(row=7, column=1, padx=10, pady=4, sticky='w')
ttk.Label(input_frame, text="OSM Tools Folder:").grid(row=8, column=0, pady=6, sticky='w')
util_entry = ttk.Entry(input_frame, textvariable=util_path_var, width=43); util_entry.grid(row=8, column=1, padx=10, pady=6, sticky='ew')
util_btn_frame = ttk.Frame(input_frame)
util_btn_frame.grid(row=8, column=2, padx=(6, 0), pady=6, sticky='w')
ttk.Button(util_btn_frame, text="Browse...", command=browse_utils, width=8).pack(side='left')
ttk.Button(util_btn_frame, text="Open", command=lambda: open_path_in_explorer(util_path_var), width=6).pack(side='left', padx=(4, 0))
ttk.Label(input_frame, text="Master OSM Data File (.pbf):").grid(row=9, column=0, pady=6, sticky='w')
pbf_entry = ttk.Entry(input_frame, textvariable=file_path_var, width=43); pbf_entry.grid(row=9, column=1, padx=10, pady=6, sticky='ew')
pbf_btn_frame = ttk.Frame(input_frame)
pbf_btn_frame.grid(row=9, column=2, padx=(6, 0), pady=6, sticky='w')
ttk.Button(pbf_btn_frame, text="Browse...", command=browse_file, width=8).pack(side='left')
ttk.Button(pbf_btn_frame, text="Open", command=lambda: open_path_in_explorer(file_path_var), width=6).pack(side='left', padx=(4, 0))
ttk.Label(input_frame, text="OSM Tile Data Output Folder:").grid(row=10, column=0, pady=6, sticky='w')
ttk.Entry(input_frame, textvariable=dest_path_var, width=43).grid(row=10, column=1, padx=10, pady=6, sticky='ew')
dest_btn_frame = ttk.Frame(input_frame)
dest_btn_frame.grid(row=10, column=2, padx=(6, 0), pady=6, sticky='w')
ttk.Button(dest_btn_frame, text="Browse...", command=browse_destination, width=8).pack(side='left')
ttk.Button(dest_btn_frame, text="Open", command=lambda: open_path_in_explorer(dest_path_var), width=6).pack(side='left', padx=(4, 0))
ttk.Checkbutton(input_frame, text="Automatically start Step 2 (Ortho4XP Batch) after Step 1 completes", variable=auto_run_ortho_var).grid(row=11, column=0, columnspan=3, sticky='w', padx=4, pady=(6,0))
action_frame = ttk.Frame(input_frame)
action_frame.grid(row=12, column=0, columnspan=3, pady=10, sticky='w')
btn_run = ttk.Button(action_frame, text="Step 1: Create/Update OSM Data", command=run_matrix_pipeline, style="LightSuccess.TButton", width=38)
btn_run.pack(side='left', padx=(0, 10))
ttk.Button(action_frame, text="Clean Up OSM Data", command=cleanup_osm_data, style="LightDanger.TButton").pack(side='left', padx=(0, 10))

step2_outer_frame = ttk.Frame(scrollable_frame)
step2_outer_frame.pack(fill='x', expand=True, padx=10, pady=5)
ttk.Label(step2_outer_frame, text="Step 2: Ortho4XP Integration", font=("Arial", 11, "bold")).pack(anchor='w', pady=(4, 8))
ortho_frame = ttk.LabelFrame(step2_outer_frame, text="")
ortho_frame.pack(fill='x', expand=True)
ortho_frame.grid_columnconfigure(1, weight=1)

ortho_frame.grid_columnconfigure(2, weight=0) # Ensure column 2 does not expand

# Row 0: Ortho4XP.exe Location
ttk.Label(ortho_frame, text="Ortho4XP.exe Location:").grid(row=0, column=0, padx=8, pady=4, sticky='w')
exe_field_frame = ttk.Frame(ortho_frame)
exe_field_frame.grid(row=0, column=1, padx=10, pady=4, sticky='ew')
ortho_exe_entry = ttk.Entry(exe_field_frame, textvariable=ortho4xp_exe_var); ortho_exe_entry.pack(side='left', fill='x', expand=True)
ttk.Button(exe_field_frame, text="Browse...", command=browse_ortho4xp_exe, width=8).pack(side='left', padx=(6, 0))
ttk.Button(exe_field_frame, text="Open", command=lambda: open_path_in_explorer(ortho4xp_exe_var), width=6).pack(side='left', padx=(4, 0))

# Row 1: Ortho4XP Tile Output Folder
ttk.Label(ortho_frame, text="Ortho4XP Tile Output Folder: (Required for Batch)").grid(row=1, column=0, padx=8, pady=4, sticky='w')
output_field_frame = ttk.Frame(ortho_frame)
output_field_frame.grid(row=1, column=1, padx=10, pady=4, sticky='ew')
ortho_output_entry = ttk.Entry(output_field_frame, textvariable=ortho4xp_output_var); ortho_output_entry.pack(side='left', fill='x', expand=True)
ttk.Button(output_field_frame, text="Browse...", command=browse_ortho4xp_output, width=8).pack(side='left', padx=(6, 0))
ttk.Button(output_field_frame, text="Open", command=lambda: open_path_in_explorer(ortho4xp_output_var), width=6).pack(side='left', padx=(4, 0))
ttk.Label(ortho_frame, text="Finished Ortho4XP tiles will be moved here. Defaults to Ortho4XP's current setting.", font=("Arial", 8, "italic")).grid(row=2, column=0, columnspan=3, padx=8, pady=(0, 4), sticky='w')

# Row 3: Overlay folder
ttk.Label(ortho_frame, text="Ortho4XP Overlay Folder:").grid(row=3, column=0, padx=8, pady=4, sticky='w') # row 3
overlay_field_frame = ttk.Frame(ortho_frame)
overlay_field_frame.grid(row=3, column=1, padx=10, pady=4, sticky='ew')
ortho_overlay_entry = ttk.Entry(overlay_field_frame, textvariable=ortho4xp_overlay_var); ortho_overlay_entry.pack(side='left', fill='x', expand=True)
ttk.Button(overlay_field_frame, text="Browse...", command=browse_ortho4xp_overlay, width=8).pack(side='left', padx=(6, 0))
ttk.Button(overlay_field_frame, text="Open", command=lambda: open_path_in_explorer(ortho4xp_overlay_var), width=6).pack(side='left', padx=(4, 0))
ttk.Label(ortho_frame, text="Ortho4XP will look for custom overlays here. Defaults to Ortho4XP's current setting.", font=("Arial", 8, "italic")).grid(row=4, column=0, columnspan=3, padx=8, pady=(0, 4), sticky='w')

ttk.Label(ortho_frame, text="Imagery Provider:").grid(row=5, column=0, padx=8, pady=4, sticky='w'); # row 5
ortho_imagery_combo = ttk.Combobox(ortho_frame, textvariable=ortho_imagery_var, width=15); ortho_imagery_combo.grid(row=5, column=1, padx=10, pady=4, sticky='w') # row 5
ttk.Label(ortho_frame, text="e.g. BI=Bing, GO2=Google. Or type your own provider code.", font=("Arial", 8, "italic")).grid(row=6, column=0, columnspan=2, padx=8, pady=(0, 4), sticky='w') # row 6
ttk.Label(ortho_frame, text="Zoom Level (ZL):").grid(row=7, column=0, padx=8, pady=4, sticky='w') # row 7
ortho_zl_combo = ttk.Combobox(ortho_frame, textvariable=ortho_zl_var, values=ORTHO4XP_ZL_CHOICES, width=15); ortho_zl_combo.grid(row=7, column=1, padx=10, pady=4, sticky='w') # row 7
ttk.Label(ortho_frame, text="Elevation Data Source (DEM):").grid(row=8, column=0, padx=8, pady=4, sticky='w') # row 8
ortho_dem_combo = ttk.Combobox(ortho_frame, textvariable=ortho_dem_choice_var, values=ORTHO4XP_DEM_CHOICES, width=25, state='readonly'); ortho_dem_combo.grid(row=8, column=1, padx=10, pady=4, sticky='w') # row 8
ortho_dem_combo.bind("<<ComboboxSelected>>", on_dem_choice_change) # row 8
ortho_dem_path_label = ttk.Label(ortho_frame, text="(using Ortho4XP's default elevation data)", font=("Arial", 8, "italic")) # row 9
ortho_dem_path_label.grid(row=9, column=0, columnspan=2, padx=8, pady=(0, 4), sticky='w') # row 9

ttk.Label(ortho_frame, text="OpenTopography API Key:").grid(row=10, column=0, padx=8, pady=4, sticky='w') # row 10
ot_api_key_entry = ttk.Entry(ortho_frame, textvariable=ot_api_key_var, width=43)
ot_api_key_entry.grid(row=10, column=1, padx=10, pady=4, sticky='w') # row 10

ttk.Label(ortho_frame, text="This tool automates Ortho4XP. Use 'Step 1' for standalone OSM data.", font=("Arial", 8, "italic")).grid(row=11, column=0, columnspan=3, padx=8, pady=(4, 6), sticky='w') # row 11
ortho_btn_holder = ttk.Frame(ortho_frame); ortho_btn_holder.grid(row=12, column=0, columnspan=3, padx=8, pady=8, sticky='w') # row 12
ttk.Button(ortho_btn_holder, text="Test Single Tile", command=test_ortho4xp_single_tile, width=16).pack(side='left', padx=(0, 8))
ttk.Button(ortho_btn_holder, text="Build Batch", command=run_ortho4xp_batch, style="LightSuccess.TButton").pack(side='left', padx=(0, 8))
ttk.Button(ortho_btn_holder, text="Clean Tiles", command=cleanup_selected_tile_batch, style="LightDanger.TButton").pack(side='left', padx=(0, 8))
ttk.Button(ortho_btn_holder, text="Clear Temp/Cache", command=cleanup_app_temp_folder, style="LightDanger.TButton").pack(side='left', padx=(0, 8))
ttk.Button(ortho_btn_holder, text="Sync Setting to Ortho4XP", command=manual_sync_with_ortho4xp, width=22).pack(side='left', padx=(8, 0))
ttk.Button(ortho_btn_holder, text="Global Settings", command=open_ortho4xp_global_settings_window, width=15).pack(side='left', padx=(8, 0))

ortho_progress_frame = ttk.Frame(scrollable_frame)
ortho_status_var, ortho_metrics_var = tk.StringVar(), tk.StringVar()
ortho_status_var.set("Status: Awaiting Ortho4XP batch start..."); ortho_metrics_var.set("Completed: 0  |  Remaining: 0  |  Total Tiles: 0")
ttk.Label(ortho_progress_frame, textvariable=ortho_status_var, font=("Arial", 10, "bold")).pack(anchor='w', pady=(5,0))
ortho_progress_bar = ttk.Progressbar(ortho_progress_frame, orient="horizontal", length=530, mode="determinate"); ortho_progress_bar.pack(fill='x', pady=5)
ttk.Label(ortho_progress_frame, textvariable=ortho_metrics_var, font=("Arial", 9, "italic")).pack(anchor='w', pady=(0,5))
ortho_log_text = scrolledtext.ScrolledText(ortho_progress_frame, height=15, wrap=tk.WORD)
ortho_log_text.pack(fill='both', expand=True, pady=5)
if is_dark:
    ortho_log_text.configure(bg=dark_select_bg, fg=dark_fg)
ortho_btn_container = ttk.Frame(ortho_progress_frame); ortho_btn_container.pack(pady=5)
ortho_btn_pause = ttk.Button(ortho_btn_container, text="Pause Ortho4XP Batch", command=trigger_ortho4xp_pause, style="Warning.TButton", width=25); ortho_btn_pause.pack(side='left', padx=10)
ortho_btn_resume = ttk.Button(ortho_btn_container, text="Resume Ortho4XP Batch", command=trigger_ortho4xp_resume, style="Success.TButton", width=25)

progress_frame = ttk.Frame(scrollable_frame); status_var, metrics_var = tk.StringVar(), tk.StringVar(); status_var.set("Status: Awaiting execution initialization..."); metrics_var.set("Completed: 0  |  Remaining: 0  |  Total Tiles: 0")
ttk.Label(progress_frame, textvariable=status_var, font=("Arial", 10, "bold")).pack(anchor='w', pady=5); progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", length=530, mode="determinate"); progress_bar.pack(fill='x', pady=10)
ttk.Label(progress_frame, textvariable=metrics_var, font=("Arial", 9, "italic")).pack(anchor='w', pady=5)
link_container = ttk.Frame(scrollable_frame); link_container.pack(fill='x', expand=True, padx=10, pady=(5,0))
link_label = ttk.Label(link_container, text="Download master .pbf data from Geofabrik", font=("Arial", 9, "underline"), foreground="#3498db", cursor="hand2")
link_label.pack(anchor='w')
link_label.bind("<Button-1>", open_geofabrik_link)
dem_link_container = ttk.Frame(scrollable_frame); dem_link_container.pack(fill='x', expand=True, padx=10, pady=(0,5)); 
dem_link_label = ttk.Label(dem_link_container, text="Download high-resolution DEM from OpenTopography (for custom DEM file)", font=("Arial", 9, "underline"), foreground="#3498db", cursor="hand2")
dem_link_label.pack(anchor='w')
dem_link_label.bind("<Button-1>", open_opentopo_link)
ttk.Label(dem_link_container, text="Note: Required dependencies (Python, Pillow, osmconvert, osmfilter) are installed automatically on first run.", font=("Arial", 8, "italic")).pack(anchor='w', pady=(5,0))

ttk.Label(root, text="add by Ahmed Qanadeely", font=("Arial", 7, "italic")).place(relx=1.0, rely=1.0, anchor='se', x=-10, y=-2)

# --- Application Startup Sequence ---

if not os.path.exists(get_app_state_path()):
    found_exe = find_ortho4xp_dynamically()
    if found_exe:
        ortho4xp_exe_var.set(found_exe)

sync_ortho4xp_defaults_from_cfg()
saved_state = load_startup_preferences()

check_and_install_dependencies()

# Moved these calls here to ensure ortho4xp_exe_var is set from preferences first
# If we reach here, it means all dependencies were already present.
# So we can safely import them for the current session.
from PIL import Image, ImageTk
if not hasattr(Image, 'LANCZOS'):
    try: Image.LANCZOS = Image.Resampling.LANCZOS
    except AttributeError: Image.LANCZOS = Image.ANTIALIAS
sync_ortho4xp_defaults_from_cfg()
update_ortho4xp_providers_list() # Explicitly call after loading preferences

if not saved_state and not ortho4xp_exe_var.get():
    preset_combo.set("CUSTOM RANGE (MANUAL)")
    mode_combo.current(1)
    on_preset_change(None)
    toggle_mode_widgets(None)

run_startup_map_cache_prefetch_async(root)
scan_xplane_ortho_tiles_async()
scan_osm_output_dir_async()
scan_ortho_output_dir_async()
root.after(250, check_error_queue)
root.bind("<F11>", toggle_main_fullscreen)
root.bind("<Escape>", lambda e: root.attributes("-fullscreen", False))
# Auto-adjust main window size on startup
scrollable_frame.update_idletasks()
req_h = scrollable_frame.winfo_reqheight()
req_w = scrollable_frame.winfo_reqwidth()
# Add some padding for window chrome, etc.
final_h = req_h + 40
final_w = req_w + 40
# Don't exceed 90% of screen height
max_h = int(root.winfo_screenheight() * 0.9)
max_w = int(root.winfo_screenwidth() * 0.9)
final_h = min(final_h, max_h)
final_w = min(final_w, max_w)
root.geometry(f"{final_w}x{final_h}")
root.mainloop()