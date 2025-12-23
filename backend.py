from nicegui import ui
import os
import cv2
import glob
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from plantcv.parallel import WorkflowInputs
from plantcv import plantcv as pcv
from PIL import Image
import zipfile
import tempfile
import shutil
##### BAD GROWTH #######
def zip_output_folder(folder: Path, zip_path: Path):
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in folder.rglob('*'):
            zipf.write(file, arcname=file.relative_to(folder))

def run_growth(folder, mask_folder, growth_sess,output_folder):
    # Loop through the pictures in the input directory files to do analysis
    count = 0
    image_extensions = ['*.png', '*.jpg', '*.jpeg']
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(folder, ext)))
    for name in image_files:
        # Our workflow, don't worry about this, as well as input/output options
        args = WorkflowInputs(
            images=["test.jpg"],    
            names="image1",
            result="lettuce_results",
            outdir=".",
            writeimg=True,
            debug="none",
            sample_label="genotype"
            )

    # Set debug to the global parameter 
        pcv.params.debug = args.debug

    # Set plotting size (default = 100)
        pcv.params.dpi = 100

    # Increase text size and thickness to make labels clearer
        pcv.params.text_size = 10
        pcv.params.text_thickness = 20

    # Read image in called "name", where "name" is our looping variable, which is the image we are currently looping by
        img = cv2.imread(name)

    # More specific directories used to get the image and corresponding mask to do analysis based on a time series    
    # Declare arrays and append the corresponding mask and image we are currently looping through    
        images_path_sort = []
        masks_path_sort = []
        images_path_sort.append(name)
        # This parameter is a direct copy of the line we used to save the masks to ensure we grab exactly the right mask (no typos!) 
        masks_path_sort.append(mask_folder + f"/mask{count}.png")

    # Sort the lists (will do by date automatically due to that being that being the difference in name)      
        images_path_sort = sorted(images_path_sort)
        masks_path_sort = sorted(masks_path_sort)

    # We will be using the first image in the time series to make our base roi
        i = 0
        try:
            img0,_,_ = pcv.readimage(filename=next(Path(folder).rglob('*.png')))
        except StopIteration:
            print("❌ No .png files found.")
            return
        
    # Turn the first image into LAB colorspace, which we will use to make our roi which is used for the time series analysis
        lab = cv2.cvtColor(img0, cv2.COLOR_BGR2LAB)
    # Store the a-channel
        a_channel = lab[:,:,1]
    # Automate threshold using Otsu method, which finds the green pixels and keeps them
        th = cv2.threshold(a_channel,127,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    # This is for labeling our masked objects as plants    
        pcv.params.sample_label = "plant"

    # Remove small background noise
        th_fill = pcv.fill(bin_img=th, size=200)
    # Make the roi with the th_fill mask which can identify the plants in the image
        rois = pcv.roi.auto_grid(mask=th_fill, nrows=6, ncols=3, img=img0)
    # Get the contours from the roi object, which is the number of plants (18)    
        valid_rois=rois.contours
    # Create a time series of previous images to segment the image based on previous ones to deal with the overlapping of leaves    
        out = pcv.segment_image_series(images_path_sort, masks_path_sort,  valid_rois , save_labels=True, ksize=3)
    # Take the most recent segmentation (which is a binary mask) from the output to do our analysis on    
        most_recent_slice = out[:, :, -1]

        # Measure each plant 
        shape_img = pcv.analyze.size(img=img, labeled_mask=most_recent_slice, n_labels=18)
        # Extract color data of objects and produce a histogram, in this case the RGB channel
        shape_img = pcv.analyze.color(rgb_img=img, labeled_mask=most_recent_slice, n_labels=18, colorspaces="RGB")

        # Save outputs with ALL the color and size data to a .csv file to pick apart later for each date
        print(growth_sess + '/'+args.result+ '_'+ name.split(f'{folder}/')[1].split('.')[0] + '.csv')
        pcv.outputs.save_results(filename = growth_sess + '/'+args.result+ '_'+ name.split(f'{folder}/')[1].split('.')[0] + '.csv', outformat="CSV")
        count +=1  
    # Now for grabbing the data we want from the csv files that were created for each picture and its date
    # Creates a variable from the folder from which we're getting our .csv files to mash together

    # Creating an array to hold all of our dataframes
    dfs =[]

    # Loop through all the .csv files 
    input_directory2 =growth_sess
    for file in glob.glob(os.path.join(input_directory2, '*.csv')):
        df = pd.read_csv(file, delimiter = ',')

    # Take the date out of the name
        print(file)
        date = file.split('s_')[1].split('.')[0]
        print(date)

    # Add a new column in the csv files for the date of the picture
        df['date'] = date
        df['date'] = pd.to_datetime(df['date'])
        df['date'] = df['date'].dt.date

    # Only keep the traits that aren't the red or blue frequencies
        df = df[(df['trait'] != 'red_frequencies') & (df['trait'] != 'blue_frequencies')]

    # Add the dataframe to dfs to create a large array
        dfs.append(df)
        
     # Turn our array of dfs to a csv file and save under Master.csv (can change based on where to save the file!)
    master_path = growth_sess +'/'+ 'Master.csv'
    pd.concat(dfs).to_csv(master_path, index = False)


    # Read back in our massive CSV file to make seperate smaller ones
    df = pd.read_csv(master_path)

    # Make an originally sorted copy otherwise our data will be messy because we sort later on in terms of date
    df_original = df.copy()

    # Loop through the sample (plant_1 ... plant_18) from the Master.csv file
    for plant in df_original['sample'].unique():

    # Create a plot of the green frequencies for the current plant 
        sns.lineplot(
            
    #Plot the green frequncies for every plant using the original sorting
            data=df_original[(df_original['sample'] == plant) & (df_original['trait'] == 'green_frequencies')],
            
    # These are what are going to be on our axis, label and value are found as headers in the .csv files
    # More specifically, x = 0-255 for green range, y = percentage of pixels 
            x='label',
            y='value',

    # This gives us a different graph with a different color based on the date the picture was taken
            hue='date'
        )
    # Give a title to the graph based on current plant
        plt.title(plant)

    # Move the legend to the left of the graph
        plt.legend(loc='center left', bbox_to_anchor=(1, 0.5))
        
    # Give the x and y axis a name
        plt.xlabel('Green Frequencies') 
        plt.ylabel('Percent of Pixels')
        
    
        
    # Save the plot to a folder that is named the current plant, and label it as the green frequency plot
        plt.savefig(growth_sess+f'/{plant}_green_freqs.png',  bbox_inches='tight')
        
    # Clear the plot to reset it!
        plt.clf()

    # Sort dataframe by 'date' so that the x axis is in order
        df = df.sort_values(by='date')

    # Plot a line that shows the growth in area for the current plant over the dates taken
        sns.lineplot(
            data = df[(df['sample'] == plant) & (df['trait'] == 'area')],
            x ='date',
            y= 'value'
        )
        plt.title(plant +' area')
        plt.ylabel('Area in pixels')

    # Rotate x-axis labels for better readability
        plt.xticks(rotation=45)
        
    # Save the plot to a folder that is named the current plant, and label it as the area plot
        print(growth_sess+f'/{plant}_area.png')
        plt.savefig(growth_sess+f'/{plant}_area.png',  bbox_inches='tight')
        
    # Clear the plot again to reset it
        plt.clf()
    zip_output_folder(Path(growth_sess), Path(output_folder))

##### TIMELAPSE #######
def run_timelapse(folder, output_path, fps=2.0, size=(1280, 720)):
    image_files = sorted([
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.lower().endswith(('.png', '.jpg', '.jpeg'))
    ])

    if not image_files:
        ui.notify("[ERROR] No images found.")
        return False

    frames = []
    for path in image_files:
        try:
            img = Image.open(path).convert("RGB").resize(size)
            frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            frames.append(frame)
            ui.notify(f"[✅] Loaded: {os.path.basename(path)}")
        except Exception as e:
            ui.notify(f"[⚠️] Skipping {path}: {e}")

    if not frames:
        ui.notify("[ERROR] No valid frames.")
        return False

    try:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, size)

        for frame in frames:
            out.write(frame)
        out.release()
        ui.notify(f"[🎬] Wrote timelapse to: {output_path}")
        return True
    except Exception as e:
        ui.notify(f"[❌] Failed to write video: {e}")
        return False

