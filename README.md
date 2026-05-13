# Hydroponic System Image App (NiceGUI + Render deployment version)

This desktop app allows you to crop, create a timelapse, and mask plant images using NiceGUI and OpenCV.

## App Usage Instructions

To run this app correctly, the best way to do so is first upload a set of images to crop. About 12 images is a good starting point. 

1. **Cropping:** Once your images are uploaded, press the button to crop. The first image will appear at the top of the page. Click four points to crop the image to **ONE PLANT**, and all uploaded images (again, of one plant) will be downloaded to the browser as a zip file. Save the images to your computer and unzip the file. Then, reload the app to use the other features.

2. **Timelapse:** Upload the newly cropped images and click the timelapse button. You will get a cool timelapse video of your plant growing saved to your desktop.

3. **Masking & Growth Charts:** Make sure the cropped images are the uploaded images (reload the page if necessary). 
   * **Masking:** In order to use the growth chart button, you must first make the masks of the images (which are just a black and white version of the plant). Click the button to generate masks, download them to your browser, save them to your computer, and unzip. 
   * **Growth Charts:** Reload the page, and upload the newly generated masks. Then you can click the growth code! A zip file containing a growth graph will be downloaded to your browser. Save to your desktop, unzip, and the graph will appear on your desktop.

---

## Requirements for Setup

### Supplies Needed
* One Raspberry Pi 4 *(details on what Raspberry Pi to be supplied later)*
* USB Camera *(ask Dr. Young potentially?)*
* 3D printer
* 4 zip ties
* 4 screws *(name the size)*

---

## Raspberry Pi & Software Setup

If you are running this locally on a PC (Linux or WSL), clone this repository by running the following command in a terminal:
```bash
git clone [https://github.com/thedaisylab/UWRL-Hydroponics-GUI.git](https://github.com/thedaisylab/UWRL-Hydroponics-GUI.git)

```

### 1. Initial Device Setup

Set up the Raspberry Pi with the Raspberry Pi OS desktop version as explained in the [official documentation here](https://www.raspberrypi.com/documentation/computers/getting-started.html).

Once set up, clone this GitHub repository onto the Raspberry Pi device:

```bash
git clone [https://github.com/thedaisylab/UWRL-Hydroponics-GUI.git](https://github.com/thedaisylab/UWRL-Hydroponics-GUI.git)

```

### 2. Installing Dependencies

This project requires specific libraries to control the webcam, manipulate images, and upload them to Google Drive.

First, install the system packages and virtual environment tools:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip fswebcam -y

```

Next, create a virtual environment (we will name it `envi`) and activate it:

```bash
python3 -m venv envi
source envi/bin/activate

```

With the virtual environment activated, install the required Python libraries:

```bash
pip install google-auth google-auth-oauthlib google-api-python-client opencv-python numpy

```

*(Note: You will also need a Google Service Account JSON file saved on the Pi to authenticate with Google Drive).*

---

## Automating the Camera and Uploads

The repository includes three key files in the `Raspberry Pi code` directory to handle photo capturing and uploading:

* **`webcam.sh`**: A bash script that uses `fswebcam` to take a picture and save it with a timestamp.
* **`serviceToDrive.py`**: A Python script that undistorts the fisheye image and uploads it to a specified Google Drive folder.
* **`serviceRun.sh`**: A bash script that automatically activates the Python virtual environment and executes `serviceToDrive.py`.

*Important: Make sure to update the directory paths inside these scripts (e.g., `/home/ciroh-uwrlphoto/...`) to match the actual username and file paths on your Raspberry Pi.*

### Adding to Crontab

To automate the system so that it takes pictures and uploads them without manual intervention, you need to add the scripts to the Pi's cron scheduler.

Open the terminal and edit your crontab:

```bash
crontab -e

```

Add the following lines to the bottom of the file (be sure to replace the file paths with your actual paths):

```bash
0 6,18 * * * /path/to/your/webcam.sh 2>&1
5 18 * * *  /path/to/your/serviceRun.sh 2>&1

```

---

## Link to the Render Site

**Live Application:** [https://hydroponicssysgui.onrender.com/](https://hydroponicssysgui.onrender.com/)

```

```
