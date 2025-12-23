from nicegui import ui, events, app, run
import uuid
import os
import tempfile
import shutil
import zipfile
import inspect  # Required to detect coroutines
from backend import *
from pathlib import Path

# --- DIRECTORY SETUP ---
BASE_DIR = Path(os.getcwd()) / 'hydro_data'
UPLOAD_DIR = BASE_DIR / 'uploads'
GROWTH_DIR = BASE_DIR / 'growth'
MASK_DIR = BASE_DIR / 'masks'

for d in [UPLOAD_DIR, GROWTH_DIR, MASK_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app.add_static_files('/hydro_data', str(BASE_DIR))

# --- GLOBAL STATE ---
uploaded_file_paths = []
uploaded_mask_paths = []
clicks = []
ii = None 
file_list_container = None 
image_container = None     

# --- STYLING ---
ui.colors(primary='#4CAF50', secondary='#8BC34A', accent='#FF9800')

# --- LOGIC FUNCTIONS ---

def update_file_list_display():
    if file_list_container:
        file_list_container.clear()
        with file_list_container:
            if not uploaded_file_paths:
                ui.label("No images uploaded yet.").classes('text-gray-400 italic')
            else:
                ui.label(f"{len(uploaded_file_paths)} Images Ready:").classes('font-bold text-gray-600')
                with ui.row().classes('gap-2 flex-wrap'):
                    for f in uploaded_file_paths:
                        ui.chip(Path(f).name, icon='image').props('outline color=primary')

def get_file_info(event):
    """
    Robustly extracts filename and content object from the event.
    """
    file_name = "unknown_file"
    content_obj = None

    # Check 1: Standard structure
    if hasattr(event, 'name'): file_name = event.name
    if hasattr(event, 'content'): content_obj = event.content

    # Check 2: Nested 'file' structure
    if hasattr(event, 'file'):
        f = event.file
        if hasattr(f, 'name'): file_name = f.name
        elif hasattr(f, 'filename'): file_name = f.filename
        
        if hasattr(f, 'read'): content_obj = f
        elif hasattr(f, 'content'): content_obj = f.content
        elif hasattr(f, 'file'): content_obj = f.file  

    return file_name, content_obj

# FIX: Changed to 'async def' to handle async file reads
async def save_uploaded_file(event):
    try:
        file_name, content_obj = get_file_info(event)

        if content_obj is None:
            # Fallback for some wrappers
            if hasattr(event, 'read'):
                content_obj = event
            else:
                raise ValueError(f"Could not find file content. Attributes: {dir(event)}")

        path = UPLOAD_DIR / file_name
        
        # FIX: Handle Async Seek
        if hasattr(content_obj, 'seek'):
            try:
                result = content_obj.seek(0)
                if inspect.iscoroutine(result):
                    await result
            except Exception:
                pass 

        # FIX: Handle Async Read
        content = content_obj.read()
        if inspect.iscoroutine(content):
            content = await content

        with open(path, 'wb') as f:
            f.write(content)
            
        uploaded_file_paths.append(str(path))
        ui.notify(f'🌱 Uploaded: {file_name}')
        update_file_list_display()
        
    except Exception as e:
        ui.notify(f"Upload Error: {e}", type='negative')
        print(f"CRITICAL UPLOAD ERROR: {e}")

# FIX: Changed to 'async def'
async def save_uploaded_mask(event):
    try:
        file_name, content_obj = get_file_info(event)
        
        if content_obj is None:
             if hasattr(event, 'read'): content_obj = event
             else: raise ValueError("No content found")

        path = MASK_DIR / file_name
        
        if hasattr(content_obj, 'seek'):
            try:
                result = content_obj.seek(0)
                if inspect.iscoroutine(result): await result
            except Exception: pass

        content = content_obj.read()
        if inspect.iscoroutine(content):
            content = await content

        with open(path, 'wb') as f:
            f.write(content)
            
        uploaded_mask_paths.append(str(path))
        ui.notify(f'🎭 Mask Uploaded: {file_name}')
    except Exception as e:
        ui.notify(f"Mask Upload Error: {e}", type='negative')

def handle_rejection(event):
    reason = "Unknown"
    if hasattr(event, 'reason'): reason = event.reason
    ui.notify(f"⚠️ File rejected! {reason}", type='negative')

def reset_points():
    clicks.clear()
    if ii: ii.content = '' 
    ui.notify("🩹 Points reset. Please click 4 new points on the image.")

def on_image_click(e: events.MouseEventArguments):
    global ii
    if len(clicks) < 4:
        color = 'SkyBlue' if e.type == 'mousedown' else 'SteelBlue'
        ii.content += f'<circle cx="{e.image_x}" cy="{e.image_y}" r="15" fill="none" stroke="{color}" stroke-width="4" />'
        clicks.append([e.image_x, e.image_y])
        if len(clicks) == 4:
            ui.notify("✅ 4 points selected! Processing crop...")
            x_coords = [pt[0] for pt in clicks]
            y_coords = [pt[1] for pt in clicks]
            x, y = min(x_coords), min(y_coords)
            w, h = max(x_coords)-x, max(y_coords)-y
            ii.content += f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="rgba(76, 175, 80, 0.3)" stroke="#4CAF50" stroke-width="5" />'
            ui.timer(0.5, crop_ready, once=True)

def crop_ready():
    x_coords = [pt[0] for pt in clicks]
    y_coords = [pt[1] for pt in clicks]
    x, y, w, h = int(min(x_coords)), int(min(y_coords)), int(max(x_coords)-min(x_coords)), int(max(y_coords)-min(y_coords))
    roi = (x, y, w, h)

    temp_input = tempfile.mkdtemp()
    for src_path in uploaded_file_paths:
        shutil.copy2(src_path, os.path.join(temp_input, os.path.basename(src_path)))

    temp_output = tempfile.mkdtemp()
    run_cropping(temp_input, temp_output, roi)

    zip_path = BASE_DIR / "cropped_images.zip"
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for fname in os.listdir(temp_output):
            zipf.write(os.path.join(temp_output, fname), arcname=fname)

    ui.download(f'/hydro_data/cropped_images.zip', filename="cropped_images.zip")
    shutil.rmtree(temp_input)
    shutil.rmtree(temp_output)
    clicks.clear()
    image_container.clear() 

def show_first_image():
    global ii
    if not uploaded_file_paths:
        ui.notify("Please upload files first", type="warning")
        return

    image_url = f'/hydro_data/uploads/{os.path.basename(uploaded_file_paths[0])}'
    image_container.clear()
    with image_container:
        ui.label("👇 Click the 4 corners of the planting bed:").classes('text-lg font-bold text-gray-700')
        ii = ui.interactive_image(image_url, on_mouse=on_image_click, events=['click'], cross=True)
        ii.classes('w-full rounded-lg shadow-md border-2 border-gray-300')

def process_timelapse():
    if not uploaded_file_paths: return
    
    temp_input = tempfile.mkdtemp()
    video_filename = f"timelapse_{uuid.uuid4().hex}.mp4"
    output_video_path = BASE_DIR / video_filename

    try:
        ui.notify("⏳ Generating timelapse...")
        for src_path in uploaded_file_paths:
            shutil.copy2(src_path, os.path.join(temp_input, os.path.basename(src_path)))

        if run_timelapse(temp_input, str(output_video_path), fps=1.0):
            ui.download(f'/hydro_data/{video_filename}', filename="timelapse.mp4")
            ui.notify("🎬 Timelapse ready!")
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)

