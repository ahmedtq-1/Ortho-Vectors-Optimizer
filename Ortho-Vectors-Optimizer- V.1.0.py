import sys
import tkinter as tk
from tkinter import messagebox

# IMMUTABLE SYSTEM BOOT HOOK: Catches basic structural load anomalies instantly on startup
try:
    import subprocess
    import os
    import bz2
    import time
    import threading
    import gc
    import shutil
    import json
    import multiprocessing
    import webbrowser
    from concurrent.futures import ThreadPoolExecutor
    from tkinter import filedialog, ttk
except Exception as boot_err:
    import traceback
    root_boot = tk.Tk()
    root_boot.withdraw()
    messagebox.showerror("Critical Initialization Boot Capture", f"Compiler failure details:\n\n{traceback.format_exc()}")
    sys.exit(1)
def diagnostic_exception_hook(exc_type, exc_value=None, exc_traceback=None):
    if hasattr(exc_type, 'exc_type'):  
        exc_value = exc_type.exc_value
        exc_traceback = exc_traceback
        exc_type = exc_type.exc_type
    import traceback
    err_det = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    root_err = tk.Tk()
    root_err.withdraw()
    messagebox.showerror("Application Thread Exception Capture", f"Runtime worker error:\n\n{err_det}")
    root_err.destroy()

sys.excepthook = diagnostic_exception_hook
threading.excepthook = diagnostic_exception_hook

try:
    import psutil
except ImportError:
    subprocess.run(["pip", "install", "psutil"], capture_output=True)
    import psutil
PRESETS = {
    "GLOBAL SCAN (WORLD DATA MATRIX)": {"lat_s": -85, "lat_n": 85, "lon_w": -180, "lon_e": 180, "file": ""},
    "AFRICA": {"lat_s": -35, "lat_n": 38, "lon_w": -18, "lon_e": 52, "file": "africa-260716.osm.pbf"},
    "ASIA & MALDIVES": {"lat_s": -12, "lat_n": 60, "lon_w": 26, "lon_e": 150, "file": "asia-260716.osm.pbf"},
    "EUROPE": {"lat_s": 34, "lat_n": 82, "lon_w": -32, "lon_e": 180, "file": "europe-latest.osm.pbf"},
    "NORTH AMERICA": {"lat_s": 14, "lat_n": 84, "lon_w": -170, "lon_e": -10, "file": "north-america-latest.osm.pbf"},
    "AUSTRALIA & NZ": {"lat_s": -55, "lat_n": -10, "lon_w": 110, "lon_e": 180, "file": "australia-oceania-260717.osm.pbf"},
    "SOUTH AMERICA": {"lat_s": -56, "lat_n": 13, "lon_w": -82, "lon_e": -34, "file": "south-america-260716.osm.pbf"},
    "CENTRAL AMERICA": {"lat_s": 7, "lat_n": 28, "lon_w": -93, "lon_e": -59, "file": "central-america-260716.osm.pbf"},
    "HAWAII & MICRONESIA": {"lat_s": -10, "lat_n": 30, "lon_w": 130, "lon_e": 180, "file": "australia-oceania-260717.osm.pbf"},
    "CUSTOM RANGE (MANUAL)": {"lat_s": "", "lat_n": "", "lon_w": "", "lon_e": "", "file": ""}
}

active_subprocesses = []
pool_executor = None
unique_pid = "master_cache" 
session_file_path = ""
master_region_path = ""
is_paused = False
resume_list = []
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
    if data["file"]:
        file_path_var.set(os.path.join(util_path_var.get(), data["file"]))
    if selected != "CUSTOM RANGE (MANUAL)":
        for widget in (lat_s_entry, lat_n_entry, lon_w_entry, lon_e_entry):
            widget.config(state='disabled')

def toggle_mode_widgets(event=None):
    active_mode = mode_combo.get()
    trig_state = "disabled" if active_mode == "Place 1 KB Bypass Holders Only" else "normal"
    util_entry.config(state=trig_state)
    pbf_entry.config(state=trig_state)
    util_btn.config(state=trig_state)
    pbf_btn.config(state=trig_state)
def browse_utils():
    f_dir = filedialog.askdirectory(initialdir=util_path_var.get(), title="Select Utilities Folder")
    if f_dir: util_path_var.set(os.path.normpath(f_dir))

