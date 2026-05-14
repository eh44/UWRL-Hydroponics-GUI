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
# --- TRACKER VARIABLES ---
limit_popup_shown = False
pending_size = 0  # Bytes currently being processed
pending_count = 0 # Files currently being processed

# --- HELPER: Get Total Size (Saved + Pending) ---
def get_total_system_usage():
    saved_size = 0
    for path_str in uploaded_file_paths:
        try:
            if os.path.exists(path_str):
                saved_size += os.path.getsize(path_str)
        except Exception: pass
    return saved_size + pending_size
# --- STYLING ---
ui.colors(primary='#4CAF50', secondary='#8BC34A', accent='#FF9800')

# --- LOGIC FUNCTIONS ---
# --- TRACKER FOR ONE-TIME WARNING ---
limit_popup_shown = False

# --- SAFE NOTIFY (Fixes "Client has been deleted" crash) ---
def safe_notify(message, **kwargs):
    try:
        ui.notify(message, **kwargs)
    except Exception:
        pass # Client disconnected, ignore error

# --- HELPER: Calculate total size ---
def get_current_total_size():
    total_bytes = 0
    for path_str in uploaded_file_paths:
        try:
            if os.path.exists(path_str):
                total_bytes += os.path.getsize(path_str)
        except Exception:
            pass
    return total_bytes
def get_current_total_size():
    total_bytes = 0
    for path_str in uploaded_file_paths:
        try:
            if os.path.exists(path_str):
                total_bytes += os.path.getsize(path_str)
        except Exception:
            pass
    return total_bytes
def copy_files_to_temp(file_paths, temp_dir):
    for src_path in file_paths:
        shutil.copy2(src_path, os.path.join(temp_dir, os.path.basename(src_path)))

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
    global limit_popup_shown, pending_size, pending_count
    
    # Reset flags if this is a fresh batch (list is empty and nothing pending)
    if not uploaded_file_paths and pending_count == 0:
        limit_popup_shown = False

    # --- 1. IMMEDIATE COUNT CHECK ---
    # Check (Existing + Pending + This one)
    if (len(uploaded_file_paths) + pending_count + 1) > 20:
        if not limit_popup_shown:
            safe_notify("⚠️ Limit Reached: Max 20 files allowed.", type='warning', closeBtn='OK', timeout=0)
            limit_popup_shown = True
        return 

    # --- PREPARE FILE INFO ---
    file_name, content_obj = get_file_info(event)
    if content_obj is None:
        if hasattr(event, 'read'): content_obj = event
        else: return 

    # --- 2. IMMEDIATE SIZE CHECK ---
    # Measure size quickly before processing
    try:
        if hasattr(content_obj, 'seek') and hasattr(content_obj, 'tell'):
            content_obj.seek(0, os.SEEK_END)
            new_file_size = content_obj.tell()
            content_obj.seek(0)
        else:
            new_file_size = 0 
    except Exception:
        new_file_size = 0

    MAX_TOTAL_SIZE = 70_000_000 # 70 MB
    
    # Check against total usage including pending files
    if (get_total_system_usage() + new_file_size) > MAX_TOTAL_SIZE:
        if not limit_popup_shown:
            space_left_mb = max(0, (MAX_TOTAL_SIZE - get_total_system_usage()) / (1024*1024))
            safe_notify(f"⚠️ Storage Full: Capacity reached ({space_left_mb:.1f} MB left).", type='warning', closeBtn='OK', timeout=0)
            limit_popup_shown = True
        return 

    # --- RESERVE SPACE ---
    pending_count += 1
    pending_size += new_file_size
    
    try:
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
            
        update_file_list_display()
        
    except Exception as e:
        safe_notify(f"Upload Error: {e}", type='negative')
        
    finally:
        # --- RELEASE RESERVATION ---
        pending_count -= 1
        pending_size -= new_file_size
        
        # --- CLEAR THE LIST WHEN BATCH IS DONE ---
        # If no more files are pending, reset the visual component
        #if pending_count == 0:
         #   event.sender.reset()
def handle_rejection(event):
    reason = event.reason if hasattr(event, 'reason') else "Max files reached"
    safe_notify(f"⚠️ File(s) rejected! {reason}", type='negative')

def reset_points():
    clicks.clear()
    if ii: ii.content = '' 
    safe_notify("🩹 Points reset. Click 4 new points.")
    show_first_image()

