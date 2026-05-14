# Hydroponic System Image App (NiceGUI + Render deployment version)
This desktop app allows you to crop, timelapse, and mask plant images using NiceGUI and OpenCV.

To run this app correctly, the best way to do so is first uploads a set of images to crop. About 12 images is good. Once those images are uploaded, and you press the button to crop, the first image will appear at the top of the page. Click four points to crop the image to ONE PLANT, and all uploaded images (again, of one plant) will be downloaded to the browser. Save images to your computer and open zip file.

Then, reload the app to work use the other buttons.

Timelapse: Upload the cropped images and click the timelapse button. You will get a cool timelapse video of your plant growing saved to your desktop.

Growth charts: Make sure the cropped images are the uploaded images (reload page if necessary). In order to use the growth chart button, you must first make the masks of the images (which are just a black and white version of the plant). Then masks will be downloaded to the browser, save to computer and unzip. Reload the page, and upload the masks. Then you can click the growth code! A zip file with a growth graph will be downloaded to the browser. Save to desktop, unzip, and the graph will appear on the desktop!

**Important Note on Masking (Segmentation):** The image segmentation algorithm used to generate these black-and-white masks is currently tuned specifically for our lab's lighting and setup. Because different locations have different lighting, backgrounds, and shadows, you will need to customize the segmentation code for your own project environment to ensure the masks capture the plants accurately.

Requirements for set up
Supplies needed
One Raspberry Pi 4 with power supply
A USB camera with a fish eye lens
3d printer
4 zip ties
4 screws that fit in the Raspberry Pi

Clone this repository by running the following command in a terminal, preferably in linux or WSL
```bash
git clone [https://github.com/thedaisylab/UWRL-Hydroponics-GUI.git](https://github.com/thedaisylab/UWRL-Hydroponics-GUI.git)

```

Set up the raspberry pi with the desktop version as explained here: https://www.raspberrypi.com/software/
Once set up, clone this GitHub on the device by using git clone link here:

```bash
git clone [https://github.com/thedaisylab/UWRL-Hydroponics-GUI.git](https://github.com/thedaisylab/UWRL-Hydroponics-GUI.git)

```

### Setting up Google Cloud and the Service Account

Before automating the Raspberry Pi, you need a place in the cloud to store the images and a "Service Account". A Google Service Account is intended to represent a non-human user. In this system, it acts as the "identity" for your Raspberry Pi. It uses a downloaded key (a JSON file) to securely authenticate in the background, allowing your Pi to deposit images directly into your Google Cloud Storage Bucket without requiring a human to log in.

**1. Create a Project and Storage Bucket:**

1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and log in.
2. Click the project drop-down menu near the top-left and select **New Project**. Name it and click **Create**. Ensure this new project is selected.
3. In the search bar at the top, type **Buckets** and click on the Cloud Storage Buckets page.
4. Click **Create**.
5. Give your bucket a globally unique name. **Write this name down; you will need it later.**
6. Choose a Region (e.g., `us-west1`), leave the storage class as **Standard**, and click **Create**.

**2. Create the Service Account:**

1. In the top search bar, type **Service Accounts** and navigate to that page.
2. Click **Create Service Account**.
3. Name it (e.g., `pi-bucket-uploader`) and click **Create and Continue**.
4. Under "Select a role", search for **Storage Object Admin** (this gives it permission to put files in the bucket). Select it, and click **Done**.

**3. Generate and Download the Key:**

1. Click on the email address of the Service Account you just created.
2. Go to the **Keys** tab.
3. Click **Add Key** > **Create new key**.
4. Select **JSON** and click **Create**.
5. A `.json` file will download to your computer. Keep this highly secure. Transfer this file to your Raspberry Pi, place it in the `Raspberry Pi code/` folder, and rename it to `credentials.json`.

*(Important: Add `credentials.json` to your `.gitignore` file so you do not accidentally publish your private database keys to GitHub).*

Update your Python script (`serviceToDrive.py`) to point to the absolute path of this file:

```python
import os
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/YOUR_PI_USERNAME/UWRL-Hydroponics-GUI/Raspberry Pi code/credentials.json"

```

### Testing and Adjusting Camera Parameters

Depending on the lighting in your specific environment, the default camera settings might result in images that are too dark or too washed out. You can visually test and change your camera parameters using a tool called `qv4l2`.

1. Open your Raspberry Pi terminal and install the tool by running:
```bash
sudo apt install qv4l2 -y

```


2. Open the application by typing `qv4l2` into the terminal and pressing **Enter**.
3. A graphical window will open showing a live feed of your camera. Use the sliders to adjust settings like brightness, contrast, and exposure until the picture looks ideal for your setup.
4. Take note of the exact numerical values you changed. You will then need to open your `webcam.sh` script and update the `fswebcam` command parameters to include those specific changes so the automated camera uses them every time it takes a photo.

### Automating the Camera

Add the following to cron.tab by going to the cron.tab items. Open the cron scheduler by typing this into the terminal:

```bash
crontab -e

```

And put the file path of the three files here (scroll to the bottom of the file and paste these, making sure to replace `YOUR_PI_USERNAME` with your actual Pi username):

```bash

@reboot /home/YOUR_PI_USERNAME/UWRL-Hydroponics-GUI/Raspberry\ Pi\ code/set_camera.sh 2>&1

0 6,18 * * * /home/YOUR_PI_USERNAME/UWRL-Hydroponics-GUI/Raspberry\ Pi\ code/webcam.sh 2>&1

5 18 * * * /home/YOUR_PI_USERNAME/UWRL-Hydroponics-GUI/Raspberry\ Pi\ code/serviceRun.sh 2>&1

```

### Deploying the Web App to Render

This project includes a `render.yaml` configuration file, which allows you to easily host the web application for free on Render.com.

1. Go to [Render](https://render.com/) and create a free account.
2. From your Render Dashboard, click the **New +** button and select **Blueprint**.
3. Connect your GitHub account and select your `UWRL-Hydroponics-GUI` repository.
4. Render will automatically read the `render.yaml` file and configure everything for you: it will select the free python environment tier, install the required packages (`pip install -r requirements.txt`), and start the app (`python3 main.py`) on port `8080`.
5. Click **Apply**. Render will build your site and provide you with a live URL.

Link to the Render site
https://hydroponicssysgui.onrender.com/

```

```