def browse_file():
    f_name = filedialog.askopenfilename(initialdir=util_path_var.get(), title="Select OSM PBF File", filetypes=(("OSM PBF", "*.osm.pbf"), ("All", "*.*")))
    if f_name: file_path_var.set(f_name)

def browse_destination():
    f_dir = filedialog.askdirectory(initialdir=dest_path_var.get(), title="Select Output Folder")
    if f_dir: dest_path_var.set(os.path.normpath(f_dir))

def open_geofabrik_link(event):
    webbrowser.open_new("https://geofabrik.de")
def on_close_purge(complete_success=False, save_session_files=False):
    global unique_pid, util_path_var, active_subprocesses, pool_executor, session_file_path, master_region_path
    if pool_executor:
        try: pool_executor.shutdown(wait=False, cancel_futures=True)
        except: pass
    for proc in active_subprocesses:
        try: proc.terminate()
        except: pass
        try: proc.kill()
        except: pass
    util_dir = util_path_var.get().strip()
    if util_dir:
        t_dir = os.path.join(util_dir, "Temp")
        if os.path.exists(t_dir):
            time.sleep(0.5)
            for item in os.listdir(t_dir):
                if "tscratch_" in item or "raw_" in item or "filter_args" in item:
                    try: shutil.rmtree(os.path.join(t_dir, item), ignore_errors=True)
                    except: pass
                    try: os.remove(os.path.join(t_dir, item))
                    except: pass
            if complete_success or not save_session_files:
                if session_file_path and os.path.exists(session_file_path):
                    try: os.remove(session_file_path)
                    except: pass
                if master_region_path and os.path.exists(master_region_path):
                    try: os.remove(master_region_path)
                    except: pass
    try: root.destroy()
    except: pass
def trigger_live_pause():
    global is_paused
    is_paused = True
    btn_pause.pack_forget()
    btn_resume.pack(side='left', padx=10, pady=10)
    status_var.set("Status: Frozen. Click Resume to continue.")
    root.update_idletasks()

def trigger_live_resume():
    global is_paused
    is_paused = False
    btn_resume.pack_forget()
    btn_pause.pack(side='left', padx=10, pady=10)
    status_var.set("Status: Resuming loops...")
    root.update_idletasks()

def trigger_save_exit():
    global is_paused, resume_list, session_file_path
    is_paused = True
    status_var.set("Status: Checkpointing full operating environment state matrix...")
    root.update_idletasks()
    state_payload = {
        "mode_selection": mode_combo.get(),
        "preset_selection": preset_combo.get(),
        "lat_s": lat_s_entry.get(),
        "lat_n": lat_n_entry.get(),
        "lon_w": lon_w_entry.get(),
        "lon_e": lon_e_entry.get(),
        "util_path": util_path_var.get(),
        "file_path": file_path_var.get(),
        "dest_path": dest_path_var.get(),
        "completed_checklist": resume_list
    }
    try:
        t_dir = os.path.join(util_path_var.get().strip(), "Temp")
        os.makedirs(t_dir, exist_ok=True)
        target_file = session_file_path if session_file_path else os.path.join(t_dir, "osm_session.json")
        with open(target_file, "w", encoding="utf-8") as sf: json.dump(state_payload, sf, indent=4)
    except: pass
    time.sleep(1.0)
    messagebox.showinfo("Saved", "Full environment state matrix checkpointed successfully!\n\nExiting wrapper panel.")
    on_close_purge(complete_success=False, save_session_files=True)
