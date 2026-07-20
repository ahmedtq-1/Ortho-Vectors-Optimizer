# Ortho-Vectors-Optimizer
A powerful offline utility that bypasses lengthy Ortho4XP Step 1 OSM data downloads when using SimHeaven and native X-Plane 12 DSF layers. It dramatically shortens tile creation times without affecting final scenery quality
Developed by **Ahmed Qanadeely**.

---

## 🚀 Key Features

* **Instant Step 1 Bypassing**: Generates optimized 3 KB bypass payload files (`.osm.bz2`) on the fly. This forces Ortho4XP to safely skip Internet downloading phases, allowing **SimHeaven X-World** and native X-Plane 12 layers to handle global object positioning with 100% accurate alignment.
* **Offline Master PBF Slicing**: Reads local `.pbf` country map extract files (e.g., from Geofabrik) and uses native space-separated `osmfilter` syntax queries to cut and sort genuine feature data into structured 1x1 degree tiles ready for Ortho4XP processing.
* **Global Scan Matrix Preset**: Includes a one-click world matrix option mapping all coordinates from `-85°` to `85°` Latitude and `-180°` to `180°` Longitude (Exactly 61,731 tile checkpoints).
* **Cross-Reactive UI Freezing**: Automatically locks out utility bins and file path browse triggers when placeholder mode is selected, keeping the user interface completely stabilized.
* **Full State Matrix Checkpointing**: Saves your exact paths, selected region presets, dropdown modes, coordinate entry fields, and completed tile checklists every single time you close or exit the application. It auto-prompts on boot to resume your previous work instantly.

---

## 🛠️ Installation & Requirements

1. Make sure you have **Python 3.x** installed on your system.
2. Ensure you have the `psutil` library. The script will attempt to auto-install it via `pip`, but you can install it manually by running:
   ```bash
   pip install psutil
   ```
3. Place your `osmconvert.exe` and `osmfilter.exe` binaries inside your utility bin directory (e.g., `C:\Ortho_OSM`). You can download the official **osmconvert** and **osmfilter** executables directly from the [OpenStreetMap Wiki Program Downloads](https://openstreetmap.org) and place both binaries inside your designated utility folder.

---

## 📖 How to Use

1. Double-click or run the script via your terminal.
2. Select your desired region from the **Select Target Region** dropdown menu.
3. Choose your **Scenery Output Mode**:
   * **Place 1 KB Bypass Holders Only**: Generates the 3 KB bypass file payloads instantly without requiring any input `.pbf` maps.
   * **Create Real OSM Data Mesh**: Slices localized `.pbf` map entries into fully populated, real vector assets.
4. Verify your folder directory paths and click **START PROCESSING BATCH**.
5. If you need to stop or close the window, simply exit or close the panel. The application will trigger an auto-save rule to snapshot your entire workspace state matrix safely.

## ☕ Support the Project

If this tool saved you hours of scenery downloading and improved your X-Plane setup, consider supporting my work!

👉 **[Support via PayPal](https://paypal.me/ahmedtq)**

*Every gift is greatly appreciated and helps me maintain and optimize this utility and more for the community!

Feel free to suggest any other tool or enhancement.
