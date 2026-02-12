import cv2 
import os
import numpy as np  # Required for the math
from matplotlib import pyplot as plt

test_images = [os.path.join("test_images", f) for f in os.listdir("test_images") if f.endswith(('.png', '.jpg', '.jpeg'))]

def plt_imshow(title, image, name):
    # Convert the image frame BGR to RGB color space and display it
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    plt.imshow(image)
    plt.title(title)
    plt.grid(False)
    # Added .png extension to avoid overwrite issues if needed
    plt.savefig(f"{title}_{os.path.basename(name)}.png") 
    plt.close()
def simple_white_balance(img):
    """
    Adjusts the white balance using the Gray World assumption.
    Scales R, G, B channels so they have the same average intensity.
    """
    b, g, r = cv2.split(img)
    
    # Calculate the mean of each channel
    b_mean = np.mean(b)
    g_mean = np.mean(g)
    r_mean = np.mean(r)
    
    # Calculate the average gray value of the whole image
    avg = (b_mean + g_mean + r_mean) / 3
    
    # Scale each channel to match the average
    # We clip to 0-255 to ensure pixel values remain valid
    b = np.clip(b * (avg / b_mean), 0, 255).astype(np.uint8)
    g = np.clip(g * (avg / g_mean), 0, 255).astype(np.uint8)
    r = np.clip(r * (avg / r_mean), 0, 255).astype(np.uint8)
    
    return cv2.merge([b, g, r])

# --- Main Execution ---
for image_path in test_images:
    img = cv2.imread(image_path)
    
    if img is None:
        print(f"Could not load {image_path}")
        continue

    # 1. APPLY THE CORRECTION HERE
    balanced_img = simple_white_balance(img)
    
    # Optional: Display the corrected full color image first
    plt_imshow("Corrected_Full_Color", balanced_img, image_path)

    # 2. Split the CORRECTED image, not the original
    b, g, r = cv2.split(balanced_img)
    
    # Note: I added np.mean() here so it prints the average value, 
    # rather than printing the entire array of pixels.
    print(f"Image: {image_path}")
    print(f"  Blue mean: {np.mean(b):.2f}, Green mean: {np.mean(g):.2f}, Red mean: {np.mean(r):.2f}")

    plt_imshow("Red_Channel", r, image_path)
    plt_imshow("Green_Channel", g, image_path)
    plt_imshow("Blue_Channel", b, image_path)