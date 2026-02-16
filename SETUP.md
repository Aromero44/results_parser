# HY-TEK Results Viewer - Setup Guide

## What You Need

- **Python 3.10 or newer** (a free programming language)
- The app files (downloaded below)

---

## Step 1: Download the App

### Option A: Download as a ZIP (easiest - no extra software needed)

1. Go to [github.com/Aromero44/results_parser](https://github.com/Aromero44/results_parser)
2. Click the green **"Code"** button near the top right
3. Click **"Download ZIP"**
4. Open your Downloads folder and find the file **`results_parser-main.zip`**
5. **Mac:** Double-click the ZIP file to unzip it. A folder called `results_parser-main` will appear.
6. **Windows:** Right-click the ZIP file and choose **"Extract All..."**, then click **Extract**. A folder called `results_parser-main` will appear.
7. Move this folder wherever you'd like to keep it (Desktop, Documents, etc.)

### Option B: Download using Git (if you have Git installed)

If you already have Git installed, you can open Terminal (Mac) or Command Prompt (Windows) and run:

```
git clone https://github.com/Aromero44/results_parser.git
```

This creates a `results_parser` folder in your current location. If you don't know what Git is, just use Option A above.

---

## Mac Setup

### Step 2: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big yellow **"Download Python"** button
3. Open the downloaded file and follow the installer prompts
4. When the installer finishes, you're done with this step

### Step 3: Install the Required Libraries

1. Open **Finder** and find the app folder you downloaded
2. Right-click the folder and choose **"New Terminal at Folder"**. A Terminal window will open already in the right location.
3. Copy and paste this line, then press Enter:

```
pip3 install -r requirements.txt
```

4. Wait for it to finish (you'll see text scrolling by). When you see your username again with a `$` or `%` at the end, it's done.

> If you get an error about "pip3 not found", try `python3 -m pip install -r requirements.txt` instead.
>
> If you don't see "New Terminal at Folder" when you right-click, go to **System Settings > Keyboard > Keyboard Shortcuts > Services** and enable it under **Files and Folders**.

### Step 4: Run the App

Double-click the file called **`HY-TEK Results.command`** in the app folder.

- The first time, Mac may say "cannot be opened because it is from an unidentified developer."
- If that happens: right-click the file, choose **Open**, then click **Open** in the popup. You only have to do this once.

---

## Windows Setup

### Step 2: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big yellow **"Download Python"** button
3. **Important:** On the first installer screen, check the box that says **"Add Python to PATH"** at the bottom before clicking Install
4. Click **Install Now** and wait for it to finish

### Step 3: Install the Required Libraries

1. Open **File Explorer** and find the app folder you downloaded
2. Click on the **address bar** at the top (where it shows the folder path), type `cmd`, and press **Enter**. A Command Prompt window will open already in the right location.
3. Copy and paste this line, then press Enter:

```
pip install -r requirements.txt
```

4. Wait for it to finish. When you see `C:\Users\...>` again, it's done.

> If you get an error about "pip not found", close Command Prompt and reopen it (the PATH needs to refresh). If it still doesn't work, try `python -m pip install -r requirements.txt`.

### Step 4: Run the App

Double-click **`HY-TEK Results.pyw`** in the app folder. The app will open directly with no terminal window.

> **Can't find the right file?** Windows hides file extensions by default, so you may see several files called "HY-TEK Results". To turn on extensions: open File Explorer, click **View** at the top, and check **File name extensions** (Windows 10) or click **View > Show > File name extensions** (Windows 11). Look for the one ending in `.pyw`.

---

## Adding to Applications / Creating a Shortcut

### Mac

**Add to Dock (quickest):**

1. Open Finder and navigate to the app folder
2. Drag **`HY-TEK Results.command`** onto your **Dock** (the bar of icons at the bottom of your screen), dropping it on the right side near the Trash
3. Now you can click it from the Dock anytime to launch the app

**Create a Desktop shortcut:**

1. Open Finder and navigate to the app folder
2. Hold **Option + Command** and drag **`HY-TEK Results.command`** to your **Desktop**. This creates a shortcut (alias) while keeping the original in place.
3. You can rename it by clicking the name, waiting a moment, then clicking again to edit

### Windows

**Desktop shortcut:**

1. Open File Explorer and navigate to the app folder
2. Right-click **`HY-TEK Results.pyw`**
3. Select **Show more options** (Windows 11) or go directly to the next step (Windows 10)
4. Click **Send to** > **Desktop (create shortcut)**
5. You can rename the shortcut by right-clicking it and choosing **Rename**

**Pin to Taskbar:**

1. First create a Desktop shortcut using the steps above
2. Right-click the shortcut on your Desktop
3. Click **Pin to taskbar**
4. The app icon will now always be visible in your taskbar at the bottom of the screen

**Pin to Start Menu:**

1. Open File Explorer and navigate to the app folder
2. Right-click **`HY-TEK Results.pyw`**
3. Click **Pin to Start** (Windows 10) or **Show more options** > **Pin to Start** (Windows 11)

---

## Using the App

1. Click **Load PDF** and select a HY-TEK meet results PDF
2. Browse results in the **Meet Results** tab - use the filters at the top to narrow down by team, event, stroke, etc.
3. Select results by clicking the checkboxes, then click **Save Selected** to add them to your saved collection
4. Switch to the **Saved Results** tab to see everything you've saved across all meets
5. The **Best Relay** tab automatically computes optimal relay lineups from your saved results

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python not found" | Reinstall Python and make sure "Add to PATH" is checked (Windows) |
| "No module named PySide6" | Run the pip install command from Step 3 again |
| App opens but window is blank | Try resizing the window, or close and reopen |
| PDF won't load | Make sure it's a HY-TEK Meet Manager results PDF (not a start list or psych sheet) |
