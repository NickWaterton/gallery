# Overview

This is a web front end for art display on Frame TV's, for use in Art Galleries.

it is intended to be run on a Raspberry Pi, with a display connected to one (or both) HDMI outputs.

**Minnimmun Python Version is 3.10**

## Raspberry Pi Configuration

### Hardware

You should prepare a Rasberry Pi 5 or 4B+ with dual HDMI ports.
* HDMI-1 (nearest to the USB-C port) should be connected to a Waveshare 11.9" LCD Display or similar https://www.waveshare.com/wiki/11.9inch_HDMI_LCD This wil be the "caption" display.
* HDMI-2 can be optionally connected to another touch screen such as https://www.waveshare.com/15.6inch-hdmi-lcd-h-with-case.htm or similar

Other Pi's with single HDMI ports should work as well, in which case the caption display should be connected to HDMI-1.

### OS

The reccomended OS is the latest Raspeberry Pi 64 bit OS Full (including UI). You should not use the OS lite.  
The OS should be set up to connect to WiFi (unless you are using a wired connection) with SSH enabled. 
**Python 3.10** is required, so do not use earlier versions of Pi OS.

### Software Configuration

Once the base OS has been installed, you should log in via SSH and configure as follows:  
```
sudo apt update
sudo apt full-upgrade
sudo apt autoremove
sudo reboot
```
Then log back in again.
Now edit `/boot/firmware/cmdline.txt` (use nano) and add:
```
video=HDMI-A-1:320x1480,rotate=90
```
To the end of the command line. Save and exit. it should look somethig like this:
```
console=serial0,115200 console=tty1 root=PARTUUID=a6e52f88-02 rootfstype=ext4 fsck.repair=yes rootwait quiet splash plymouth.ignore-serial-consoles cfg80211.ieee80211_regdom=CA video=HDMI-A-1:320x1480,rotate=90
```

Install the following packages (if not already installed):
```
sudo apt install git chromium-browser
```
and clone this repository (you may want to create a subdirectory first, such as `Scripts`, and clone into that).
```
md Scripts
cd Scripts
git clone https://github.com/NickWaterton/gallery.git
```
On a raspberry Pi, you need to either create a virtual environment to run the python programs in, or delete the `EXTERNALLY_MANAGED` file as described here https://learn.adafruit.com/python-virtual-environment-usage-on-raspberry-pi
If you don't care about breaking system packages:
```bash
sudo rm /usr/lib/python3.11/EXTERNALLY-MANAGED
```
**NOTE:** If you don't create the virtual environment, or delete the `EXTERNALLY-MANAGED` file, `pip` will be unable to install any python packages, and you will get lots of errors.

Now, cd to the `gallery` folder you just cloned, and use the helper scripts to set up the console display:
```
cd Scripts/gallery
rotate_screen_90.sh
```
If you only have the one caption display, also hide the cursor:
```bash
hide_cursor.sh
```
And reboot. The Pi screen should now display on the caption display in the correct orientation.  
You can test the screen using the utility script `screen.sh`:
```
./screen.sh off
./screen.sh on
```
and the utility `wlr-randr` should display:
```
nick@raspberrypi:~/Scripts $ wlr-randr
HDMI-A-1 "HOT WaveShsare 0x00000001 (HDMI-A-1)"
  Enabled: no
  Modes:
    1280x720 px, 100.000000 Hz
    320x1480 px, 59.324001 Hz (preferred)
NOOP-1 "Headless output 2"
  Enabled: yes
  Modes:
    1920x1080 px (current)
  Position: 0,0
  Transform: normal
  Scale: 1.000000
```
You may show two HDMI screens if you have two displays connected.  
You now need to install the **samsung-tv-ws-api** package as described here https://github.com/NickWaterton/samsung-tv-ws-api/tree/master  
Make sure you cd to your `Scripts` directory first, do **NOT** install it in the gallery folder.

```
cd ~/Scripts
git clone https://github.com/NickWaterton/samsung-tv-ws-api.git
cd samsung-tv-ws-api
sudo pip install --editable .
```
Don't miss the `.` after `--editable`!

Your Scripts folder should now look like this:
```
nick@raspberrypi:~/Scripts $ ls -l
total 8
drwx------ 5 nick nick 4096 Apr  1 15:22 gallery
drwxr-xr-x 9 nick nick 4096 Mar 29 15:23 samsung-tv-ws-api
```
Make sure you have installed the `samsung-tv-ws-api` package without errors before proceeding.

Continue with the gallery program set up as described below.

## Install

### Install additional packages

There are additional packages required to support the web framework, to install them, change to this directory and run:
```
cd gallery
pip install -r requirements.txt
```
This is *after* you have installed the `samsungtvws` package as described on the above. `pip` may be `pip3` on your system.

### Updating

