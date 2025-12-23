# --- CRITICAL: Must be at the top for WSL/Linux ---
import matplotlib
matplotlib.use('Agg') 

from nicegui import ui, events, app, run
import uuid
import os
import tempfile
import shutil
import zipfile
import inspect
from backend import *
from pathlib import Path
from PIL import Image

# --- DIRECTORY SETUP ---
BASE_DIR = Path(os.getcwd()) / 'hydro_data'
UPLOAD_DIR = BASE_DIR / 'uploads'
CROPPED_DIR = BASE_DIR / 'cropped' 
GROWTH_DIR = BASE_DIR / 'growth'
MASK_DIR = BASE_DIR / 'masks'

for d in [UPLOAD_DIR, CROPPED_DIR, GROWTH_DIR, MASK_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app.add_static_files('/hydro_data', str(BASE_DIR))

# --- GLOBAL STATE ---
uploaded_file_paths = []      
latest_color_paths = []       
original_file_paths = []      

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
                ui.label("No active images.").classes('text-gray-400 italic')
            else:
                first_file = str(uploaded_file_paths[0])
                if "masks" in first_file or "_mask" in first_file:
                    status_text = "Active Images (Masks)"
                    color = "purple"
                elif "cropped" in first_file:
                    status_text = "Active Images (Cropped)"
                    color = "green"
                else:
                    status_text = "Active Images (Originals)"
                    color = "grey"
                
                ui.label(f"{len(uploaded_file_paths)} {status_text}:").classes('font-bold text-gray-600')
                with ui.row().classes('gap-2 flex-wrap'):
                    for f in uploaded_file_paths:
                        ui.chip(Path(f).name, icon='image', color=color).props('outline')

def get_file_info(event):
    file_name = "unknown_file"
    content_obj = None
    if hasattr(event, 'name'): file_name = event.name
    if hasattr(event, 'content'): content_obj = event.content
    if hasattr(event, 'file'):
        f = event.file
        if hasattr(f, 'name'): file_name = f.name
        elif hasattr(f, 'filename'): file_name = f.filename
        if hasattr(f, 'read'): content_obj = f
        elif hasattr(f, 'content'): content_obj = f.content
        elif hasattr(f, 'file'): content_obj = f.file  
    return file_name, content_obj

async def save_uploaded_file(event):
    try:
        file_name, content_obj = get_file_info(event)
        if content_obj is None:
            if hasattr(event, 'read'): content_obj = event
            else: raise ValueError(f"Could not find file content.")

        path = UPLOAD_DIR / file_name
        if hasattr(content_obj, 'seek'):
            try:
                result = content_obj.seek(0)
                if inspect.iscoroutine(result): await result
            except Exception: pass 

        content = content_obj.read()
        if inspect.iscoroutine(content): content = await content

        with open(path, 'wb') as f:
            f.write(content)
            
        path_str = str(path)
        if path_str not in original_file_paths:
            original_file_paths.append(path_str)
        
        if path_str not in uploaded_file_paths:
            uploaded_file_paths.append(path_str)
        if path_str not in latest_color_paths:
            latest_color_paths.append(path_str)
            
        ui.notify(f'🌱 Uploaded: {file_name}')
        update_file_list_display()
    except Exception as e:
        ui.notify(f"Upload Error: {e}", type='negative')

def handle_rejection(event):
    reason = event.reason if hasattr(event, 'reason') else "Unknown"
    ui.notify(f"⚠️ File rejected! {reason}", type='negative')

def reset_points():
    clicks.clear()
    if ii: ii.content = '' 
    ui.notify("🩹 Points reset. Click 4 new points.")
    show_first_image()

def revert_to_originals():
    if not original_file_paths:
        ui.notify("No originals to revert to.", type='warning')
        return
    
    uploaded_file_paths.clear()
    uploaded_file_paths.extend(original_file_paths)
    
    latest_color_paths.clear()
    latest_color_paths.extend(original_file_paths)
    
    update_file_list_display()
    ui.notify("Start over: Reverted to original images.")

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

    if CROPPED_DIR.exists(): shutil.rmtree(CROPPED_DIR)
    CROPPED_DIR.mkdir()
    temp_input = tempfile.mkdtemp()
    
    if not original_file_paths:
        ui.notify("No original files found to crop!", type='negative')
        return

    files_to_crop = 0
    for src_path in original_file_paths:
        try:
            shutil.copy2(src_path, os.path.join(temp_input, os.path.basename(src_path)))
            files_to_crop += 1
        except Exception: pass

    if files_to_crop == 0:
        ui.notify("Could not find original files on disk.", type='negative')
        return

    run_cropping(temp_input, str(CROPPED_DIR), roi)
    new_active_files = sorted([str(p) for p in CROPPED_DIR.glob('*') if p.is_file()])
    
    if new_active_files:
        uploaded_file_paths.clear()
        uploaded_file_paths.extend(new_active_files)
        
        latest_color_paths.clear()
        latest_color_paths.extend(new_active_files)
        
        ui.notify(f"✅ Active set updated to {len(new_active_files)} cropped images.")
        update_file_list_display()
        
        zip_path = BASE_DIR / "cropped_images.zip"
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for fpath in new_active_files:
                zipf.write(fpath, arcname=os.path.basename(fpath))
        ui.download(f'/hydro_data/cropped_images.zip', filename="cropped_images.zip")
    else:
        ui.notify("❌ Cropping produced no images. Check ROIs.", type='negative')

    shutil.rmtree(temp_input)
    clicks.clear()
    image_container.clear() 

def show_first_image():
    global ii
    if not original_file_paths:
        ui.notify("Please upload files first", type="warning")
        return
    filename = os.path.basename(original_file_paths[0])
    image_url = f'/hydro_data/uploads/{filename}'
    image_container.clear()
    with image_container:
        ui.label("Click 4 corners of the original image):").classes('text-lg font-bold text-gray-700')
        ii = ui.interactive_image(image_url, on_mouse=on_image_click, events=['click'], cross=True)
        ii.classes('w-full rounded-lg shadow-md border-2 border-gray-300')
    ui.timer(0.1, lambda: image_container.run_method('scrollIntoView', {'behavior': 'smooth', 'block': 'center'}), once=True)

def process_timelapse():
    source_files = latest_color_paths if latest_color_paths else uploaded_file_paths
    
    if not source_files: 
        ui.notify("No images available.", type='warning')
        return
    
    video_size = (1280, 720) 
    try:
        with Image.open(source_files[0]) as img:
            video_size = img.size 
    except Exception as e:
        ui.notify(f"Warning: Could not detect image size: {e}")

    temp_input = tempfile.mkdtemp()
    video_filename = f"timelapse_{uuid.uuid4().hex}.mp4"
    output_video_path = BASE_DIR / video_filename

    try:
        ui.notify(f"⏳ Generating segmented timelapse...")
        for src_path in source_files:
            shutil.copy2(src_path, os.path.join(temp_input, os.path.basename(src_path)))

        if run_timelapse(temp_input, str(output_video_path), fps=1.0, size=video_size):
            ui.download(f'/hydro_data/{video_filename}', filename="timelapse.mp4")
            ui.notify("🎬 Timelapse ready!")
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)

