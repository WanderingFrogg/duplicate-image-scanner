import os
import subprocess
import sys
from collections import defaultdict
import imagehash
from PIL import Image
import streamlit as st
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
           results = scan_for_duplicates(folder_input)

       if not results:
           st.success("Clean folder! No duplicate images detected.")
       else:
           st.warning(f"Scan complete. Found {len(results)} duplicate groups.")
           st.divider()

           for group_num, (fingerprint, file_list) in enumerate(
               results.items(), start=1
           ):
               st.subheader(f"Match Group #{group_num}")
               cols = st.columns(len(file_list))

               for col_idx, file_path in enumerate(file_list):
                   with cols[col_idx]:
                       st.image(file_path, use_container_width=True)

                       file_name = os.path.basename(file_path)
                       file_size_kb = os.path.getsize(file_path) / 1024

                       st.caption(f"**{file_name}**")
                       st.text(f"Size: {file_size_kb:.1f} KB")

                       if st.button(
                           "🗑️ Delete this copy", key=f"del_{file_path}"
                       ):
                           os.remove(file_path)
                           st.rerun()
               st.divider()
   else:
       st.error("That folder path doesn't seem to exist. Try browsing for it!")