If there are updates published to either the `samsung-tv-ws-api` or `gallery` package github, just change to the appropriate directory and run `git pull`:  
```
cd gallery
git pull
```

No need to reinstall anything, unless told to do so.

## Usage

### Basic

The entry point is `web_interface.py`, the other files are resources used by the web interface. The command line options are:
```
nick@raspberrypi:~/Scripts/gallery $ ./web_interface.py -h
usage: web_interface.py [-h] [-p PORT] [-f FOLDER] [-m MATTE] [-t TOKEN_FILE] [-u UPDATE] [-c CHECK] [-d DISPLAY_FOR]
                        [-mo {modal-sm,modal-lg,modal-xl,modal-fullscreen,modal-fullscreen-sm-down,modal-fullscreen-md-down,modal-fullscreen-lg-down,modal-fullscreen-xl-down,modal-fullscreen-xxl-down}]
                        [-th {None,cerulian,cosmo,cyborg,darkly,flatly,journal,litera,lumen,lux,materia,minty,morph,pulse,quartz,sandstone,simplex,sketchy,slate,solar,spacelab,suerhero,united,vapour,yeti,zephyr,dark}]
                        [-ph PHOTOGRAPHER] [-sf] [-s] [-K] [-P] [-A] [-S] [-O] [-F] [-X] [-D]
                        ip

Async Art gallery for Samsung Frame TV Version: 2.0.0

positional arguments:
  ip                    ip address of TV (default: None))

options:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  port for web page interface (default: 5000))
  -f FOLDER, --folder FOLDER
                        folder to load images from (default: ./images))
  -m MATTE, --matte MATTE
                        default matte to use (default: none))
  -t TOKEN_FILE, --token_file TOKEN_FILE
                        default token file to use (default: token_file.txt))
  -u UPDATE, --update UPDATE
                        slideshow update period (mins) 0=off (default: 0))
  -c CHECK, --check CHECK
                        how often to check for new art 0=run once (default: 600))
  -d DISPLAY_FOR, --display_for DISPLAY_FOR
                        how long to display manually selected art for (default: 120))
  -mo {modal-sm,modal-lg,modal-xl,modal-fullscreen,modal-fullscreen-sm-down,modal-fullscreen-md-down,modal-fullscreen-lg-down,modal-fullscreen-xl-down,modal-fullscreen-xxl-down}, --modal {modal-sm,modal-lg,modal-xl,modal-fullscreen,modal-fullscreen-sm-down,modal-fullscreen-md-down,modal-fullscreen-lg-down,modal-fullscreen-xl-down,modal-fullscreen-xxl-down}
                        size of modal text box see https://www.w3schools.com/bootstrap5/bootstrap_modal.php for explanation (default: medium)
  -th {None,cerulian,cosmo,cyborg,darkly,flatly,journal,litera,lumen,lux,materia,minty,morph,pulse,quartz,sandstone,simplex,sketchy,slate,solar,spacelab,suerhero,united,vapour,yeti,zephyr,dark}, --theme {None,cerulian,cosmo,cyborg,darkly,flatly,journal,litera,lumen,lux,materia,minty,morph,pulse,quartz,sandstone,simplex,sketchy,slate,solar,spacelab,suerhero,united,vapour,yeti,zephyr,dark}
                        theme to apply to display (default: None))
  -ph PHOTOGRAPHER, --photographer PHOTOGRAPHER
                        default photographer to use (default: Paul Thompsen))
  -sf, --serif_font     use Serif Font for caption display (default: False))
  -s, --sync            automatically syncronize (needs Pil library) (default: True))
  -K, --kiosk           Show in Kiosk mode (default: False))
  -P, --production      Run in Production server mode (default: False))
  -A, --art_mode        Ensure TV stays in art mode (except when off) (default: False))
  -S, --sequential      sequential slide show (default: False))
  -O, --on              exit if TV is off (default: False))
  -F, --favourite       include favourites in rotation (default: False))
  -X, --exif            Use Exif data (default: True))
  -D, --debug           Debug mode (default: False))
```
The ip address of your TV is required, the rest of the command line is optional.  
Here is a basic example:
```
./web_interface.py 192.168.100.32 -u 1 -d 30
```
Where `192.168.100.32` is *your* TV ip address.  
This will start the interface to the frame TV with ip address 192.168.100.32, automatically updating the displayed image every 1 minutes, and if an image is selected from the web interface, it will be displayed for 30 seconds, before the rotation resumes.  
To view the web interface, open a browser and navigate to:
```bash
http://<ip>:5000
```
Where ip is the ip address of the Pi running the server (**NOT** the TV).  

you should see a screen similar to this:
![User interface](screens/user.png?raw=true "User interface")

If you don't see a modal display window, you may have started the server in `Display` mode, not `Kiosk` mode. The Modal window only appears automatically in `Kiosk` mode.

