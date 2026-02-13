import os
import cv2
import glob
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from plantcv.parallel import WorkflowInputs
from plantcv import plantcv as pcv
import zipfile
import tempfile
import shutil


def zip_output_folder(folder: Path, zip_path: Path):
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in folder.rglob('*'):
            zipf.write(file, arcname=file.relative_to(folder))
    return str(zip_path)

def generate_mask(plant_image):
    if plant_image is None: return None
    MIN_PART_AREA = 100             
    GIANT_PLANT_RATIO = 0.03       
    MEDIUM_PART_RATIO = 0.005      
    MIN_KEEP_RATIO = 0.10          

    B, G, R = cv2.split(plant_image)
    B_f, G_f, R_f = B.astype(float), G.astype(float), R.astype(float)
    
    try:
        lab_image = cv2.cvtColor(plant_image, cv2.COLOR_BGR2LAB)
        hsv_image = cv2.cvtColor(plant_image, cv2.COLOR_BGR2HSV)
        L, _, _ = cv2.split(lab_image)
        H, _, V = cv2.split(hsv_image)
        if L.size == 0: return np.zeros(plant_image.shape[:2], dtype=np.uint8)
        l_95 = np.percentile(L, 15)
        h_90 = np.percentile(H, 10)
        v_90 = np.percentile(V, 15)
        g_90 = np.percentile(G, 100)
    except Exception:
        return np.zeros(plant_image.shape[:2], dtype=np.uint8)

    bg_sum = B_f + G_f
    _, too_bright_mask = cv2.threshold(bg_sum, 350, 255, cv2.THRESH_BINARY)
    too_bright_mask = too_bright_mask.astype(np.uint8)
    
    valid_parts_mask = cv2.bitwise_not(too_bright_mask)
    kernel_parts = np.ones((5,5), np.uint8)
    valid_parts_mask = cv2.morphologyEx(valid_parts_mask, cv2.MORPH_OPEN, kernel_parts)
    
    image_no_white_bg = cv2.bitwise_and(plant_image, plant_image, mask=valid_parts_mask)
    grayscale_no_white_bg = cv2.cvtColor(image_no_white_bg, cv2.COLOR_BGR2GRAY)
    
    contours, _ = cv2.findContours(valid_parts_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    valid_pixel_values_count = cv2.countNonZero(valid_parts_mask)
    
    final_combined_mask = None

    if valid_pixel_values_count > 0 and len(contours) > 0:
        max_contour_area = max([cv2.contourArea(c) for c in contours])
        dominance_ratio = max_contour_area / valid_pixel_values_count
        if dominance_ratio > 0.8 and (v_90 + h_90 < 75) and g_90 < 250 and l_95 < 41:
            final_combined_mask = np.ones_like(grayscale_no_white_bg) * 255
    
    if final_combined_mask is None:
        final_plant_mask_reconstructed = np.zeros_like(grayscale_no_white_bg)
        h, w = grayscale_no_white_bg.shape[:2]
        total_image_area = h * w
        rgb_sum_map = R_f + G_f + B_f
        valid_pixels = rgb_sum_map[valid_parts_mask > 0]
        if len(valid_pixels) > 0:
            p90_value = np.percentile(valid_pixels, 90)
            STRICT_BRIGHTNESS_LIMIT = min(max(500, int(p90_value)), 500)
        else:
            STRICT_BRIGHTNESS_LIMIT = 450
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < MIN_PART_AREA: continue
            part_isolation_mask = np.zeros_like(grayscale_no_white_bg)
            cv2.drawContours(part_isolation_mask, [contour], -1, 255, cv2.FILLED)
            isolated_part_rgb = cv2.bitwise_and(image_no_white_bg, image_no_white_bg, mask=part_isolation_mask)
            
            if area > (total_image_area * GIANT_PLANT_RATIO):
                B_part, G_part, R_part = cv2.split(isolated_part_rgb)
                bg_sum_part = B_part.astype(float) + G_part.astype(float) + R_part.astype(float)
                _, too_bright_strict = cv2.threshold(bg_sum_part, STRICT_BRIGHTNESS_LIMIT, 255, cv2.THRESH_BINARY)
                strict_part_mask = cv2.bitwise_and(part_isolation_mask, cv2.bitwise_not(too_bright_strict.astype(np.uint8)))
                holes_inv = cv2.bitwise_not(strict_part_mask)
                holes_inv = cv2.bitwise_and(holes_inv, part_isolation_mask)
                cnts_holes, _ = cv2.findContours(holes_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for hole in cnts_holes:
                    if cv2.contourArea(hole) < 1000:
                        cv2.drawContours(strict_part_mask, [hole], -1, 255, cv2.FILLED)
                final_plant_mask_reconstructed = cv2.bitwise_or(final_plant_mask_reconstructed, strict_part_mask)
            else:
                isolated_part_lab = cv2.cvtColor(isolated_part_rgb, cv2.COLOR_BGR2LAB)
                l_chan, a_chan, _ = cv2.split(isolated_part_lab)
                content_mask_adaptive = (l_chan > 5).astype(np.uint8) * 255
                pixel_count_total = cv2.countNonZero(content_mask_adaptive)
                if pixel_count_total > 0:
                    a_neutral = a_chan.copy()
                    a_neutral[content_mask_adaptive == 0] = 128
                    adaptive_thresh_strict = cv2.adaptiveThreshold(a_neutral, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 41, 5)
                    mask_lab = cv2.bitwise_and(adaptive_thresh_strict, content_mask_adaptive)
                    mask_lab = cv2.morphologyEx(mask_lab, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))
                    
                    B_part, G_part, R_part = cv2.split(isolated_part_rgb)
                    exg_part_raw = G_part.astype(float)*3.2 - (B_part.astype(float))-(R_part.astype(float))*1.2
                    exg_part_norm = cv2.normalize(exg_part_raw, None, 0, 255, cv2.NORM_MINMAX)
                    exg_part_uint8 = exg_part_norm.astype(np.uint8)
                    mask_exg_adaptive = cv2.adaptiveThreshold(exg_part_uint8, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 41, 15)
                    _, mask_exg_abs = cv2.threshold(exg_part_raw, 0, 255, cv2.THRESH_BINARY)
                    mask_exg = cv2.bitwise_and(mask_exg_adaptive, mask_exg_abs.astype(np.uint8))
                    mask_exg = cv2.bitwise_and(mask_exg, content_mask_adaptive)
                    mask_combined = cv2.bitwise_or(mask_lab, mask_exg)
                    pixel_count_kept = cv2.countNonZero(mask_combined)
                    keep_ratio = pixel_count_kept / pixel_count_total
                    is_medium = area > (total_image_area * MEDIUM_PART_RATIO)
                    if is_medium and keep_ratio < MIN_KEEP_RATIO:
                        final_plant_mask_reconstructed = cv2.bitwise_or(final_plant_mask_reconstructed, part_isolation_mask)
                    else:
                        final_plant_mask_reconstructed = cv2.bitwise_or(final_plant_mask_reconstructed, mask_combined)

        union_mask = final_plant_mask_reconstructed 
        inverse_mask = cv2.bitwise_not(union_mask)
        contours_holes, _ = cv2.findContours(inverse_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        MAX_GLOBAL_HOLE_SIZE = 5000
        for hole in contours_holes:
            if cv2.contourArea(hole) < MAX_GLOBAL_HOLE_SIZE:
                cv2.drawContours(union_mask, [hole], -1, 255, cv2.FILLED)
        
        bg_sum = B_f + G_f
        _, too_bright_mask_final = cv2.threshold(bg_sum, 325, 255, cv2.THRESH_BINARY)
        allowed_intensity_mask = cv2.bitwise_not(too_bright_mask_final.astype(np.uint8))
        final_combined_mask = cv2.bitwise_and(union_mask, union_mask, mask=allowed_intensity_mask)
        final_combined_mask = cv2.morphologyEx(final_combined_mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))

    return final_combined_mask

def run_mask(input_folder, output_zip_path, progress_callback=None):
    output_folder = os.path.join(tempfile.gettempdir(), "masks_temp")
    if os.path.exists(output_folder): shutil.rmtree(output_folder)
    os.makedirs(output_folder, exist_ok=True)
    image_files = sorted(glob.glob(os.path.join(input_folder, '*.*')))
    total_files = len(image_files)
    count = 0
    for idx, file in enumerate(image_files):
        if progress_callback: progress_callback((idx + 1) / total_files)
        if not file.lower().endswith(('.png', '.jpg', '.jpeg')): continue
        plant_image = cv2.imread(file)
        if plant_image is None: continue
        mask = generate_mask(plant_image)
        output_image_path = os.path.join(output_folder, f"mask{count}.png")
        cv2.imwrite(output_image_path, mask)
        count += 1
    zip_file = os.path.join(output_zip_path, "masks.zip")
    return zip_output_folder(Path(output_folder), Path(zip_file))

def run_timelapse(folder, output_path, fps, size=None):
    image_files = sorted([os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
    if not image_files: return False
    frames = []
    for path in image_files:
        img = cv2.imread(path)
        if img is not None:
            # Generate mask on fly to ensure color on black result
            mask = generate_mask(img)
            segmented = cv2.bitwise_and(img, img, mask=mask)
            frames.append(segmented)
    if not frames: return False
    if size: video_w, video_h = size
    else:
        video_h = max(f.shape[0] for f in frames)
        video_w = max(f.shape[1] for f in frames)
        if video_h % 2 != 0: video_h += 1
        if video_w % 2 != 0: video_w += 1
    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (video_w, video_h))
        for frame in frames:
            h, w = frame.shape[:2]
            canvas = np.zeros((video_h, video_w, 3), dtype=np.uint8)
            y_off = max(0, (video_h - h) // 2)
            x_off = max(0, (video_w - w) // 2)
            h_crop = min(h, video_h)
            w_crop = min(w, video_w)
            canvas[y_off:y_off+h_crop, x_off:x_off+w_crop] = frame[:h_crop, :w_crop]
            out.write(canvas)
        out.release()
        return True
    except Exception as e:
        print(f"Timelapse Error: {e}")
        return False

def run_cropping(input_folder, output_folder, roi):
    os.makedirs(output_folder, exist_ok=True)
    x, y, w, h = roi
    count = 0
    for filename in os.listdir(input_folder):
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')): continue
        filepath = os.path.join(input_folder, filename)
        image = cv2.imread(filepath)
        if image is None: continue
        img_h, img_w = image.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(img_w, x + w), min(img_h, y + h)
        if x2 <= x1 or y2 <= y1: continue
        cropped = image[y1:y2, x1:x2]
        if cropped.size == 0: continue
        cv2.imwrite(os.path.join(output_folder, filename), cropped)
        count += 1
    return count

def pixlCount(mask_folder):
    pixel_count_list = []
    extensions = ['*.png', '*.jpg', '*.jpeg']
    file_list = []
    for ext in extensions:
        file_list.extend(glob.glob(os.path.join(mask_folder, ext)))
    file_list = sorted(list(set(file_list)))
    for file in file_list:
        binary_image = cv2.imread(file, cv2.IMREAD_GRAYSCALE)
        if binary_image is None: continue
        _, binary_image = cv2.threshold(binary_image, 127, 255, cv2.THRESH_BINARY)
        count = cv2.countNonZero(binary_image)
        pixel_count_list.append(count)
    return pixel_count_list, file_list

def run_graph(input_folder, output_zip_base):
    output_folder = tempfile.mkdtemp(prefix="graphs_")
    os.makedirs(output_folder, exist_ok=True)
    
    # 1. Get raw counts and filenames
    pixels, file_names = pixlCount(input_folder)
    
    if pixels and file_names:
        # 2. Get Total Image Area to calculate percentage
        # (We read the first mask to get dimensions, assuming all images are the same size)
        first_mask = cv2.imread(file_names[0], cv2.IMREAD_GRAYSCALE)
        if first_mask is not None:
            h, w = first_mask.shape
            total_area = h * w
        else:
            total_area = 1 # Fallback to prevent division by zero
            
        # 3. Convert Raw Pixel Counts to Percentages
        percentages = [(p / total_area) * 100 for p in pixels]
        
        # 4. Zip and Sort by Percentage (Low -> High)
        combined_data = list(zip(percentages, file_names))
        combined_data.sort(key=lambda x: x[0])
        
        # Unzip back into lists
        sorted_percents, sorted_files = zip(*combined_data)
        sorted_filenames = [os.path.basename(f) for f in sorted_files]
        
        # 5. Plot
        plt.figure(figsize=(10, 6))
        plt.plot(range(len(sorted_percents)), sorted_percents, marker='o', linestyle='-', color='green')
        
        # 6. Add Axes Labels & Title (4th Grader Friendly)
        plt.title("How Much of the Picture is Plant?", fontsize=16)
        plt.xlabel("Plant Image Number", fontsize=12)
        plt.ylabel("Percentage of Plant Matter in Image (%)", fontsize=12)
        plt.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()
        
        plt.savefig(os.path.join(output_folder, "growth_plot.png"))
        plt.close()
        
        # 7. Save CSV with sorted data
        csv_path = os.path.join(output_folder, "growth_data.csv")
        df = pd.DataFrame({
            'Filename': sorted_filenames, 
            'Coverage_Percent': sorted_percents
        })
        df.to_csv(csv_path, index=False)
        
    zip_file = os.path.join(output_zip_base, "graphs.zip")
    result = zip_output_folder(Path(output_folder), Path(zip_file))
    shutil.rmtree(output_folder)
    return result