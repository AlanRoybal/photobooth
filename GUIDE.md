# Photobooth build guide

Order: buy the missing parts, assemble, flash the SD card, deploy AWS (Agent A), set up the Pi (Agent B), make frames (Agent C), install frames (Agent D).

## 1. Parts you still need

| Part | Why |
|---|---|
| Raspberry Pi 5 camera cable, 22-pin to 15-pin (200 mm or 300 mm) | The Pi 5 camera port is smaller than the one the Arducam cable fits. Skip if your Arducam box already has a cable with one narrow end. |
| Raspberry Pi 5 Active Cooler | The Pi runs the camera and browser all day and will throttle without it. |
| Phone hotspot or travel router | Venue Wi-Fi usually blocks devices from talking to each other, so the Pi can't find the printer. Put the Pi, printer, and your laptop on the same hotspot. The SELPHY only does 2.4 GHz, so on iPhone turn on Settings > Personal Hotspot > Maximize Compatibility. |
| microSD card reader for your laptop | To flash the SD card. |
| Something to mount the camera above the screen | Tape, a 3D printed bracket, or a box. |

The Hosyond screen comes with an HDMI adapter and a USB cable. You'll use your Cable Matters micro HDMI cable for video and the Hosyond USB cable for touch and screen power.

## 2. Assemble

Do all of this with nothing plugged into power.