def process_masking():
    if not uploaded_file_paths: return
    temp_input = tempfile.mkdtemp()
    try:
        ui.notify("⏳ Generating masks...")
        for file_path in uploaded_file_paths:
            shutil.copy2(file_path, os.path.join(temp_input, os.path.basename(file_path)))
        zip_path = run_mask(temp_input, str(BASE_DIR))
        if os.path.exists(zip_path):
            ui.download(f'/hydro_data/{os.path.basename(zip_path)}', filename="masks.zip")
            ui.notify("✅ Masks ready!")
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)

def process_growth():
    if not uploaded_file_paths: return
    temp_input = tempfile.mkdtemp()
    try:
        ui.notify("⏳ Analyzing growth...")
        for file_path in uploaded_file_paths:
            shutil.copy2(file_path, os.path.join(temp_input, os.path.basename(file_path)))
        zip_path = run_graph(temp_input, str(BASE_DIR))
        if os.path.exists(zip_path):
            ui.download(f'/hydro_data/{os.path.basename(zip_path)}', filename="graphs.zip")
            ui.notify("✅ Graphs ready!")
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)

# --- MAIN PAGE LAYOUT ---
def main_page():
    global file_list_container, image_container
    
    with ui.header().classes('bg-primary text-white shadow-lg'):
        ui.icon('eco', size='2em').classes('q-mr-sm')
        ui.label('Hydroponic System Analysis').classes('text-2xl font-bold')

    with ui.column().classes('w-full items-center gap-6 p-6 bg-gray-50 min-h-screen'):
        
        with ui.expansion('📖 Instructions & Guide', icon='help', value=True).classes('w-full max-w-4xl bg-white rounded-lg shadow-sm'):
            with ui.list():
                ui.item('1. Upload Images: Drop images (Max 70MB) below.')
                ui.item('2. Crop: Setup Cropping > Pick 4 points > Download.')
                ui.item('3. Masking/Growth: Use the buttons below.')

        with ui.card().classes('w-full max-w-4xl p-6 items-center'):
            ui.label('Step 1: Upload Data').classes('text-xl font-bold text-gray-700')
            
            ui.upload(
                on_upload=save_uploaded_file, 
                on_rejected=handle_rejection,
                multiple=True, 
                auto_upload=True, 
                max_file_size=70_000_000, 
                label="Drop images here (Max 70MB)"
            ).props('color=primary flat bordered').classes('w-full max-w-lg')
            
            file_list_container = ui.column().classes('w-full items-center mt-4')
            update_file_list_display()

        with ui.grid(columns=2).classes('w-full max-w-4xl gap-6'):
            with ui.card().classes('p-6 items-center hover:shadow-lg transition-shadow border-t-4 border-green-500'):
                ui.icon('crop', size='3em', color='primary')
                ui.label('Crop Images').classes('text-lg font-bold mt-2')
                with ui.row().classes('mt-2'):
                    ui.button('Setup Cropping', on_click=lambda: show_first_image(), icon='edit').props('color=secondary')
                    ui.button('Reset', on_click=reset_points, icon='refresh').props('flat color=grey')

            for icon, label, func, btn_text in [
                ('movie', 'Timelapse', process_timelapse, 'Create Video'),
                ('contrast', 'Generate Masks', process_masking, 'Make Masks'),
                ('ssid_chart', 'Growth Analysis', process_growth, 'Run Analysis')
            ]:
                with ui.card().classes('p-6 items-center hover:shadow-lg transition-shadow'):
                    ui.icon(icon, size='3em', color='primary')
                    ui.label(label).classes('text-lg font-bold mt-2')
                    ui.button(btn_text, on_click=func).props('color=secondary class=mt-2')

        image_container = ui.column().classes('w-full max-w-4xl items-center mt-8 bg-white p-4 rounded-lg shadow-lg')

# --- ENTRY POINT ---
if __name__ in {"__main__", "__mp_main__"}:
    main_page()
    ui.run(title="Hydroponic Analysis", host='0.0.0.0', port=8080, show=False)