async def process_masking():
    source_files = latest_color_paths if latest_color_paths else uploaded_file_paths
    
    if not source_files: return
    temp_input = tempfile.mkdtemp()
    
    with ui.dialog() as p_dialog, ui.card().classes('w-64 items-center'):
        ui.label("Generating Masks...")
        progress_bar = ui.linear_progress(value=0).props('instant-feedback')
        percentage_label = ui.label("0%")
    
    try:
        p_dialog.open()
        for file_path in source_files:
            shutil.copy2(file_path, os.path.join(temp_input, os.path.basename(file_path)))
            
        def update_prog(ratio):
            progress_bar.value = ratio
            percentage_label.set_text(f"{int(ratio*100)}%")
            
        zip_path = await run.io_bound(run_mask, temp_input, str(BASE_DIR), update_prog)
        p_dialog.close()
        
        if zip_path and os.path.exists(zip_path):
            ui.download(f'/hydro_data/{os.path.basename(zip_path)}', filename="masks.zip")
            ui.notify("✅ Masks Generated!")
            
            if MASK_DIR.exists(): shutil.rmtree(MASK_DIR)
            MASK_DIR.mkdir()
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(MASK_DIR)
            
            new_masks = sorted([str(p) for p in MASK_DIR.glob('*') if p.is_file()])
            if new_masks:
                uploaded_file_paths.clear()
                uploaded_file_paths.extend(new_masks)
                update_file_list_display()
                ui.notify(f"🔄 Active set switched to {len(new_masks)} masks.", type='positive')
        else:
            ui.notify("❌ Masking failed (No output).", type='negative')
    except Exception as e:
        ui.notify(f"Error: {e}", type='negative')
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)
        p_dialog.close()