The caption display (if used) should automatically start up, and show the details of the currently displayed image. If you have a second display connected to HDMI-2, the web interface will automatically start on the second display.  
It should look like this:  
![Caption Display](screens/caption2.png?raw=true "Caption Display")

A more typical command line would be:
```
./web_interface.py 192.168.100.32 -u 1 -d 30 -m modal-xl -ph "<your name>" -P -K
```
Which would start the server in `kiosk` mode (modal window displays details of the current image automatically), with the modal window set to extra-large size, and server `production` mode.  
**NOTE:** you *do* need the `"` around your name, if you have spaces in the name, ie `"Nick Waterton"`.

### Touch/Mouse Interface

On the user Interface screen, clicking or touching anywhere outside the modal display window, or the `X` in the top right hand corner will close the window, and allow you to select another imge. Just click or touch on the image button, and a new modal display window will appear. The TV and caption display will update with the new image in a few seconds.  

If you are using a touch display, you may have to calibrate the touch interface. The caption display does not use a touch interface.

### Advanced

The Web interface supports *themes* selected using the `-th` option, you can select a theme as follows:
```
./web_interface.py 192.168.100.32 -u 1 -d 30 -m modal-xl -ph "<your name>" -th cyborg -P -K
```
Where `cyborg` is a dark theme. The theme names are one of:  
`cerulian,cosmo,cyborg,darkly,flatly,journal,litera,lumen,lux,materia,minty,morph,pulse,quartz,sandstone,simplex,sketchy,slate,solar,spacelab,suerhero,united,vapour,yeti,zephyr,dark`

You can checkout what the themes look like here https://bootswatch.com/

**NOTE:** `dark` is not really a theme, when selected it just switches the caption display to white text on a black background.

The font family used on the caption display can be switched from the usual sans-serif font, to a serif font using the `-sf` switch. 

### Shut Down

Use `<cntl>C` to exit the web server, it takes a few seconds to shut down. The modal window (if any) will be removed.

### Automatic Start

To automatically start the server when the Pi boots, the best way is to use *systemd*. You can read all about it here https://www.thedigitalpictureframe.com/ultimate-guide-systemd-autostart-scripts-raspberry-pi/ and I have included an exaple `gallery.service` file for you to use.

To use the example `gallery.service` file, first edit it to customise the `ExecStart` command line:
```
[Unit]
Description=Gallery
After=graphical.target
Requires=network.target

[Service]
Type=idle
User=nick
UMask=0000
Environment="XDG_RUNTIME_DIR=/run/user/1000"
WorkingDirectory=/home/nick/Scripts/gallery
ExecStart=/home/nick/Scripts/gallery/web_interface.py 192.168.100.32 -u 1 -d 30 -f /home/nick/Scripts/gallery/images -mo modal-xl -ph "Nick Waterton" -K -P
Restart=always
RestartSec=10

[Install]
WantedBy=graphical.target
```
Replace the defaults with your tv IP address, the location of your images directory, and your name. Now copy the file to the `/etc/systemd/system` directory:
```
sudo cp gallery.service /etc/systemd/system
sudo chmod 644 /etc/systemd/system/gallery.service
```
And re-initialise the systemctl daemon:
```
sudo systemctl daemon-reload
```
You can now start and stop the gallery server using the commands:
```
sudo systemctl start gallery.service
sudo systemctl stop gallery.service
sudo systemctl status gallery.service
```
And to see the logs:
```
journalctl -u gallery.service -o cat -f
```

to enable auto starting of the service on boot:
```
sudo systemctl enable gallery.service
```
And to disable it:
```
sudo systemctl disable gallery.service
```

if you edit the file, don't forget to run `sudo systemctl daemon-reload`.


## Caption Display

The caption display is optimized for a 320x1420 landscape display (so 1420 wide, 320 high). The following information is displayed center-justified on it:
* Title
* Location
* Photographer month and year of photograph
* Camera model and lens focal length
* camera shutter speed, f-stop and ISO settings

On the Waveshare 11.9" display, the maximum line legth is about 40 characters for the title (the largest font), and I reccomend that the backlight brightness be turned down (by long pressing the power on button several times). 

It should look like this:  
![Caption Display](screens/caption.png?raw=true "Caption Display")

## TV is off or playing

If the TV turns off, or starts playing TV, the modal image will be removed, and clicking the buttons will do nothing.  
When the TV is switched to art Mode, the image updating will resume, and modal windows will be displayed again.

You can choose to keep the TV in art mode, by using the `-A` switch. In this case, you can turn the TV off, but if the the TV switches to playing (as it sometimes randomly does from art mode), then it will be switched back to art mode in a few seconds.

If you turn the TV off, then the attached caption and display screens will also turn off. They will turn back on when the TV is turned back on again.

## Internet

