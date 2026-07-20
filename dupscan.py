import os
import subprocess
import sys
from collections import defaultdict
import imagehash
from PIL import Image
import streamlit as st
import shutil
import time
from datetime import datetime
import json
# Optional system trash support
try:
    from send2trash import send2trash
except Exception:
    send2trash = None
# Supported image extensions for previews and detection
VALID_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

# Set the webpage title and layout
st.set_page_config(page_title="Duplicate Image Scanner", layout="wide")

st.title("🖼️ Visual Duplicate Scanner")
st.write(
   "Paste a folder path below. This engine uses **Perceptual Hashing**—meaning it looks at the *visual picture*, not the file name."
)


# --- THE ENGINE (Logic) ---
def scan_for_duplicates(folder_path):
   # defaultdict creates a dictionary that automatically starts an empty list [] for any new key
   hashes = defaultdict(list)

   valid_extensions = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

   # 1. Gather all image files inside the folder
   image_files = []
   for root, _, files in os.walk(folder_path):
       for file in files:
           ext = os.path.splitext(file)[1].lower()
           if ext in valid_extensions:
               image_files.append(os.path.join(root, file))

   # 2. Set up a progress bar on the webpage
   progress_bar = st.progress(0)
   status_text = st.empty()

   # 3. Inspect every image
   for index, file_path in enumerate(image_files):
       status_text.text(
           f"Scanning ({index + 1}/{len(image_files)}): {os.path.basename(file_path)}"
       )

       try:
           with Image.open(file_path) as img:
               # Generate a 16-character 'visual fingerprint' of the image
               fingerprint = str(imagehash.phash(img))

               # Put the file path into the dictionary under that fingerprint's name
               hashes[fingerprint].append(file_path)

       except Exception:
           # If an image is corrupted or unreadable, safely skip it
           continue

       # Update the visual progress bar
       progress_bar.progress((index + 1) / len(image_files))

   status_text.empty()
   progress_bar.empty()

   # 4. Filter: We only care about fingerprints that caught 2 or more files
   duplicates_only = {
       fingerprint: paths
       for fingerprint, paths in hashes.items()
       if len(paths) > 1
   }

   return duplicates_only


# --- Helpers for safe deletes (undo buffer using a trash folder) ---

def get_trash_dir():
   """Return a trash folder path inside the scanning folder (or home if none)."""
   base = st.session_state.get("scanning_folder") or os.path.expanduser("~")
   trash = os.path.join(base, ".duplicate_trash")
   os.makedirs(trash, exist_ok=True)
   # Load persistent undo index when the trash folder is available
   load_undo_index()
   return trash


def undo_index_path():
   base = st.session_state.get("scanning_folder") or os.path.expanduser("~")
   trash = os.path.join(base, ".duplicate_trash")
   return os.path.join(trash, "undo.json")


def load_undo_index():
   p = undo_index_path()
   if os.path.exists(p):
       try:
           with open(p, "r") as f:
               data = json.load(f)
           # Ensure it's a list
           if isinstance(data, list):
               st.session_state.undo_stack = data
           else:
               st.session_state.undo_stack = st.session_state.get("undo_stack", [])
       except Exception:
           st.session_state.undo_stack = st.session_state.get("undo_stack", [])
   else:
       # leave any existing in-memory stack, or initialize empty
       st.session_state.undo_stack = st.session_state.get("undo_stack", [])


def save_undo_index():
   p = undo_index_path()
   try:
       tmp = p + ".tmp"
       with open(tmp, "w") as f:
           json.dump(st.session_state.get("undo_stack", []), f)
       os.replace(tmp, p)
   except Exception:
       # best-effort; don't crash the app on save errors
       pass


def move_to_trash(path, fingerprint=None):
    """Move a file to the trash (system or local) and record it in the undo stack.

    Returns the trashed path (or None for system trash) on success, None on failure.
    """
    if not os.path.exists(path):
        return None
    ts = int(time.time() * 1000)
    # If user opted for system trash and send2trash is available, use it
    use_system = st.session_state.get("use_system_trash", False) and send2trash is not None
    if use_system:
        try:
            send2trash(path)
        except Exception:
            return None
        # We cannot reliably determine the system trash path; mark trashed as None
        entry = {"original": path, "trashed": None, "time": ts, "fingerprint": fingerprint, "system": True}
    else:
        trash = get_trash_dir()
        base = os.path.basename(path)
        dest = os.path.join(trash, f"{ts}_{base}")
        try:
            shutil.move(path, dest)
        except Exception:
            return None
        entry = {"original": path, "trashed": dest, "time": ts, "fingerprint": fingerprint}

    if "undo_stack" not in st.session_state:
        st.session_state.undo_stack = []
    st.session_state.undo_stack.append(entry)
    # persist undo index to disk
    try:
        save_undo_index()
    except Exception:
        pass
    # Return a sentinel for system-trash to indicate success but no local path
    if entry.get("system"):
        return "__SYSTEM_TRASH__"
    return entry.get("trashed")