def revert_to_originals():
    if not original_file_paths:
        safe_notify("No originals to revert to.", type='warning')
        return
    
    uploaded_file_paths.clear()
    uploaded_file_paths.extend(original_file_paths)
    
    latest_color_paths.clear()
    latest_color_paths.extend(original_file_paths)
    
    update_file_list_display()
    safe_notify("Start over: Reverted to original images.")

def on_image_click(e: events.MouseEventArguments):
    global ii
    if len(clicks) < 4:
        color = 'SkyBlue' if e.type == 'mousedown' else 'SteelBlue'
        ii.content += f'<circle cx="{e.image_x}" cy="{e.image_y}" r="15" fill="none" stroke="{color}" stroke-width="4" />'
        clicks.append([e.image_x, e.image_y])
        if len(clicks) == 4:
            safe_notify("✅ 4 points selected! Processing crop...")
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
        safe_notify("No original files found to crop!", type='negative')
        return

    files_to_crop = 0
    for src_path in original_file_paths:
        try:
            shutil.copy2(src_path, os.path.join(temp_input, os.path.basename(src_path)))
            files_to_crop += 1
        except Exception: pass

    if files_to_crop == 0:
        safe_notify("Could not find original files on disk.", type='negative')
        return

    run_cropping(temp_input, str(CROPPED_DIR), roi)
    new_active_files = sorted([str(p) for p in CROPPED_DIR.glob('*') if p.is_file()])
    
    if new_active_files:
        uploaded_file_paths.clear()
        uploaded_file_paths.extend(new_active_files)
        
        latest_color_paths.clear()
        latest_color_paths.extend(new_active_files)
        
        safe_notify(f"✅ Active set updated to {len(new_active_files)} cropped images.")
        update_file_list_display()
        
        zip_path = BASE_DIR / "cropped_images.zip"
        with zipfile.ZipFile(zip_path, "w") as zipf:
            for fpath in new_active_files:
                zipf.write(fpath, arcname=os.path.basename(fpath))
        ui.download(f'/hydro_data/cropped_images.zip', filename="cropped_images.zip")
    else:
        safe_notify("❌ Cropping produced no images. Check ROIs.", type='negative')

    shutil.rmtree(temp_input)
    clicks.clear()
    image_container.clear() 

def show_first_image():
    global ii
    if not original_file_paths:
        safe_notify("Please upload files first", type="warning")
        return
    filename = os.path.basename(original_file_paths[0])
    image_url = f'/hydro_data/uploads/{filename}'
    image_container.clear()
    with image_container:
        ui.label("Click 4 corners of the original image to crop:").classes('text-lg font-bold text-gray-700')
        ii = ui.interactive_image(image_url, on_mouse=on_image_click, events=['click'], cross=True, sanitize=False)
        ii.classes('w-full rounded-lg shadow-md border-2 border-gray-300')
    ui.timer(0.1, lambda: image_container.run_method('scrollIntoView', {'behavior': 'smooth', 'block': 'center'}), once=True)

async def process_timelapse(fps):
    import asyncio # Ensure asyncio is imported
    source_files = latest_color_paths if latest_color_paths else uploaded_file_paths
    
    if not source_files: 
        safe_notify("No images available.", type='warning')
        return
    
    video_size = (1280, 720) 
    try:
        with Image.open(source_files[0]) as img:
            video_size = img.size 
    except Exception as e:
        safe_notify(f"Warning: Could not detect image size: {e}")

    temp_input = tempfile.mkdtemp()
    video_filename = f"timelapse_{uuid.uuid4().hex}.mp4"
    output_video_path = BASE_DIR / video_filename

    # --- LOADING DIALOG ---
    with ui.dialog() as loading_dialog, ui.card().classes('w-64 items-center'):
        ui.label(f"Generating Video ({fps} FPS)...")
        ui.spinner(size='lg')
    
    try:
        loading_dialog.open()
        # CRITICAL: Force UI to update before heavy work starts
        await asyncio.sleep(0.1) 
        
        # 1. Offload file copying (This was causing the connection lost error)
        await run.io_bound(copy_files_to_temp, source_files, temp_input)

        # 2. Offload video generation
        success = await run.io_bound(run_timelapse, temp_input, str(output_video_path), fps=fps, size=video_size)
        
        loading_dialog.close()
        
        if success:
            ui.download(f'/hydro_data/{video_filename}', filename="timelapse.mp4")
            safe_notify("🎬 Timelapse ready!")
    except Exception as e:
        loading_dialog.close()
        safe_notify(f"Error: {e}", type='negative')
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
            safe_notify("✅ Masks Generated!")
            
            if MASK_DIR.exists(): shutil.rmtree(MASK_DIR)
            MASK_DIR.mkdir()
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(MASK_DIR)
            
            new_masks = sorted([str(p) for p in MASK_DIR.glob('*') if p.is_file()])
            if new_masks:
                uploaded_file_paths.clear()
                uploaded_file_paths.extend(new_masks)
                update_file_list_display()
                safe_notify(f"🔄 Active set switched to {len(new_masks)} masks.", type='positive')
        else:
            safe_notify("❌ Masking failed (No output).", type='negative')
    except Exception as e:
        safe_notify(f"Error: {e}", type='negative')
    finally:
        shutil.rmtree(temp_input, ignore_errors=True)
        p_dialog.close()