I do not reccomend exposing the web interface to the internet, this is just an example interface, it is **NOT** secure. If you **must** expose it, ensure you only use Production mode `-P` option, and do not expose your `images` directory.

## Typical Use

This interface is intended to be used in a Gallery, so that visitors can see information on the displayed image, or select their own. Typically, you would have this running on a small computer, such as a Raspberry Pi, with a touch screen in `Kiosk` mode.  
if you use a tablet or other device to display the user interface, and not an attached HDMI screen, you should set it up in a *kiosk mode* (**Note:** This is not the same as the `-K` `Kiosk` mode command line seting):  

Examples of kiosk mode for RPI:  
* https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode
* https://github.com/debloper/piosk

### Modes of Operation

There are two main modes of operation, display mode and Kiosk mode. Display mode is the default, Kiosk mode is enabled with the `-K` switch.

#### Display Mode

In Display mode, the images in the `./images` folder (or whatever folder you have selected using the `-f` option) will be displayed as buttons on the web interface. Clicking on one of the buttons will display the image on the TV (assuming the TV is in art mode).  

If you have created a text file to describe the image, or exif tags exist that do the same, the description will appear in a modal window. After the preset time, (option `-d`) the automatic rotation will resume.

#### Kiosk Mode

In `Kiosk` mode, the images will be displayed in rotation as before, but for each image displayed, the text box describing the currently displayed image will automatically appear.  
You can still close the text box, and select a new image the same way as in display mode.  
This is the command line for `Kiosk` mode
```
./web_interface.py 192.168.100.32 -u 1 -d 30 -K
```
Where `192.168.100.32` is *your* TV ip address, and `-K` is the option for `Kiosk` mode.

## Text Files

You can create text files to describe the associated image - this imformation will appear in a modal window, when the image is clicked, or automatically in Kiosk mode.

### Naming  

The text file has to be given the same name as the image file, with a `.TXT` or `.txt` extension. See the `images` folder for examples.

### Format

The text files are in json format, with the following layout:
```json
{   
    "header"        : "Crimson Finch at Fogg Dam",
    "description"   : "<i>Neochmia phaeton</i>",
    "details"       : "The <b>Crimson Finch</b> is a species of bird in the family <i>Estrildidae</i>. It is found throughout Northern Australia as well as parts of southern New Guinea.<br>Crimson finches feature a distinctively bright crimson coat and are known for their aggression.",
    "time"          : "",
    "location"      : "",
    "credit"        : "wildfoto.au",
    "caption"       : "Crimson Finch at Fogg Dam",
    "photographer"  : "Paul Thompsen" 
}
```
The only mandatory fields are `"header"` and `"details"`, the rest are optional.  
The `"description"` and `"details"` fields support inline html, so italic `<i>`, bold `<b>` line break `<br>` etc are supported as shown in the example above.  

### Missing TXT file

If a `.TXT` or `.txt` is not found, and the Exif Tags for `ImageTitle` or `ImageDescription` are not present, then no modal information box is displayed. 

## EXIF tags

If the Exif tags for `ImageTitle` or `ImageDescription` are present, these will be used on the modal information window, and caption display.

**NOTE:** The values in a `.TXT` file if present will always override the values in the Exif tags.

If the image has embedded exif information, the `"location"` and `"time"` fields will be filled in automatically if exif tags `DateTimeOriginal` and `GPSInfo` are available.  

**NOTE:** If you enter details for `"time"` and `"location"` in the text file, then the exif data will not overwrite this information.  
**NOTE:** There are rate limits on the free geolocating api, so loading large amounts of GPS info will be slow, and you should read the acceptible use policy at: https://operations.osmfoundation.org/policies/nominatim/ GPS addresses are cached locally in the file `gps_info.json` to reduce hits on the server.  

The mapping of the fields in the `.TXT` file to Exif tags is as follows:
```
"header"        : ImageTitle or ImageDescription or XPTitle
"description"   : XPSubject or ImageDescription
"details"       : UserComments or XPComment
"time"          : DateTimeOriginal
"location"      : GPSInfo
"credit"        : Copywrite
"caption"       : ImageTitle or ImageDescription or XPTitle
"photographer"  : Photographer or Artist or XPAuthor
```
If `ImageDescription` is used for both `header` and `description` then `description` will not be displayed.

**NOTE:** The *XP* tags are the tags that can be edited in Windows under `properties->details`, as "Title', "Subject", "Comments", and "Authors". Additionally "Copywrite" and "DateTimeOriginal" can be edited.  
Like this:  
![Windows Edit](screens/windows.png?raw=true "Windows Edit")

This means that it is possible to edit this information on the `.jpg` files in Windows, and thus not need a `.TXT` file at all. If you are having other people submit photographs for your gallery, you should have them edit this information into the files first.

If you use and like this library for art mode, [Buy me a coffee](https://paypal.me/NWaterton).