def restore_from_trash(entry):
   """Restore a trashed file back to its original location and update results.

   Returns True on success, False otherwise.
   """
   # System-trash entries cannot be restored by this app
   if entry.get("trashed") is None:
       return False
   trashed = entry.get("trashed")
   original = entry.get("original")
   fp = entry.get("fingerprint")
   if not trashed or not os.path.exists(trashed):
       return False
   try:
       dest_dir = os.path.dirname(original)
       os.makedirs(dest_dir, exist_ok=True)
       shutil.move(trashed, original)
   except Exception:
       return False

   # Re-insert into results under the fingerprint if possible
   if fp:
       if "results" not in st.session_state:
           st.session_state.results = {}
       if fp in st.session_state.results:
           if original not in st.session_state.results[fp]:
               st.session_state.results[fp].append(original)
       else:
           # recreate group with just the restored file
           st.session_state.results[fp] = [original]
   return True


# --- THE DASHBOARD (Webpage UI) ---

# 1. Memory: Streamlit resets every time you click a button.
# We use 'session_state' to force it to remember the folder path.
def pick_folder():
   try:
       if sys.platform == "darwin":
           result = subprocess.run(
               [
                   "osascript",
                   "-e",
                   'POSIX path of (choose folder with prompt "Select a folder")',
               ],
               capture_output=True,
               text=True,
               check=True,
           )
           selected_folder = result.stdout.strip()
           return selected_folder or ""
       else:
           import tkinter as tk
           from tkinter import filedialog

           root = tk.Tk()
           root.withdraw()
           root.attributes("-topmost", True)
           folder_selected = filedialog.askdirectory()
           root.destroy()
           return folder_selected or ""
   except Exception:
       return ""

if "folder_path" not in st.session_state:
   st.session_state.folder_path = ""

st.write("Choose a folder to scan for duplicates.")
st.write(
   "Click Browse to pick a local folder, or paste its path manually below."
)

if st.button("Browse Folder"):
   selected_folder = pick_folder()
   if selected_folder:
       st.session_state.folder_path = selected_folder
       st.rerun()
   else:
       st.info("The folder picker could not be opened. Please paste the folder path manually instead.")

# 3. The Input Box (now automatically filled by the Browse button)
folder_input = st.text_input(
   "Target Folder Path:",
   value=st.session_state.folder_path
)

if st.button("Start Scan", type="primary"):
   if os.path.exists(folder_input):
       with st.spinner("Crunching pixels..."):
           st.session_state.results = scan_for_duplicates(folder_input)
           st.session_state.scanning_folder = folder_input

   else:
       st.error("That folder path doesn't seem to exist. Try browsing for it!")