def run_matrix_pipeline():
    global session_file_path, master_region_path, unique_pid, resume_list
    sel_file, out_dir, bin_dir = file_path_var.get().strip(), dest_path_var.get().strip(), util_path_var.get().strip()
    mode_selection = mode_combo.get()
    if not out_dir:
        messagebox.showerror("Validation Error", "Output parameters folder destination path is missing!"); return
    osmconv, osmfilt = os.path.join(bin_dir, "osmconvert.exe"), os.path.join(bin_dir, "osmfilter.exe")
    if mode_selection == "Create Real OSM Data Mesh":
        if not bin_dir or not sel_file:
            messagebox.showerror("Validation Error", "Required path parameters are missing!"); return
        if not os.path.exists(sel_file):
            messagebox.showerror("Execution Error", "Missing target master PBF input asset for real data compile!"); return
        if not os.path.exists(osmconv) or not os.path.exists(osmfilt):
            messagebox.showerror("Utility Error", "Missing osmconvert.exe or osmfilter.exe binaries!"); return
    try:
        S_LAT, E_LAT = int(lat_s_entry.get().strip()), int(lat_n_entry.get().strip())
        S_LON, E_LON = int(lon_w_entry.get().strip()), int(lon_e_entry.get().strip())
    except ValueError:
        messagebox.showerror("Format Error", "Coordinates parameters must use whole integers only!"); return
    if S_LAT > E_LAT or S_LON > E_LON:
        messagebox.showerror("Logic Error", "Starting coordinates must be lower than ending limits!"); return

    session_file_path = os.path.abspath(os.path.join(bin_dir, "Temp", "osm_session.json"))
    master_region_path = os.path.abspath(os.path.join(bin_dir, "Temp", f"temp_region_{unique_pid}.o5m"))

    input_frame.grid_forget(); btn_run.grid_forget(); link_container.grid_forget()
    progress_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=20, sticky='nsew')
    root.geometry("580x300")
    threading.Thread(target=bg_worker_process, args=(S_LAT, E_LAT, S_LON, E_LON, bin_dir, out_dir, sel_file, osmconv, osmfilt, resume_list, mode_selection), daemon=True).start()