1. **Cooler.** Peel the thermal pads' film, press the Active Cooler onto the Pi until the two spring pins click into the holes, and plug its 4-pin fan cable into the FAN connector near the USB-C port.
2. **Camera cable at the Pi.** Use the port labeled CAM/DISP 0. Gently pull the dark latch up, slide in the narrow end of the cable as far as it goes, and push the latch down. Look into the slot first: the metal pins are on one side, and the cable's gold contacts must face those pins.
3. **Camera cable at the camera.** Same thing on the Arducam: lift the latch, insert the wide end with the gold contacts facing the connector's pins, close the latch. Tug lightly on both ends. Nothing should move.
4. **Screen.** Micro HDMI cable from the Pi's HDMI 0 port (the one closest to the USB-C power port) to the screen's HDMI. Hosyond USB cable from the screen's Touch port to any USB port on the Pi. This carries touch and powers the screen.
5. **Mount.** Put the camera centered just above the top edge of the screen, tilted slightly down, lens around head height for the people using it. The on-screen arrow points to the top center of the screen. If the camera ends up off-center, tell Agent B and it will move the arrow.
6. **Printer.** Load the RP-108 ink cassette and up to 18 sheets in the tray (glossy side up, don't touch it). Power it on.
7. **SD card** goes in after step 3 below.
8. **Power** the Pi last with the official 27W supply.

## 3. Flash the SD card (on your laptop)

1. Install Raspberry Pi Imager from raspberrypi.com/software and put the SD card in your laptop.
2. Device: **Raspberry Pi 5**. OS: **Raspberry Pi OS (64-bit)**, the regular desktop version, not Lite (the kiosk screen needs the desktop). Storage: your SD card.
3. When it asks to apply OS customization, choose Edit Settings:
   - Hostname: `photobooth`
   - Username `booth`, and a password you'll remember
   - Wi-Fi: your hotspot's name and password, Wi-Fi country US
   - Locale/timezone: yours
   - Services tab: Enable SSH, use password authentication
4. Write, eject, put the card in the Pi, power it on. First boot takes a few minutes and you'll see the desktop on the touchscreen.

## 4. Connect your laptop to the Pi

1. Put your laptop on the same hotspot.
2. In Terminal: `ssh booth@photobooth.local` and type `yes`, then your password. If you get a prompt that ends in `booth@photobooth:~ $`, you're in. Type `exit` to leave.
3. If `photobooth.local` isn't found, check your hotspot's connected devices list for the Pi's IP address and use `ssh booth@<that IP>`.

From here the agents do everything over SSH. You only need to keep the laptop, Pi, and printer on the same hotspot.

## 5. Put the printer on the hotspot

On the SELPHY: open the Wi-Fi settings menu, choose connecting through a Wi-Fi network/router, pick your hotspot, and enter the password. Leave it on. Agent B will find it from the Pi.

## 6. AWS

You need AWS credentials on your laptop that can create CloudFormation stacks, Lambda, S3, API Gateway, and IAM roles (an admin user or SSO profile from your team's account is easiest). Agent A installs the tools and deploys.

## 7. The agent prompts

Run these with a coding agent on your laptop (Devin, Claude Code, Cursor, etc.) that has terminal access. Run A, then B. C can run any time. D after C and B.

Before starting, the code needs to be in `github.com/AlanRoybal/photobooth` (or replace that URL in the prompts with wherever the code is).

### Agent A: deploy AWS

```
Deploy the AWS backend for my photobooth. The code is in github.com/AlanRoybal/photobooth. Clone it to my laptop if it isn't already.

The backend is an AWS SAM app in cloud/ (template.yaml + share/app.py): a private S3 bucket and one Lambda behind an HTTP API with POST /upload (gives the Pi presigned S3 PUT URLs, protected by an x-booth-key header) and GET /p/{id} (the mobile share page the QR code opens).

Steps:
1. Make sure the AWS CLI and AWS SAM CLI are installed (install them if not). Run `aws sts get-caller-identity` to confirm I'm logged in. If not, stop and tell me what to run to log in.
2. Generate a booth key with `openssl rand -hex 24`.
3. From cloud/, run `sam build`, then `sam deploy --guided` with stack name `photobooth`, region us-east-1 (unless I say otherwise), parameter BoothKey = the generated key, EventName = "<EVENT NAME>", allow SAM to create IAM roles, and save the config.
4. Test it:
   - `curl -X POST <ApiUrl>/upload -H "x-booth-key: <key>" -H "Content-Type: application/json" -d '{"id":"testabcd"}'` returns JSON with presigned URLs for framed.jpg and story.jpg.
   - PUT any JPEG to both URLs with `-H "Content-Type: image/jpeg"`, then open <ApiUrl>/p/testabcd. It should show the photo with "Share to Instagram Story" and "Download photo" buttons.
   - The same POST with a wrong key returns 403.
   - Delete the test objects from the bucket afterward.
5. Give me the ApiUrl output and the booth key. I'll pass both to the agent setting up the Pi. Don't commit the key anywhere.

Don't change the app code unless something fails. If you do, explain why.
```

### Agent B: set up the Raspberry Pi

```
Set up my Raspberry Pi 5 photobooth over SSH. The Pi is at booth@photobooth.local (password: I'll type it when asked) and is on the same Wi-Fi hotspot as this laptop and a Canon SELPHY CP1500 printer. The code is in github.com/AlanRoybal/photobooth. Read README.md and GUIDE.md first.

Hardware: Pi 5 8GB on Raspberry Pi OS 64-bit desktop, Arducam Camera Module 3 (IMX708, 102° wide) on CAM/DISP 0, Hosyond 7" 1024x600 HDMI touchscreen on HDMI 0 with USB touch, SELPHY CP1500 on Wi-Fi.

AWS values from the deploy: ApiUrl = <API URL>, booth key = <BOOTH KEY>. Event title for the start screen: "<EVENT NAME>".

Steps:
1. Set up SSH key login so I only type the password once (ssh-copy-id).
2. Get the repo onto the Pi at /home/booth/photobooth. If the Pi can't clone it (private repo), clone it on this laptop and rsync it over.
3. On the Pi, `sudo apt update && sudo apt full-upgrade -y`, reboot, then run `bash deploy/setup.sh` from the repo.
4. Camera: `rpicam-hello --list-cameras` must list an imx708. If it doesn't, add `dtoverlay=imx708` and set `camera_auto_detect=0` in /boot/firmware/config.txt, reboot, and check again. Then take a test still with `rpicam-still -o test.jpg` (stop photobooth.service first since only one process can use the camera) and look at it. If the image is upside down, set "camera_rotate_180": true in booth/config.local.json.
5. Screen: confirm the desktop runs at 1024x600 (`wlr-randr` or /sys/class/drm/*/modes). If not, append `video=HDMI-A-1:1024x600M@60` to the single line in /boot/firmware/cmdline.txt. Confirm touch works.
6. Printer: run `bash deploy/setup-printer.sh`. It finds the SELPHY with `driverless` and adds it as queue SELPHY with `-m everywhere`. Check the PageSize list it prints and make sure print_options in booth/config.local.json uses the borderless postcard/4x6 entry (default is `["-o", "PageSize=Postcard.Borderless"]`). Print one test with `lp -d SELPHY -o PageSize=... <a 1200x1800 jpg>`.
7. Write booth/config.local.json with: title, share_base_url and upload_api_url (both = the ApiUrl), booth_key, printer_name "SELPHY". Keep any camera/print settings from earlier steps. Options are in booth/config.py.
8. `sudo systemctl restart photobooth` and check `journalctl -u photobooth -f`. Then reboot. The touchscreen should come up straight into the photobooth start screen (Chromium kiosk via ~/.config/labwc/autostart).
9. Run the whole flow on the touchscreen with me or by curl: start, instructions, countdown over live preview, review, frame carousel, confirm. Check the print comes out with the frame and QR, scanning the QR on a phone opens the share page after the upload (the log says "uploaded <id>"), and Share to Instagram Story opens the share sheet with the story image.
10. Tune from the real print: if there's a white border, raise print_scale toward 1.0; if the frame gets cut off at the edges, lower it. If the arrow on the instructions screen isn't pointing at the camera, change camera_arrow_x_percent. If the live preview looks mirrored wrong or the print should not be mirrored, change mirror_preview / mirror_photo.

Only change app code if something doesn't work on the real hardware, and tell me what you changed. Commit fixes to the repo. Never commit booth/config.local.json.
```

### Agent C: make the frame templates

Give this agent your assets: logo files (PNG/SVG, transparent background), event name, colors (hex), fonts, any stickers/art, a short description of the theme, how many frames you want, and one sample photo of people (for checking alignment).

```
Make themed photo frame templates for my photobooth, using the assets I've attached. The photobooth code is in github.com/AlanRoybal/photobooth. The booth places the user's photo under a frame PNG and then draws a QR code on top. See booth/compose.py for exactly how, and booth/frames/ for 3 placeholder frames in the right format.

Theme: <describe the theme>. Event name: <EVENT NAME>. Colors: <hex codes>. Fonts: <fonts>. Number of frames: <N>, each a different design in the same theme.

Format for each frame (id = short lowercase name, e.g. neon):
- booth/frames/<id>.png: 1200x1800 px (4x6 in at 300 DPI, portrait), RGBA, sRGB. The photo shows through transparent pixels.
- booth/frames/<id>.json:
  {"name": "Neon", "order": 0,
   "photo": {"x": 80, "y": 120, "w": 1040, "h": 1160},
   "qr": {"x": 820, "y": 1400, "size": 300},
   "story_bg": "#14143a"}
  photo = the rectangle the camera photo fills (center-cropped to fill it). Every transparent pixel must be inside this rectangle. You can make the window rounded or any shape by keeping pixels inside the rectangle opaque. Wider windows crop less: the camera is 16:9 and very wide angle, so 1040 wide by 780-1160 tall works well.
  qr = where the QR goes, square, at least 260 px. It's drawn black on white with its own white border, on top of the frame. The QR only appears on the printed copy. Downloads and Instagram stories show the frame without it, so put something under that spot that looks good on its own, like the event logo.
  name = shown under the carousel. order = carousel order.
  story_bg = background color for the Instagram story version (the framed photo is centered on a 1080x1920 canvas of this color).
- Optional booth/frames/<id>.story.png: a 1080x1920 frame designed for Instagram stories, plus "story_photo": {"x":..,"y":..,"w":..,"h":..} in the JSON. Without it, the story is made automatically from story_bg.

Design rules:
- Keep text, logos, and anything important at least 70 px from every edge. The printer prints borderless and trims the edges slightly.
- Only use the assets and text I gave you. Don't invent slogans or extra copy.
- Make the PNGs with code (Python/Pillow, SVG, etc.) so they're exact. Keep the source in frames-src/<id>/ so I can tweak them later.
- Delete the 3 placeholder frames (classic, midnight, sunset) unless I say to keep them.

Check your work: run `python3 frames-src/preview_frames.py <my sample photo>` and look at every image in frames-src/previews/. Fix anything misaligned, cut off, or with photo showing through where it shouldn't. Send me the previews.

Commit the frames to the repo.
```

### Agent D: put the new frames on the Pi

```
The photobooth repo github.com/AlanRoybal/photobooth has new frames in booth/frames/. Update the Pi at booth@photobooth.local: pull or rsync the repo to /home/booth/photobooth (don't overwrite booth/config.local.json), then `sudo systemctl restart photobooth`, and confirm on the touchscreen that the carousel shows the new frames. Print one to check the edges.
```

## 8. Event day

- Power on in this order: hotspot, printer, Pi. The booth opens by itself.
- To shut down: press the Pi's power button twice, wait for the green light to stop flashing, then unplug. Don't just pull the plug.
- Prints that can't upload (no internet) still print. Their QR codes start working once the Pi is back online and the upload catches up.
- The SELPHY holds 18 sheets and one RP-108 cassette makes 36 prints. A print takes about 40 seconds.
