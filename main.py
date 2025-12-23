from nicegui import ui, events, app, run
import uuid
import os
import tempfile
import shutil
import zipfile
from backend import *
from PIL import Image
import threading
from pathlib import Path

# --- GLOBAL VARIABLES ---
clicks = []
ii = None 
# UI Element References (for enabling/disabling)
crop_download_btn = None
image_container = None
file_list_label = None

# --- SETUP DIRECTORIES ---
UPLOAD_DIR = Path('/tmp/hydro_uploads')
GROWTH_DIR = Path('/tmp/hydro_growth')
MASK_DIR = Path('/tmp/hydro_masks')

for d in [UPLOAD_DIR, GROWTH_DIR, MASK_DIR]:
    d.mkdir(parents=True, exist_ok=True)

session_id = str(uuid.uuid4())
session_dir = UPLOAD_DIR / session_id
growth_session_dir = GROWTH_DIR / session_id
mask_session_dir = MASK_DIR / session_id

for d in [session_dir, growth_session_dir, mask_session_dir]:
    d.mkdir(parents=True, exist_ok=True)

uploaded_file_paths = []
uploaded_mask_paths = []

# --- STYLING ---
ui.colors(primary='#4CAF50', secondary='#8BC34A', accent='#FF9800')

# --- LOGIC FUNCTIONS ---

def update_file_list_display():
    if file_list_label:
        count = len(uploaded_file_paths)
        file_list_label.set_text(f'{count} Image{"s" if count != 1 else ""} Ready')

def save_uploaded_file(event):
    file = event.name
    path = session_dir / file
    content = event.content.read()
    with open(path, 'wb') as f:
        f.write(content)
    uploaded_file_paths.append(str(path))
    ui.notify(f'🌱 Uploaded: {file}')
    update_file_list_display()

def save_uploaded_mask(event):
    file = event.name
    path = mask_session_dir / file
    content = event.content.read()
    with open(path, 'wb') as f:
        f.write(content)
    uploaded_mask_paths.append(str(path))
    ui.notify(f'🎭 Mask Uploaded: {file}')

def reset_points():
    global clicks, ii
    clicks.clear()
    if ii:
        ii.content = '' # Clear SVG drawings
    if crop_download_btn:
        crop_download_btn.disable()
    ui.notify("🩹 Points reset. Click 4 corners of the plant bed.")

def on_image_click(e: events.MouseEventArguments):
    global ii, clicks
    if len(clicks) >= 4:
        ui.notify("Region already selected. Press Reset to start over.", type='warning')
        return

    # Draw a point where user clicked
    color = '#FF9800' # Orange
    ii.content += f'<circle cx="{e.image_x}" cy="{e.image_y}" r="15" fill="none" stroke="{color}" stroke-width="4" />'
    clicks.append([e.image_x, e.image_y])

    # If 4 points are selected, draw the box and enable download
    if len(clicks) == 4:
        x_coords = [pt[0] for pt in clicks]
        y_coords = [pt[1] for pt in clicks]
        
        # Calculate bounding box
        x = min(x_coords)
        y = min(y_coords)
        w = max(x_coords) - x
        h = max(y_coords) - y
        
        # Draw the rectangle visually so user sees what they are cropping
        ii.content += f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="rgba(76, 175, 80, 0.3)" stroke="#4CAF50" stroke-width="5" />'
        
        ui.notify("✅ Region confirmed! Press 'Download Crop' to finish.")
        if crop_download_btn:
            crop_download_btn.enable()

def execute_crop():
    if len(clicks) != 4:
        ui.notify("Please select 4 points first", type='warning')
        return

    x_coords = [pt[0] for pt in clicks]
    y_coords = [pt[1] for pt in clicks]
    x = int(min(x_coords))
    y = int(min(y_coords))
    w = int(max(x_coords) - x)
    h = int(max(y_coords) - y)
    roi = (x, y, w, h)

    temp_input = tempfile.mkdtemp()
    for src_path in uploaded_file_paths:
        shutil.copy2(src_path, os.path.join(temp_input, os.path.basename(src_path)))

    temp_output = tempfile.mkdtemp()
    
    # Run the backend cropping
    run_cropping(temp_input, temp_output, roi)

    zip_path = os.path.join(tempfile.gettempdir(), "cropped_images.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for fname in os.listdir(temp_output):
            zipf.write(os.path.join(temp_output, fname), arcname=fname)

    ui.download(zip_path, filename="cropped_images.zip")
    shutil.rmtree(temp_input)
    shutil.rmtree(temp_output)
    
    # Cleanup UI
    image_container.clear()
    clicks.clear()

def setup_cropping_ui():
    if not uploaded_file_paths:
        ui.notify("Please upload files first!", type="warning")
        return
    
    global ii, crop_download_btn
    first_file_path = uploaded_file_paths[0]
    
    image_container.clear()
    with image_container:
        ui.label("👇 Click the 4 corners of the area you want to keep:").classes('text-lg font-bold text-gray-700')
        
        # Image Area
        ii = ui.interactive_image(str(first_file_path), on_mouse=on_image_click, events=['click'], cross=True)
        ii.classes('w-full rounded-lg shadow-md border-2 border-gray-300')
        
        # Control Row below image
        with ui.row().classes('w-full justify-center gap-4 mt-4'):
            ui.button('Reset Points', on_click=reset_points, icon='refresh').props('color=grey')
            crop_download_btn = ui.button('Download Crop', on_click=execute_crop, icon='download').props('color=primary')
            crop_download_btn.disable() # Disabled until 4 points clicked

def process_timelapse():
    if not uploaded_file_paths:
        ui.notify("Please upload images first", type="warning")
        return
    
    temp_input = tempfile.mkdtemp()
    temp_video = os.path.join(tempfile.gettempdir(), f"timelapse_{uuid.uuid4().hex}.mp4")
    try:
        for src_path in uploaded_file_paths:
            shutil.copy2(src_path, os.path.join(temp_input, os.path.basename(src_path)))
        
        # Note: Ensure backend.py has the updated run_timelapse logic we discussed!
        if run_timelapse(temp_input, temp_video, fps=2.0):
            ui.download(temp_video, filename="timelapse.mp4")
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)