async def process_growth():
    import asyncio # Ensure asyncio is imported
    if not uploaded_file_paths: return
    
    first_file = str(uploaded_file_paths[0])
    is_mask_set = "masks" in first_file or "mask" in Path(first_file).name.lower() or "_mask" in Path(first_file).name.lower()
    
    temp_mask_dir = tempfile.mkdtemp()
    
    # --- LOADING DIALOG ---
    with ui.dialog() as loading_dialog, ui.card().classes('w-64 items-center'):
        status_label = ui.label("Preparing Data...")
        ui.spinner(size='lg')

    loading_dialog.open()
    await asyncio.sleep(0.1) # CRITICAL: Force UI update
    
    try:
        if is_mask_set:
            status_label.set_text("Copying Masks...")
            # Offload copying
            await run.io_bound(copy_files_to_temp, uploaded_file_paths, temp_mask_dir)
        else:
            status_label.set_text("Auto-Masking Images...")
            temp_input_images = tempfile.mkdtemp()
            
            # Offload copying source images
            await run.io_bound(copy_files_to_temp, uploaded_file_paths, temp_input_images)
            
            # Run masking (this is already offloaded in your original code, which is good)
            def update_prog(ratio): 
                # Optional: You could update a progress bar here if you added one to the dialog
                pass
                
            zip_path = await run.io_bound(run_mask, temp_input_images, str(temp_mask_dir), update_prog)
            shutil.rmtree(temp_input_images)
            
            if not (zip_path and os.path.exists(zip_path)):
                 loading_dialog.close()
                 safe_notify("❌ Auto-Masking failed.", type='negative')
                 return
                 
            # Unzip (fast enough to do here, or offload if very large)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_mask_dir)

        status_label.set_text("Analyzing Growth...")
        # Force update again before the next heavy step
        await asyncio.sleep(0.1) 
        
        # Run Graph Analysis
        zip_path = await run.io_bound(run_graph, temp_mask_dir, str(BASE_DIR))
        
        loading_dialog.close()

        if zip_path and os.path.exists(zip_path):
            ui.download(f'/hydro_data/{os.path.basename(zip_path)}', filename="graphs.zip")
            safe_notify("✅ Graphs ready!")
        else:
            safe_notify("❌ Growth Analysis failed (No Data).", type='negative')
            
    except Exception as e:
        loading_dialog.close()
        safe_notify(f"Critical Error: {e}", type='negative')
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
            with ui.list().props('dense'):
                with ui.item():
                    with ui.item_section():
                        ui.markdown('**1. Upload Images:** Drag & drop images or click the plus button to browse files. (Max 20 files, 10MB per file, .jpg, .jpeg, .png files only). The "Active Images" list below shows what will be processed.')
                
                with ui.item():
                    with ui.item_section():
                        ui.markdown('**2. Crop Images (Optional):** Click "Setup Cropping". Then click the 4 corners of the grow tray on the image to crop the image. Cropped images will be downloaded as a zip file and will be used instead of the whole image for Timelapse and Growth Data.')
                with ui.item():
                    with ui.item_section():
                        ui.markdown('**3. Timelapse:** Create a timelapse video of the plant growth. Set the desired speed by using the slider to pick how many frames per second (FPS), which can be any values between 0.5 and 20 and click "Create Video". The video will be downloaded as an MP4 file.')
                
                with ui.item():
                    with ui.item_section():
                        ui.markdown('**4. Growth Data:** Click "Export Data" to generate a graph and CSV report of plant coverage over time. This will generate a downloadable Growth Graph and CSV Report, downloaded as a .zip file .')

        with ui.card().classes('w-full max-w-4xl p-6 items-center'):
            ui.label('Upload Images').classes('text-xl font-bold text-gray-700')
            upload_element = ui.upload(
                
                on_upload=save_uploaded_file, 

                on_rejected=handle_rejection,
                multiple=True, 
                auto_upload=True, 
                max_file_size=10_000_000, 
                max_files=20,
                label="Drop images here (Max 20 files, Max 10MB per file)"
            ).props('accept=".png, .jpg, .jpeg" color=primary flat bordered').classes('w-full max-w-lg')
            upload_element.add_slot('list', '<div />')
            upload_element.on('finish', lambda: upload_element.reset())
            file_list_container = ui.column().classes('w-full items-center mt-4')
            update_file_list_display()
        # --- ACTION CARDS (Steps 2, 3, 4) ---
        # Container matches Upload Card width (max-w-4xl)
        # --- ACTION CARDS (Steps 2, 3, 4) ---
        # --- ACTION CARDS (Steps 2, 3, 4) ---
        # --- ACTION CARDS (Steps 2, 3, 4) ---
        with ui.row().classes('w-full max-w-4xl justify-center gap-6 items-stretch'):
            
            # --- CARD STYLE HELPER ---
            def card_style():
                return (
                    'relative w-full md:w-[calc(50%-0.75rem)] p-6 flex flex-col items-center '
                    'bg-white rounded-lg shadow-md '               # Base: Rounded, subtle shadow
                    'border-2 border-transparent '                 # Invisible border (preserves layout)
                    'hover:border-primary hover:shadow-xl '        # Hover: Green border + Deep shadow
                    'transition-all duration-300'                  # Smooth animation
                )

            # --- 1. CROP CARD ---
            with ui.card().classes(card_style()):
                # Reset Button (Top Right)
                ui.button(icon='refresh', on_click=reset_points) \
                    .props('flat color=primary round dense').classes('absolute top-2 right-2') \
                    .tooltip('Reset Points')

                # Top Content
                ui.icon('crop', size='3.5em').classes('text-primary mb-2') 
                ui.label('Crop Images').classes('text-xl font-bold text-gray-800')
                #ui.label('Define the grow tray area').classes('text-sm text-gray-500 mb-4 text-center')
                
                # Bottom Section
                with ui.column().classes('w-full mt-auto'):
                    # Spacer to match slider height
                    ui.element('div').classes('h-[58px] w-full') 
                    
                    ui.button('Setup', on_click=lambda: show_first_image()).props('color=primary').classes('w-full')

            # --- 2. TIMELAPSE CARD ---
            with ui.card().classes(card_style()):
                # Top Content
                ui.icon('movie_creation', size='3.5em').classes('text-primary mb-2')
                ui.label('Timelapse').classes('text-xl font-bold text-gray-800')
                #ui.label('Compile images into video').classes('text-sm text-gray-500 mb-2 text-center')
                
                # Bottom Section
                with ui.column().classes('w-full mt-auto gap-2'):
                    # Slider
                    with ui.column().classes('w-full items-center bg-gray-50 p-3 rounded-md'):
                        ui.label('Playback Speed (FPS)').classes('text-xs font-bold text-gray-400 uppercase tracking-wider')
                        fps_slider = ui.slider(min=.5, max=20, value=10, step=.5).props('label-always color=primary').classes('w-full')
                    
                    ui.button('Create Video', on_click=lambda: process_timelapse(fps_slider.value)).props('color=primary').classes('w-full')

            # --- 3. GROWTH CARD ---
            with ui.card().classes(card_style()):
                # Top Content
                ui.icon('ssid_chart', size='3.5em').classes('text-primary mb-2')
                ui.label('Growth Data').classes('text-xl font-bold text-gray-800')
                #ui.label('Calculate vegetation coverage').classes('text-sm text-gray-500 mb-4 text-center')
                
                # Bottom Section
                with ui.column().classes('w-full mt-auto'):
                    # Spacer
                    ui.separator().classes('w-12 bg-gray-200 mb-4 self-center')
                    
                    ui.button('Export Data', on_click=process_growth).props('color=primary').classes('w-full')
        image_container = ui.column().classes('w-full max-w-4xl items-center mt-8 bg-white p-4 rounded-lg shadow-lg')

# --- ENTRY POINT ---
if __name__ in {"__main__", "__mp_main__"}:
    main_page()
    ui.run(title="Hydroponic Analysis", port=8080, show=False,favicon='🌱')