def bg_worker_process(START_LAT, END_LAT, START_LON, END_LON, util_dir, storage_dir, selected_file, osmconvert_path, osmfilter_path, resume_list, active_mode):
    global unique_pid, active_subprocesses, pool_executor, session_file_path, master_region_path, is_paused
    start_time = time.time()
    t_scratch = os.path.abspath(os.path.join(util_dir, "Temp"))
    os.makedirs(t_scratch, exist_ok=True)
    startupinfo = None
    all_tiles = []
    for lat in range(START_LAT, END_LAT + 1):
        for lon in range(START_LON, END_LON + 1):
            all_tiles.append((lat, lon))
    total_tiles = len(all_tiles)
    progress_bar["maximum"] = total_tiles
    completed_tiles = len(resume_list)
    loop_start_time = time.time()

    if total_tiles < 500: chunk_count = 1
    elif total_tiles < 1500: chunk_count = 3
    elif total_tiles < 3500: chunk_count = 5
    else: chunk_count = 10

    c_size = max(1, -(-total_tiles // chunk_count))
    t_chunks = [all_tiles[i:i + c_size] for i in range(0, total_tiles, c_size)]
    sys_cores = multiprocessing.cpu_count()       
    calc_workers = max(1, int(sys_cores * 0.85))
    if psutil.virtual_memory().total / (1024**3) <= 18.0: calc_workers = min(calc_workers, 4)
    completed_lock = threading.Lock()

    def process_single_tile_thread(coords):
        global unique_pid, active_subprocesses, session_file_path, master_region_path, is_paused
        while is_paused: time.sleep(0.01)
        lat_coord, lon_coord = coords
        l_p = "+" if lat_coord >= 0 else "-"
        o_p = "+" if lon_coord >= 0 else "-"
        base_folder_name = f"{l_p}{str(abs(lat_coord)).zfill(2)}{o_p}{str(abs(lon_coord)).zfill(3)}"
        if base_folder_name in resume_list: return base_folder_name

        suffixes = ["_airports.osm", "_big_roads.osm", "_coastline.osm", "_water.osm"]
        t_lat = (int(lat_coord) // 10) * 10
        t_lon = (int(lon_coord) // 10) * 10
        group_folder_name = f"{'+' if t_lat >= 0 else '-'}{str(abs(t_lat)).zfill(2)}{'+' if t_lon >= 0 else '-'}{str(abs(t_lon)).zfill(3)}"
        tile_folder = os.path.abspath(os.path.join(storage_dir, group_folder_name, base_folder_name))
        os.makedirs(tile_folder, exist_ok=True)
        
        if active_mode == "Place 1 KB Bypass Holders Only":
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
                    try:
                        with open(session_file_path, "r") as r_f: current_state = json.load(r_f)
                        current_state["completed_checklist"] = resume_list
                        with open(session_file_path, "w") as w_f: json.dump(current_state, w_f)
                    except: pass
            return base_folder_name
        all_protected = True
        for suffix in suffixes:
            if not (os.path.exists(os.path.join(tile_folder, f"{base_folder_name}{suffix}.bz2")) and os.path.getsize(os.path.join(tile_folder, f"{base_folder_name}{suffix}.bz2")) > 2000):
                all_protected = False; break
        if all_protected:
            with completed_lock:
                if base_folder_name not in resume_list: resume_list.append(base_folder_name)
            return base_folder_name

        scr_dir = os.path.abspath(os.path.join(t_scratch, f"tscratch_{l_p}{abs(lat_coord)}_{o_p}{abs(lon_coord)}_{unique_pid}"))
        os.makedirs(scr_dir, exist_ok=True)
        loc_tile = os.path.abspath(os.path.join(scr_dir, "temp_tile.osm"))
        cmd_cut = [osmconvert_path, os.path.abspath(master_region_path), f"-b={float(lon_coord)},{float(lat_coord)},{float(lon_coord)+1.0},{float(lat_coord)+1.0}", "--complete-ways", "--drop-author", "--drop-version", f"-o={loc_tile}"]
        p_cut = subprocess.Popen(cmd_cut, startupinfo=startupinfo); p_cut.wait()
        try: active_subprocesses.remove(p_cut)
        except: pass
        if is_paused: return "PAUSED_SKIP"

        filters = {
            "_airports.osm": 'aeroway=airport =aerodrome =apron =runway =taxiway =helipad',
            "_big_roads.osm": 'highway=motorway =motorway_link =trunk =trunk_link =primary =primary_link =secondary =secondary_link',
            "_coastline.osm": 'natural=coastline boundary=administrative maritime=yes place=sea water=sea',
            "_water.osm": 'natural=water water=polygon =lake =river =reservoir waterway=riverbank =dock'
        }
        for suffix, query in filters.items():
            if is_paused: return "PAUSED_SKIP"
            final_bz2 = os.path.abspath(os.path.join(tile_folder, f"{base_folder_name}{suffix}.bz2"))
            if os.path.exists(final_bz2) and os.path.getsize(final_bz2) > 2000: continue
            r_out = os.path.abspath(os.path.join(scr_dir, f"raw_{suffix}"))
            u_pref = os.path.abspath(os.path.join(scr_dir, f"osmfilter_tempfile_{base_folder_name}"))
            p_file = os.path.abspath(os.path.join(t_scratch, f"filter_args_global_{suffix}_{base_folder_name}.txt"))
            with open(p_file, "w", encoding="utf-8") as pf:
                pf.write(f"--keep={query}\n--max-objects=1000000000\n--drop-relations\n--used-node\n--used-way\n")
            cmd_filt = [osmfilter_path, loc_tile, "--parameter-file=" + p_file, f"-t={u_pref}", f"-o={r_out}"]
            p_filt = subprocess.Popen(cmd_filt, startupinfo=startupinfo); active_subprocesses.append(p_filt); p_filt.wait()
            try: active_subprocesses.remove(p_filt)
            except: pass
            try: os.remove(p_file)
            except: pass
            if not os.path.exists(r_out) or os.path.getsize(r_out) == 0:
                with open(r_out, "w", encoding="utf-8") as f: f.write("<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6' generator='osmfilter'>\n</osm>")
            try:
                with open(r_out, 'rb') as f_in, bz2.open(final_bz2, 'wb', compresslevel=6) as f_out:
                    while True:
                        chunk = f_in.read(65536)
                        if not chunk: break
                        f_out.write(chunk)
            except: pass
            try: os.remove(r_out)
            except: pass
        try: shutil.rmtree(scr_dir, ignore_errors=True)
        except: pass
        with completed_lock:
            if base_folder_name not in resume_list and not is_paused:
                resume_list.append(base_folder_name)
                try:
                    with open(session_file_path, "r") as r_f: current_state = json.load(r_f)
                    current_state["completed_checklist"] = resume_list
                    with open(session_file_path, "w") as w_f: json.dump(current_state, w_f)
                except: pass
        gc.collect(); return base_folder_name
    for chunk_idx, current_chunk in enumerate(t_chunks):
        if is_paused: break
        chunk_ready = True
        for c_lat, c_lon in current_chunk:
            t_chk = f"{'+' if c_lat >= 0 else '-'}{str(abs(c_lat)).zfill(2)}{'+' if c_lon >= 0 else '-'}{str(abs(c_lon)).zfill(3)}"
            if t_chk not in resume_list: chunk_ready = False; break
        if chunk_ready: completed_tiles = len(resume_list); continue
        if active_mode == "Create Real OSM Data Mesh":
            c_lats = [lat for lat, lon in current_chunk]
            c_lons = [lon for lat, lon in current_chunk]
            chunk_bbox = f"{int(min(c_lons))},{int(min(c_lats))},{int(max(c_lons))+1},{int(max(c_lats))+1}"
            if os.path.exists(master_region_path) and len(resume_list) > 0: pass 
            else:
                if os.path.exists(master_region_path):
                    try: os.remove(master_region_path)
                    except: pass
                cmd_master = [osmconvert_path, os.path.abspath(selected_file), f"-b={chunk_bbox}", "--complete-ways", "--drop-author", "--drop-version", f"-o={os.path.abspath(master_region_path)}"]
                proc = subprocess.Popen(cmd_master, startupinfo=startupinfo); active_subprocesses.append(proc); m_start = time.time()
                while proc.poll() is None:
                    if is_paused: break
                    status_var.set(f"Package {chunk_idx + 1}/{len(t_chunks)} Scan... [Elapsed: {int(time.time() - m_start)}s]")
                    root.update_idletasks(); time.sleep(0.5)
                try: active_subprocesses.remove(proc)
                except: pass
                time.sleep(2.5)
        pool_executor = ThreadPoolExecutor(max_workers=calc_workers if active_mode == "Create Real OSM Data Mesh" else max(4, calc_workers))
        for completed_name in pool_executor.map(process_single_tile_thread, current_chunk):
            if is_paused or completed_name == "PAUSED_SKIP": break
            act_c = len(resume_list)
            if act_c > completed_tiles: completed_tiles = act_c
            rem_t = total_tiles - completed_tiles; l_elap = int(time.time() - loop_start_time)
            avg_t = l_elap / completed_tiles if completed_tiles > 0 else 0.0
            raw_etc = int(rem_t * (avg_t / calc_workers)) if active_mode == "Create Real OSM Data Mesh" else int(rem_t * 0.0001)
            status_var.set(f"Package {chunk_idx + 1}/{len(t_chunks)} | Compiling: {completed_name}")
            metrics_var.set(f"Completed: {completed_tiles} | Remaining: {rem_t} | Total: {total_tiles}\nElapsed: {l_elap // 60}m {l_elap % 60}s | Avg/Tile: {round(avg_t, 2)}s\nETC: {raw_etc // 60}m {raw_etc % 60}s")
            progress_bar["value"] = completed_tiles; root.update_idletasks()
        pool_executor.shutdown(wait=True); gc.collect()
    if not is_paused:
        final_elapsed = int(time.time() - loop_start_time); final_avg = final_elapsed / total_tiles if total_tiles > 0 else 0.0
        status_var.set("Status: Batch compilation finished successfully!"); root.update_idletasks()
        if messagebox.askyesno("Batch Processing Complete", f"Extraction Creation Is Successful!\n\n=== BATCH SUMMARY RUN LOG ===\n• Total Tiles Compiled: {total_tiles}\n• Total Elapsed Time: {final_elapsed // 60}m {final_elapsed % 60}s\n• Average Execution/Tile: {round(final_avg, 2)} seconds\n\nWould you like to return to the dashboard to start a brand new map sequence?"):
            if pool_executor:
                try: pool_executor.shutdown(wait=False, cancel_futures=True)
                except: pass
            if master_region_path and os.path.exists(master_region_path):
                try: os.remove(master_region_path)
                except: pass
            if session_file_path and os.path.exists(session_file_path):
                try: os.remove(session_file_path)
                except: pass
            progress_frame.grid_forget(); input_frame.grid(row=0, column=0, columnspan=2, padx=15, pady=5, sticky='w')
            btn_run.grid(row=10, column=0, columnspan=2, padx=24, pady=10, sticky='w'); link_container.grid(row=11, column=0, columnspan=2, sticky='w', padx=15, pady=8)
            status_var.set("Status: Awaiting execution initialization..."); metrics_var.set("Completed: 0  |  Remaining: 0  |  Total Tiles: 0"); progress_bar["value"] = 0; root.geometry("580x475"); root.update_idletasks()
        else: on_close_purge(complete_success=True, save_session_files=False)

root = tk.Tk(); root.title("Ortho4XP Step 1: Offline Vector Data Compiler"); root.geometry("580x475"); root.resizable(False, False)
root.protocol("WM_DELETE_WINDOW", trigger_save_exit)
input_frame = tk.Frame(root); input_frame.grid(row=0, column=0, columnspan=2, padx=15, pady=5, sticky='w')
file_path_var, dest_path_var, util_path_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
dest_path_var.set(r"E:\Ortho4XP\_internal\Ortho4XP_Data\OSM_data"); util_path_var.set(r"C:\Ortho_OSM")
tk.Label(input_frame, text="Select Target Region:", font=("Arial", 10, "bold")).grid(row=0, column=0, pady=6, sticky='w')
preset_combo = ttk.Combobox(input_frame, values=list(PRESETS.keys()), width=40, state="readonly"); preset_combo.grid(row=0, column=1, padx=10, pady=6, sticky='w')
preset_combo.bind("<<ComboboxSelected>>", on_preset_change)
tk.Label(input_frame, text="Scenery Output Mode:", font=("Arial", 10, "bold")).grid(row=1, column=0, pady=6, sticky='w')
mode_combo = ttk.Combobox(input_frame, values=["Place 1 KB Bypass Holders Only", "Create Real OSM Data Mesh"], width=40, state="readonly"); mode_combo.grid(row=1, column=1, padx=10, pady=6, sticky='w')
mode_combo.bind("<<ComboboxSelected>>", toggle_mode_widgets)
tk.Label(input_frame, text="Format Rule: Input whole numbers only (e.g., 27 or -35). No decimals or symbols!", font=("Arial", 8, "italic"), fg="#e74c3c").grid(row=2, column=0, columnspan=2, pady=2, sticky='w')
tk.Label(input_frame, text="Start Latitude (South):").grid(row=3, column=0, pady=4, sticky='w')
lat_s_entry = tk.Entry(input_frame, width=15); lat_s_entry.grid(row=3, column=1, padx=10, pady=4, sticky='w')
tk.Label(input_frame, text="End Latitude (North):").grid(row=4, column=0, pady=4, sticky='w')
lat_n_entry = tk.Entry(input_frame, width=15); lat_n_entry.grid(row=4, column=1, padx=10, pady=4, sticky='w')
tk.Label(input_frame, text="Start Longitude (West):").grid(row=5, column=0, pady=4, sticky='w')
lon_w_entry = tk.Entry(input_frame, width=15); lon_w_entry.grid(row=5, column=1, padx=10, pady=4, sticky='w')
tk.Label(input_frame, text="End Longitude (East):").grid(row=6, column=0, pady=4, sticky='w')
lon_e_entry = tk.Entry(input_frame, width=15); lon_e_entry.grid(row=6, column=1, padx=10, pady=4, sticky='w')
tk.Label(input_frame, text="Utility Folder Bin:", font=("Arial", 10, "bold")).grid(row=7, column=0, pady=6, sticky='w')
util_entry = tk.Entry(input_frame, textvariable=util_path_var, width=43); util_entry.grid(row=7, column=1, padx=10, pady=6, sticky='w')
util_btn = tk.Button(input_frame, text="Browse...", command=browse_utils, width=10); util_btn.grid(row=7, column=1, padx=280, pady=6, sticky='w')
tk.Label(input_frame, text="Select Master PBF File:", font=("Arial", 10, "bold")).grid(row=8, column=0, pady=6, sticky='w')
pbf_entry = tk.Entry(input_frame, textvariable=file_path_var, width=43); pbf_entry.grid(row=8, column=1, padx=10, pady=6, sticky='w')
pbf_btn = tk.Button(input_frame, text="Browse...", command=browse_file, width=10); pbf_btn.grid(row=8, column=1, padx=280, pady=6, sticky='w')
tk.Label(input_frame, text="Output Destination:", font=("Arial", 10, "bold")).grid(row=9, column=0, pady=6, sticky='w')
tk.Entry(input_frame, textvariable=dest_path_var, width=43).grid(row=9, column=1, padx=10, pady=6, sticky='w')
tk.Button(input_frame, text="Browse...", command=browse_destination, width=10); util_btn.grid(row=9, column=1, padx=280, pady=6, sticky='w')
btn_run = tk.Button(root, text="START PROCESSING BATCH", font=("Arial", 11, "bold"), bg="#2ecc71", fg="white", command=run_matrix_pipeline, height=2, width=54); btn_run.grid(row=10, column=0, columnspan=2, padx=24, pady=10, sticky='w')
progress_frame = tk.Frame(root); status_var, metrics_var = tk.StringVar(), tk.StringVar(); status_var.set("Status: Awaiting execution initialization..."); metrics_var.set("Completed: 0  |  Remaining: 0  |  Total Tiles: 0")
tk.Label(progress_frame, textvariable=status_var, font=("Arial", 10, "bold"), fg="#2c3e50").pack(anchor='w', pady=5); progress_bar = ttk.Progressbar(progress_frame, orient="horizontal", length=530, mode="determinate"); progress_bar.pack(fill='x', pady=10)
tk.Label(progress_frame, textvariable=metrics_var, font=("Arial", 9, "italic"), fg="#7f8c8d").pack(anchor='w', pady=5); btn_container = tk.Frame(progress_frame); btn_container.pack(pady=10)
btn_pause = tk.Button(btn_container, text="PAUSE BATCH", font=("Arial", 10, "bold"), bg="#f39c12", fg="white", command=trigger_live_pause, height=2, width=24); btn_pause.pack(side='left', padx=10)
btn_resume = tk.Button(btn_container, text="RESUME BATCH", font=("Arial", 10, "bold"), bg="#27ae60", fg="white", command=trigger_live_resume, height=2, width=24); btn_save_exit = tk.Button(btn_container, text="SAVE FOR LATER & EXIT", font=("Arial", 10, "bold"), bg="#d35400", fg="white", command=trigger_save_exit, height=2, width=24); btn_save_exit.pack(side='left', padx=10)
link_container = tk.Frame(root); link_container.grid(row=11, column=0, columnspan=2, sticky='w', padx=15, pady=8); link_label = tk.Label(link_container, text="Download OSM data package from Geofabrik here https://geofabrik.de", font=("Arial", 9, "underline"), fg="#3498db", cursor="hand2"); link_label.pack(anchor='w'); link_label.bind("<Button-1>", open_geofabrik_link)

tk.Label(root, text="add by Ahmed Qanadeely", font=("Arial", 7, "italic"), fg="#95a5a6").place(relx=1.0, rely=1.0, anchor='se', x=-10, y=-2)

preset_combo.current(0); on_preset_change(None); mode_combo.current(0); toggle_mode_widgets(None)

session_fallbacks = [r"C:\Ortho_OSM\Temp\osm_session.json", r"E:\Ortho4XP\Temp\osm_session.json"]
for fallback_path in session_fallbacks:
    if os.path.exists(fallback_path) and os.path.getsize(fallback_path) > 10:
        if messagebox.askyesno("Session Found", f"A saved environment state matrix was captured at:\n{fallback_path}\n\nWould you like to completely restore your previous dashboard configuration?"):
            try:
                with open(fallback_path, "r", encoding="utf-8") as sf: state = json.load(sf)
                util_path_var.set(state.get("util_path", r"C:\Ortho_OSM"))
                file_path_var.set(state.get("file_path", ""))
                dest_path_var.set(state.get("dest_path", r"E:\Ortho4XP\_internal\Ortho4XP_Data\OSM_data"))
                mode_combo.set(state.get("mode_selection", "Place Bypass Holders Only"))
                preset_combo.set(state.get("preset_selection", "GLOBAL SCAN (WORLD DATA MATRIX)"))
                for widget in (lat_s_entry, lat_n_entry, lon_w_entry, lon_e_entry):
                    widget.config(state='normal')
                    widget.delete(0, tk.END)
                lat_s_entry.insert(0, state.get("lat_s", "-85"))
                lat_n_entry.insert(0, state.get("lat_n", "85"))
                lon_w_entry.insert(0, state.get("lon_w", "-180"))
                lon_e_entry.insert(0, state.get("lon_e", "180"))
                if preset_combo.get() != "CUSTOM RANGE (MANUAL)":
                    for widget in (lat_s_entry, lat_n_entry, lon_w_entry, lon_e_entry): widget.config(state='disabled')
                toggle_mode_widgets(None)
                resume_list = state.get("completed_checklist", [])
                messagebox.showinfo("Restored", f"Dashboard configuration fully synchronized!\n• Restored Tiles: {len(resume_list)}\n\nYou are ready to click 'START PROCESSING BATCH' right away.")
                break
            except: pass
root.mainloop()