##### CROPPING #######
def run_cropping(input_folder, output_folder, roi):

    os.makedirs(output_folder, exist_ok=True)
    x, y, w, h = roi

    for filename in os.listdir(input_folder):
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
        filepath = os.path.join(input_folder, filename)
        image = cv2.imread(filepath)
        if image is None:
            ui.notify(f"⚠️ Could not read: {filename}")
            continue

        cropped = image[int(y):int(y + h), int(x):int(x + w)]
        if cropped.size == 0:
            print(f"❌ Empty crop for: {filename}")
            continue

        output_path = os.path.join(output_folder, filename)
        cv2.imwrite(output_path, cropped)
        print(f"✅ Cropped and saved: {filename}")

##### MASKING #######
def run_mask(input_folder, output_zip_path):
    # ui.notify(f"[MASK] Running on folder: {input_folder}")
    count = 0
    output_folder = os.path.join(tempfile.gettempdir(), "masks")
    os.makedirs(output_folder, exist_ok=True)

    image_extensions = ['*.png', '*.jpg', '*.jpeg']
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(input_folder, ext)))

    for file in image_files:
        img = cv2.imread(file)
        hsv_image = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        lower_brown = np.array([10, 100, 20])
        upper_brown = np.array([20, 255, 200])
        lower_black = np.array([0, 0, 0])
        upper_black = np.array([180, 255, 50])
        lower_black2 = np.array([100, 59, 20])
        upper_black2 = np.array([123, 140, 236])

        black_mask = cv2.inRange(hsv_image, lower_black, upper_black)
        black2_mask = cv2.inRange(hsv_image, lower_black2, upper_black2)
        brown_mask = cv2.inRange(hsv_image, lower_brown, upper_brown)

        combined_mask = black2_mask | black_mask | brown_mask
        inverted_mask = cv2.bitwise_not(combined_mask)

        kernel = np.ones((3, 3), np.uint8)
        for i in range(4):
            if i == 0:
                eroded = cv2.erode(inverted_mask.copy(), kernel, iterations=i + 1)
            else:
                eroded = cv2.erode(dilated.copy(), kernel, iterations=i + 1)
            dilated = cv2.dilate(eroded.copy(), kernel, iterations=i + 1)
        filename = Path(file).stem 
        output_image_path = os.path.join(output_folder, f"{filename}_mask.png")
        cv2.imwrite(output_image_path, eroded)
        count += 1

    zip_path = os.path.join(output_zip_path, "masks.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for fname in os.listdir(output_folder):
            fpath = os.path.join(output_folder, fname)
            zipf.write(fpath, arcname=fname)

    ui.notify(f"✅ Masking complete! Zip saved to: {zip_path}")
    shutil.rmtree(output_folder)
    return zip_path


##### GRAPHING #######
def fill_holes2(binary_image):
    """Fill holes inside binary mask."""
    h, w = binary_image.shape[:2]
    mask = np.zeros((h+2, w+2), np.uint8)

    # ensure strictly binary 0/255 uint8
    _, binary_image = cv2.threshold(binary_image, 127, 255, cv2.THRESH_BINARY)
    binary_image = binary_image.astype(np.uint8)

    cv2.floodFill(binary_image, mask, (0, 0), 255)
    mask = cv2.bitwise_not(mask)
    return mask


def get_largest_blobs(binary_image, num_blobs):
    """Extract the N largest connected components from a binary mask."""
    # --- safety: ensure grayscale, binary, and uint8 ---
    if len(binary_image.shape) == 3:
        binary_image = cv2.cvtColor(binary_image, cv2.COLOR_BGR2GRAY)
    _, binary_image = cv2.threshold(binary_image, 127, 255, cv2.THRESH_BINARY)
    binary_image = binary_image.astype(np.uint8)

    # find connected components
    num_comps, output, stats, centroids = cv2.connectedComponentsWithStats(
        binary_image, connectivity=8
    )

    sizes = stats[1:, -1]
    nb_components = num_comps - 1

    blob_indices = np.argsort(sizes)[::-1][0:num_blobs]

    aggregate_img = np.zeros((binary_image.shape[0], binary_image.shape[1], num_blobs))
    centroid_list = centroids[blob_indices + 1]

    for i in range(num_blobs):
        img2 = np.zeros(output.shape, dtype=np.uint8)
        img2[output == blob_indices[i] + 1] = 255
        img2 = fill_holes2(img2) == 255
        aggregate_img[:, :, i] = img2[:-2, :-2]  # crop floodfill padding

    return aggregate_img, centroid_list


def pixlCount(mask_folder):
    """Count pixels in the largest blob of each mask in a folder."""
    pixel_count_list = []
    file_list = sorted(glob.glob(os.path.join(mask_folder, '*')))

    for file in file_list:
        # --- load mask in grayscale (1 channel) ---
        binary_image = cv2.imread(file, cv2.IMREAD_GRAYSCALE)

        # --- force binary 0/255 ---
        _, binary_image = cv2.threshold(binary_image, 127, 255, cv2.THRESH_BINARY)
        binary_image = binary_image.astype(np.uint8)

        aggregate_img, cen = get_largest_blobs(binary_image, 1)
        per_blob_counts = np.count_nonzero(aggregate_img[:, :, 0])
        pixel_count_list.append(per_blob_counts)

    return pixel_count_list


def graph(mask_folder, pixels, output_path):
    """Plot growth curve from pixel counts and save as PNG."""
    file_list = sorted(glob.glob(os.path.join(mask_folder, '*')))
    file1 = Path(file_list[0]).stem
    lastfile = Path(file_list[-1]).stem

    days = [f'Day {i+1}' for i in range(len(pixels))]
    plt.figure(figsize=(10, 5))
    plt.plot(days, pixels, marker='o')
    plt.xlabel(f"{file1.split('_mask')[0]} - {lastfile.split('_mask')[0]}")
    plt.ylabel("Plant Pixel Count")
    plt.title("Plant Area")
    plt.grid(True)
    plt.tight_layout()

    output_path = Path(output_path)
    plt.savefig(output_path)
    plt.close()


def run_graph(input_folder, output_zip_base):
    """Run pixel counting + graphing, zip results, and return path."""
    output_folder = tempfile.mkdtemp(prefix="graphs_")
    os.makedirs(output_folder, exist_ok=True)

    pixels = pixlCount(input_folder)
    output_image_path = os.path.join(output_folder, "growth_plot.png")
    graph(input_folder, pixels, output_image_path)

    zip_path = os.path.join(output_zip_base, "graphs.zip")
    with zipfile.ZipFile(zip_path, "w") as zipf:
        for fname in os.listdir(output_folder):
            fpath = os.path.join(output_folder, fname)
            zipf.write(fpath, arcname=fname)

    ui.notify(f"✅ Graphing complete! Zip saved to: {zip_path}")
    shutil.rmtree(output_folder)
    return zip_path