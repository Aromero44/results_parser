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

1. Open **Terminal** (search for "Terminal" in Spotlight, or find it in Applications > Utilities)
2. Copy and paste this entire line, then press Enter:

```
pip3 install pdfplumber pandas PySide6
```

3. Wait for it to finish (you'll see text scrolling by). When you see your username again with a `$` or `%` at the end, it's done.

> If you get an error about "pip3 not found", try `python3 -m pip install pdfplumber pandas PySide6` instead.

### Step 4: Run the App

**Option A** - Double-click the file called **`HY-TEK Results.command`** in this folder.

- The first time, Mac may say "cannot be opened because it is from an unidentified developer."
- If that happens: right-click the file, choose **Open**, then click **Open** in the popup.

**Option B** - In Terminal, paste this and press Enter:

```
cd path/to/this/folder
python3 gui.py
```

Replace `path/to/this/folder` with the actual location. Tip: type `cd ` (with a space after it), then drag the folder from Finder into the Terminal window - it will fill in the path for you.

---

## Windows Setup

### Step 2: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big yellow **"Download Python"** button
3. **Important:** On the first installer screen, check the box that says **"Add Python to PATH"** at the bottom before clicking Install
4. Click **Install Now** and wait for it to finish

### Step 3: Install the Required Libraries

1. Open **Command Prompt** (search for "cmd" in the Start menu)
2. Copy and paste this line, then press Enter:

```
pip install pdfplumber pandas PySide6
```

3. Wait for it to finish. When you see `C:\Users\...>` again, it's done.

> If you get an error about "pip not found", close Command Prompt and reopen it (the PATH needs to refresh). If it still doesn't work, try `python -m pip install pdfplumber pandas PySide6`.

### Step 4: Run the App

**Option A** - Double-click the file called **`HY-TEK Results.bat`** in this folder.

**Option B** - Double-click **`HY-TEK Results.pyw`** (this runs without a black terminal window).

---

## Adding to Applications / Creating a Shortcut

### Mac - Add to Dock or Applications

**Add to Dock (quickest):**

1. Open Finder and navigate to this folder
2. Drag the **`HY-TEK Results.command`** file onto your **Dock** (the bar of icons at the bottom of your screen), dropping it on the right side near the Trash
3. Now you can click it from the Dock anytime to launch the app

**Add to Launchpad / Applications:**

1. Open Finder and navigate to this folder
2. Hold the **Option** key and drag the **`HY-TEK Results.command`** file into your **Applications** folder (in the Finder sidebar on the left). Holding Option creates a copy so the original stays in place.
3. It will now show up when you search in **Spotlight** (Cmd + Space) or in **Launchpad**

**Create a Desktop shortcut:**

1. Open Finder and navigate to this folder
2. Right-click **`HY-TEK Results.command`** and choose **Make Alias**
3. Drag the new alias file (it will have "alias" in the name) to your **Desktop**
4. You can rename it to just "HY-TEK Results" by clicking the name once, waiting, then clicking again to edit

### Windows - Create a Desktop Shortcut / Pin to Taskbar

**Desktop shortcut:**

1. Open File Explorer and navigate to this folder
2. Right-click **`HY-TEK Results.bat`** (or **`HY-TEK Results.pyw`**)
3. Select **Show more options** (Windows 11) or go directly to the next step (Windows 10)
4. Click **Send to** > **Desktop (create shortcut)**
5. A shortcut will appear on your Desktop - you can rename it by right-clicking and choosing **Rename**

**Pin to Taskbar:**

1. First create a Desktop shortcut using the steps above
2. Right-click the shortcut on your Desktop
3. Click **Pin to taskbar**
4. The app icon will now always be visible in your taskbar at the bottom of the screen

**Pin to Start Menu:**

1. Open File Explorer and navigate to this folder
2. Right-click **`HY-TEK Results.bat`**
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
| "No module named PySide6" | Run the pip install command from Step 2 again |
| App opens but window is blank | Try resizing the window, or close and reopen |
| PDF won't load | Make sure it's a HY-TEK Meet Manager results PDF (not a start list or psych sheet) |