# If we have stored results display them and allow deletion in-place
if "results" in st.session_state and st.session_state.get("results"):
   # Keep a stable ordered list of groups so we can navigate between them without re-scanning
   if "group_index" not in st.session_state:
       st.session_state.group_index = 0

   if "groups_per_page" not in st.session_state:
       st.session_state.groups_per_page = 1

   results = st.session_state.results
   if not results:
       st.success("Clean folder! No duplicate images detected.")
   else:
       groups = list(results.items())
       # clamp the index
       if st.session_state.group_index >= len(groups):
           st.session_state.group_index = max(0, len(groups) - 1)

       st.warning(f"Scan complete. Found {len(groups)} duplicate groups.")
       st.divider()

       # Control: how many groups to show per page
       max_groups = max(1, len(groups))
       per_page = st.number_input(
           "Groups per page:", min_value=1, max_value=max_groups, value=st.session_state.groups_per_page, step=1, key="groups_per_page_input"
       )
       st.session_state.groups_per_page = int(per_page)

       # Slice the groups for current page
       start = st.session_state.group_index
       end = min(start + st.session_state.groups_per_page, len(groups))
       page_groups = groups[start:end]

       # Show selected groups
       for i, (fingerprint, file_list) in enumerate(page_groups, start=start + 1):
           st.subheader(f"Match Group #{i} of {len(groups)}")

           # Display images for this group
           cols = st.columns(len(file_list) if file_list else 1)
           for col_idx, file_path in enumerate(list(file_list)):
               with cols[col_idx]:
                   if os.path.exists(file_path):
                       st.image(file_path, width='stretch')

                       file_name = os.path.basename(file_path)
                       file_size_kb = os.path.getsize(file_path) / 1024

                       st.caption(f"**{file_name}**")
                       st.text(f"Size: {file_size_kb:.1f} KB")

                       # Instead of immediately deleting, set a pending action so the user must confirm
                       if st.button("🗑️ Delete this copy", key=f"del_{file_path}"):
                           st.session_state.pending_action = {
                               "type": "delete",
                               "fingerprint": fingerprint,
                               "target": file_path,
                               "continue": False,
                           }
                           st.experimental_rerun()

                       if st.button("🗑️ Delete and continue", key=f"delcont_{file_path}"):
                           st.session_state.pending_action = {
                               "type": "delete",
                               "fingerprint": fingerprint,
                               "target": file_path,
                               "continue": True,
                           }
                           st.experimental_rerun()

                       # Bulk action: keep this file, delete the other copies in the same group
                       if st.button("🔒 Keep this, delete others", key=f"keepone_{file_path}"):
                           st.session_state.pending_action = {
                               "type": "keep_one",
                               "fingerprint": fingerprint,
                               "keep": file_path,
                               "continue": True,
                           }
                           st.experimental_rerun()

                   else:
                       st.text("File not found on disk")

           st.divider()

       # Confirmation area for pending actions (uses trash + undo stack)
       if st.session_state.get("pending_action"):
           action = st.session_state.pending_action
           act_type = action.get("type")

           if act_type == "delete":
               tgt = action.get("target")
               fp = action.get("fingerprint")
               st.warning(f"Confirm deletion of: {tgt}")
               cols = st.columns([1,1,3])
               with cols[0]:
                   if st.button("Confirm Delete"):
                       dest = move_to_trash(tgt, fp)
                       if not dest:
                           st.error("Could not move the file to trash.")
                       else:
                           # update results
                           if fp in st.session_state.results and tgt in st.session_state.results[fp]:
                               st.session_state.results[fp].remove(tgt)
                               if len(st.session_state.results[fp]) < 2:
                                   del st.session_state.results[fp]
                           # adjust index if needed
                           if action.get("continue"):
                               if st.session_state.group_index < len(st.session_state.results) - 1:
                                   st.session_state.group_index += 1
                               else:
                                   st.session_state.group_index = max(0, len(st.session_state.results) - 1)
                       # clear pending and refresh
                       del st.session_state.pending_action
                       st.experimental_rerun()
               with cols[1]:
                   if st.button("Cancel"):
                       del st.session_state.pending_action
                       st.experimental_rerun()
               with cols[2]:
                   st.info(f"The file will be moved to the trash folder ({get_trash_dir()}). You can undo recent deletes from the Trash & Undo panel below.")

           elif act_type == "keep_one":
               keep = action.get("keep")
               fp = action.get("fingerprint")
               others = [p for p in st.session_state.results.get(fp, []) if p != keep]
               st.warning(f"Confirm: delete {len(others)} files and keep {keep}")
               cols = st.columns([1,1,3])
               with cols[0]:
                   if st.button("Confirm Keep One"):
                       deleted_any = False
                       for p in others:
                           dest = move_to_trash(p, fp)
                           if dest:
                               deleted_any = True
                           else:
                               st.error(f"Could not move {p} to trash")
                       # update session results
                       if fp in st.session_state.results:
                           # keep only the chosen file
                           st.session_state.results[fp] = [keep]
                           if len(st.session_state.results[fp]) < 2:
                               del st.session_state.results[fp]
                       # move to next group if requested
                       if action.get("continue"):
                           if st.session_state.group_index < len(st.session_state.results) - 1:
                               st.session_state.group_index += 1
                           else:
                               st.session_state.group_index = max(0, len(st.session_state.results) - 1)
                       del st.session_state.pending_action
                       st.experimental_rerun()
               with cols[1]:
                   if st.button("Cancel Keep One"):
                       del st.session_state.pending_action
                       st.experimental_rerun()
               with cols[2]:
                   st.info(f"All other copies will be moved to the trash folder ({get_trash_dir()}). You can undo if needed.")

       # Trash / Undo panel (selective restore, auto-purge, system trash option)
       # Ensure undo stack exists
       if "undo_stack" not in st.session_state:
           st.session_state.undo_stack = []

       # System trash support toggle (send2trash if available)
       if "use_system_trash" not in st.session_state:
           st.session_state.use_system_trash = False
       # Auto-empty settings
       if "auto_empty_days" not in st.session_state:
           st.session_state.auto_empty_days = 30
       if "auto_empty_enabled" not in st.session_state:
           st.session_state.auto_empty_enabled = True

       st.divider()
       st.subheader("Trash & Undo")

       # System trash toggle
       st.session_state.use_system_trash = st.checkbox(
           "Move deletes to system Trash/Recycle Bin if available (send2trash)",
           value=st.session_state.use_system_trash,
           key="use_system_trash_input",
       )
       # show availability note
       try:
           from send2trash import send2trash  # noqa: F401
           send2trash_available = True
       except Exception:
           send2trash_available = False
       if st.session_state.use_system_trash and not send2trash_available:
           st.warning("send2trash not installed — system Trash option is unavailable. Install with 'pip install send2trash' to enable it.")

       trash = get_trash_dir()
       st.write(f"Local trash folder: {trash} (used when system Trash is unavailable or not selected)")

       # Auto-empty controls
       cols_ae = st.columns([2,1])
       with cols_ae[0]:
           st.session_state.auto_empty_enabled = st.checkbox("Auto-purge trashed items older than N days", value=st.session_state.auto_empty_enabled)
       with cols_ae[1]:
           st.session_state.auto_empty_days = st.number_input("Days", min_value=1, max_value=3650, value=st.session_state.auto_empty_days, key="auto_empty_days_input")

       # Purge old trashed items if enabled
       def purge_old_trash(days):
           now_ms = int(time.time() * 1000)
           kept = []
           removed_count = 0
           for e in list(st.session_state.get("undo_stack", [])):
               entry_time = e.get("time") or 0
               age_ms = now_ms - entry_time
               if age_ms > days * 24 * 60 * 60 * 1000:
                   # attempt to remove trashed file if present
                   tpath = e.get("trashed")
                   try:
                       if tpath and os.path.exists(tpath):
                           os.remove(tpath)
                           removed_count += 1
                   except Exception:
                       # couldn't remove, keep the entry so user can inspect
                       kept.append(e)
                       continue
                   # if system entry (trashed is None), just drop the record
               else:
                   kept.append(e)
           st.session_state.undo_stack = kept
           try:
               save_undo_index()
           except Exception:
               pass
           return removed_count

       if st.session_state.auto_empty_enabled and st.session_state.auto_empty_days:
           removed = purge_old_trash(int(st.session_state.auto_empty_days))
           if removed:
               st.info(f"Auto-purged {removed} trashed files older than {st.session_state.auto_empty_days} days.")

       # Show undo stack with selectable entries
       undo_list = st.session_state.get("undo_stack", [])
       st.write(f"Pending undo items: {len(undo_list)}")

       selected = []
       if undo_list:
           st.markdown("Select items to restore or permanently delete:")
           # Render each undo entry with an optional image preview (if available locally)
           for idx, entry in enumerate(list(undo_list)):
               orig = entry.get("original")
               ts = entry.get("time") or 0
               ts_readable = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M:%S") if ts else "unknown"
               system = entry.get("trashed") is None
               label = f"{orig} — trashed at {ts_readable}" + (" [system Trash]" if system else "")

               # layout: preview | info | select
               row_cols = st.columns([1, 6, 1])
               trashed_path = entry.get("trashed")
               # Preview column
               with row_cols[0]:
                   try:
                       if trashed_path and os.path.exists(trashed_path):
                           ext = os.path.splitext(trashed_path)[1].lower()
                           if ext in VALID_IMAGE_EXT:
                               # show a small preview
                               try:
                                   st.image(trashed_path, width=120)
                               except Exception:
                                   st.text("Preview unavailable")
                           else:
                               st.text("No preview")
                       else:
                           st.text("No preview")
                   except Exception:
                       st.text("No preview")

               # Info column
               with row_cols[1]:
                   st.write(label)

               # Checkbox/select column
               with row_cols[2]:
                   key = f"undo_select_{idx}"
                   if st.checkbox("", key=key):
                       selected.append(idx)

           action_cols = st.columns([1,1,1,1])
           with action_cols[0]:
                   if st.button("Restore Selected"):
                   # restore in reverse order to avoid index shifts
                   for sel in sorted(selected, reverse=True):
                       entry = st.session_state.undo_stack[sel]
                       if entry.get("trashed") is None:
                           st.error(f"Cannot restore {entry.get('original')} from system Trash")
                           continue
                       ok = restore_from_trash(entry)
                       if ok:
                           st.success(f"Restored: {entry.get('original')}")
                           del st.session_state.undo_stack[sel]
                       else:
                           st.error(f"Failed to restore: {entry.get('original')}")
                   try:
                       save_undo_index()
                   except Exception:
                       pass
                   st.experimental_rerun()
           with action_cols[1]:
               if st.button("Permanently Delete Selected"):
                   removed_any = 0
                   for sel in sorted(selected, reverse=True):
                       entry = st.session_state.undo_stack[sel]
                       tpath = entry.get("trashed")
                       if tpath and os.path.exists(tpath):
                           try:
                               os.remove(tpath)
                               removed_any += 1
                           except Exception:
                               st.error(f"Could not permanently remove {tpath}")
                       else:
                           # system trash entries cannot be removed here
                           if entry.get("trashed") is None:
                               st.info(f"{entry.get('original')} was sent to system Trash; cannot permanently remove from here.")
                       del st.session_state.undo_stack[sel]
                   try:
                       save_undo_index()
                   except Exception:
                       pass
                   st.success(f"Removed {removed_any} trashed files permanently and cleared their undo entries")
                   st.experimental_rerun()
           with action_cols[2]:
               if st.button("Undo last delete"):
                   entry = st.session_state.undo_stack.pop()
                   try:
                       save_undo_index()
                   except Exception:
                       pass
                   if entry.get("trashed") is None:
                       st.error("Cannot restore items sent to system Trash")
                   else:
                       ok = restore_from_trash(entry)
                       if ok:
                           st.success(f"Restored: {entry.get('original')}")
                       else:
                           st.error("Could not restore the file from trash")
                   st.experimental_rerun()
           with action_cols[3]:
               if st.button("Empty Trash (permanent)"):
                   removed = 0
                   for e in list(st.session_state.get("undo_stack", [])):
                       tpath = e.get("trashed")
                       try:
                           if tpath and os.path.exists(tpath):
                               os.remove(tpath)
                               removed += 1
                       except Exception:
                           st.error(f"Could not remove {tpath}")
                   st.session_state.undo_stack = []
                   try:
                       save_undo_index()
                   except Exception:
                       pass
                   st.success(f"Emptied trash ({removed} files removed)")
                   st.experimental_rerun()

       else:
           st.info("Trash is empty")

       # Quick controls
       qcols = st.columns([1,1])
       with qcols[0]:
           if st.button("Show trash folder"):
               st.info(trash)
       with qcols[1]:
           if st.button("Clear Undo History (leave trashed files)"):
               st.session_state.undo_stack = []
               try:
                   save_undo_index()
               except Exception:
                   pass
               st.success("Cleared undo history (trashed files left on disk)")
               st.experimental_rerun()

       # Navigation controls (move by page size)
       st.divider()
       nav_step = max(1, st.session_state.groups_per_page)
       nav_cols = st.columns([1,1,2])
       with nav_cols[0]:
           if st.button("⬅️ Previous"):
               st.session_state.group_index = max(0, st.session_state.group_index - nav_step)
               st.experimental_rerun()
       with nav_cols[1]:
           if st.button("Next ➡️"):
               st.session_state.group_index = min(max(0, len(groups) - 1), st.session_state.group_index + nav_step)
               st.experimental_rerun()
       with nav_cols[2]:
           if st.button("Rescan Folder"):
               # Re-run a fresh scan of the stored folder
               if st.session_state.get("scanning_folder") and os.path.exists(st.session_state.scanning_folder):
                   with st.spinner("Re-scanning folder..."):
                       st.session_state.results = scan_for_duplicates(st.session_state.scanning_folder)
                       st.session_state.group_index = 0
                       st.experimental_rerun()
               else:
                   st.error("No folder stored to re-scan. Please run a new scan.")