async def process_growth():
    if not uploaded_file_paths: return
    
    first_file = str(uploaded_file_paths[0])
    is_mask_set = "masks" in first_file or "mask" in Path(first_file).name.lower() or "_mask" in Path(first_file).name.lower()
    
    temp_mask_dir = tempfile.mkdtemp()
    
    try:
        if is_mask_set:
            for file_path in uploaded_file_paths:
                shutil.copy2(file_path, os.path.join(temp_mask_dir, os.path.basename(file_path)))
        else:
            ui.notify("⚠️ Generating temporary masks for analysis...", type='warning')
            temp_input_images = tempfile.mkdtemp()
            for file_path in uploaded_file_paths:
                shutil.copy2(file_path, os.path.join(temp_input_images, os.path.basename(file_path)))
            
            with ui.dialog() as p_dialog, ui.card().classes('w-64 items-center'):
                ui.label("Auto-Masking...")
                progress_bar = ui.linear_progress(value=0).props('instant-feedback')
                p_dialog.open()
                def update_prog(ratio): progress_bar.value = ratio
                zip_path = await run.io_bound(run_mask, temp_input_images, str(temp_mask_dir), update_prog)
                p_dialog.close()
                shutil.rmtree(temp_input_images)
                
                if zip_path and os.path.exists(zip_path):
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_mask_dir)
                else:
                    ui.notify("❌ Auto-Masking failed.", type='negative')
                    return

        ui.notify("⏳ Running Growth Analysis...")
        zip_path = await run.io_bound(run_graph, temp_mask_dir, str(BASE_DIR))
        
        if zip_path and os.path.exists(zip_path):
            ui.download(f'/hydro_data/{os.path.basename(zip_path)}', filename="graphs.zip")
            ui.notify("✅ Graphs ready!")
        else:
            ui.notify("❌ Growth Analysis failed (No Data).", type='negative')
            
    except Exception as e:
        ui.notify(f"Critical Error: {e}", type='negative')
    finally:
        shutil.rmtree(temp_mask_dir, ignore_errors=True)

# --- MAIN PAGE LAYOUT ---
def main_page():
    global file_list_container, image_container
    
    with ui.header().classes('bg-primary text-white shadow-lg'):
        ui.icon('eco', size='2em').classes('q-mr-sm')
        ui.label('Hydroponic System Analysis').classes('text-2xl font-bold')

    with ui.column().classes('w-full items-center gap-6 p-6 bg-gray-50 min-h-screen'):
        
        with ui.expansion('Instructions & Guide', icon='help', value=True).classes('w-full max-w-4xl bg-white rounded-lg shadow-sm'):
            with ui.list():
                ui.item('1. Upload: Drop images (Max 70MB).')
                ui.item('2. Choose: Select which pictures are wanted by selecting the check mark on each image or select all by clicking the multi-check mark at the top.')
                ui.item('3. Crop: Pick 4 points on the image and downloads them as a zip file. Active images become cropped versions.')
                ui.item('4. Mask: Converts active images to B&W masks and downloads them as a zip file.')
                ui.item('5. Growth: Analyzes the current active masks and downloads a zip file of a plot and csv file.')

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
            # --- FIX: REMOVED GREEN BORDER FROM CROP CARD ---
            with ui.card().classes('p-6 items-center hover:shadow-lg transition-shadow'):
                ui.icon('crop', size='3em', color='primary')
                ui.label('Crop Images').classes('text-lg font-bold mt-2')
                with ui.row().classes('mt-2'):
                    ui.button('Setup Cropping', on_click=lambda: show_first_image(), icon='edit').props('color=secondary')
                    ui.button('Reset Points', on_click=reset_points, icon='refresh').props('flat color=grey')

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
    ui.run(title="Hydroponic Analysis", port=8080, show=False)