def process_masking():
    if not uploaded_file_paths:
        ui.notify("Please upload images first.", type="warning")
        return

    temp_input = tempfile.mkdtemp()
    try:
        for file_path in uploaded_file_paths:
            shutil.copy2(file_path, os.path.join(temp_input, os.path.basename(file_path)))
        zip_path = run_mask(temp_input, tempfile.gettempdir())
        if os.path.exists(zip_path):
            ui.download(zip_path, filename="masks.zip")
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)

def process_growth():
    if not uploaded_file_paths:
        ui.notify("Please upload BINARY images first.", type="warning")
        return

    temp_input = tempfile.mkdtemp()
    try:
        for file_path in uploaded_file_paths:
            shutil.copy2(file_path, os.path.join(temp_input, os.path.basename(file_path)))
        zip_path = run_graph(temp_input, tempfile.gettempdir())
        if os.path.exists(zip_path):
            ui.download(zip_path, filename="graphs.zip")
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)


# --- MAIN UI LAYOUT ---
def main_page():
    global file_list_label, image_container

    with ui.header().classes('bg-primary text-white shadow-lg'):
        ui.icon('eco', size='2em').classes('q-mr-sm')
        ui.label('Hydroponic System Analysis').classes('text-2xl font-bold')

    with ui.column().classes('w-full items-center gap-8 p-8 bg-gray-50 min-h-screen'):
        
        # 1. Instructions Section
        with ui.expansion('📖 Instructions & Guide', icon='help', value=True).classes('w-full max-w-4xl bg-white rounded-lg shadow-sm'):
            with ui.list():
                ui.item('1. Upload Images: Add your plant images using the upload button below.')
                ui.item('2. Crop: Click "Setup Cropping", select 4 points on the image, then download.')
                ui.item('3. Masking: Upload the cropped images, run "Make Masks", and download the zip.')
                ui.item('4. Growth: Upload the mask images, run "Growth Analysis", and get your data!')

        # 2. Main Upload Section (Cleaned Up)
        with ui.card().classes('w-full max-w-4xl p-6 items-center'):
            ui.label('Step 1: Upload Data').classes('text-xl font-bold text-gray-700')
            
            # auto_upload=True removes the need for extra button presses
            ui.upload(on_upload=save_uploaded_file, multiple=True, auto_upload=True, label="Select Images to Upload")\
                .props('color=primary flat bordered').classes('w-full max-w-lg')
            
            file_list_label = ui.label('0 Images Ready').classes('text-gray-500 font-bold mt-2')

        # 3. Action Cards (Grid Layout)
        with ui.grid(columns=2).classes('w-full max-w-4xl gap-6'):
            
            # Card: Cropping
            with ui.card().classes('p-6 items-center hover:shadow-lg transition-shadow border-t-4 border-green-500'):
                ui.icon('crop', size='3em', color='primary')
                ui.label('Crop Images').classes('text-lg font-bold mt-2')
                ui.label('Isolate the plant bed.').classes('text-sm text-gray-500 text-center')
                ui.button('Setup Cropping', on_click=setup_cropping_ui, icon='edit').props('color=secondary class=mt-2')

            # Card: Timelapse
            with ui.card().classes('p-6 items-center hover:shadow-lg transition-shadow'):
                ui.icon('movie', size='3em', color='primary')
                ui.label('Timelapse').classes('text-lg font-bold mt-2')
                ui.label('Generate video from images.').classes('text-sm text-gray-500 text-center')
                ui.button('Create Video', on_click=process_timelapse, icon='play_circle').props('color=secondary class=mt-2')

            # Card: Masking
            with ui.card().classes('p-6 items-center hover:shadow-lg transition-shadow'):
                ui.icon('contrast', size='3em', color='primary')
                ui.label('Generate Masks').classes('text-lg font-bold mt-2')
                ui.label('Convert to binary (B&W).').classes('text-sm text-gray-500 text-center')
                ui.button('Make Masks', on_click=process_masking, icon='brush').props('color=secondary class=mt-2')

            # Card: Growth Analysis
            with ui.card().classes('p-6 items-center hover:shadow-lg transition-shadow'):
                ui.icon('ssid_chart', size='3em', color='primary')
                ui.label('Growth Analysis').classes('text-lg font-bold mt-2')
                ui.label('Analyze growth trends.').classes('text-sm text-gray-500 text-center')
                ui.button('Run Analysis', on_click=process_growth, icon='analytics').props('color=accent class=mt-2')

        # 4. Image Workspace (Where the image appears for cropping)
        image_container = ui.column().classes('w-full max-w-4xl items-center mt-8 bg-white p-4 rounded-lg shadow-lg')

# --- ENTRY POINT ---
# This guard is required to prevent "Client has been deleted" errors 
# when using multiprocessing on some systems.
if __name__ in {"__main__", "__mp_main__"}:
    main_page()
    ui.run()