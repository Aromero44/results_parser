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

### Step 3: Run the App

Double-click the file called **`HY-TEK Results.command`** in the app folder. The first time, it installs the libraries the app needs (a few minutes), then opens the app.

- The first time, Mac may say "cannot be opened because it is from an unidentified developer."
- If that happens: right-click the file, choose **Open**, then click **Open** in the popup. You only have to do this once.

---

## Windows Setup

### Step 2: Install Python

1. Go to [python.org/downloads](https://www.python.org/downloads/)
2. Click the big yellow **"Download Python"** button
3. **Important:** On the first installer screen, check the box that says **"Add Python to PATH"** at the bottom before clicking Install
4. Click **Install Now** and wait for it to finish

### Step 3: Run the App

Open the app folder and double-click **`HY-TEK Results.bat`**.

- **The first time**, a black window will appear and install the libraries the app needs. This takes a few minutes. Don't close it. The app opens when it's done.
- After that, double-clicking it opens the app right away.

> **Can't find the right file?** Windows hides file extensions by default, so you may see several files called "HY-TEK Results". To turn on extensions: open File Explorer, click **View** at the top, and check **File name extensions** (Windows 10) or click **View > Show > File name extensions** (Windows 11). Look for the one ending in `.bat`.
>
> **Folder inside a folder?** "Extract All" often creates `results_parser-main` *inside* another `results_parser-main`. Open folders until you see `gui.py`, `requirements.txt`, and `HY-TEK Results.bat` together. That is the real app folder.

<details>
<summary>Manual install (only if the automatic setup fails)</summary>

1. Open the app folder, the one that contains `requirements.txt`
2. Click the **address bar** at the top of File Explorer (the bar showing the folder path, *not* the search box), type `cmd`, and press **Enter**
3. Paste this and press Enter:

```
python -m pip install -r requirements.txt
```

If you see `No such file or directory: 'requirements.txt'`, you're in the wrong folder. Type `dir` and press Enter. If `requirements.txt` isn't listed, go back to step 1.
</details>

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
2. Right-click **`HY-TEK Results.bat`**
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
2. Right-click **`HY-TEK Results.bat`**
3. Click **Pin to Start** (Windows 10) or **Show more options** > **Pin to Start** (Windows 11)

---

## Updating the App

### Easiest: the update button

1. Open the app and go to the **Settings** tab
2. Click **Check for Updates**, then **Yes**
3. When it says the update was installed, close the app and open it again

That's it. If the new version needs extra libraries, the launcher installs them the next time you open the app.

**Your saved results are always safe.** They're stored outside the app folder, in a hidden `.hytek_results` folder in your user folder (`C:\Users\<you>\.hytek_results` on Windows, `~/.hytek_results` on Mac). Updating never touches them.

### If you're on a version without the update button

1. Download the new ZIP the same way as in Step 1
2. Delete the old app folder. If you keep meet PDFs inside it, move them somewhere else first.
3. Extract the new ZIP and put the folder **in the same place, with the same name** as the old one. Your Desktop shortcut, Dock icon or taskbar pin will then keep working.

If you downloaded with Git, you can instead run `git pull` in the app folder.

---

## Using the App

### Step 1: Load Your Meet Results

The app reads HY-TEK Meet Manager results PDFs. You'll want to load each meet one at a time:

1. Click **Load PDF** and select a meet results PDF
2. The app will parse the PDF and show every result from that meet in the **Meet Results** tab
3. You'll see results from all teams — this is normal

### Step 2: Filter and Save Your Team's Results

After loading a meet, you'll usually just want your own team's results:

1. Use the **Team** dropdown at the top to filter to your team
2. You can also filter by **Gender**, **Stroke**, or **Event** to narrow things down further
3. Click **Select All Visible** to check every result currently shown
4. Click **Save Selected** to copy those results to your saved collection

You can also double-click any relay to see individual leg splits, and save specific legs from there.

### Step 3: Repeat for Each Meet

1. Click **Load PDF** again and select your next meet PDF
2. Filter to your team, select all visible, and save — same as before
3. Repeat until you've loaded all the meets you want

Each saved result is an independent copy — it includes the meet name and date so you know where it came from. You can delete a loaded meet from the app at any time without losing your saved results.

### Step 4: View Your Saved Results

Switch to the **Saved Results** tab to see everything you've saved across all meets. Each row shows the swimmer's name, year, team, event, time, which meet it came from, and the date. You can:

- Filter by team, event, or gender
- Remove results you no longer want
- Export to CSV for use in spreadsheets

### Step 5: Best Relay Calculator

The **Best Relay** tab automatically computes your fastest possible relay lineups using your saved results. It calculates five relays for both Women and Men:

- **200 Freestyle Relay** (4 x 50 Free)
- **400 Freestyle Relay** (4 x 100 Free)
- **800 Freestyle Relay** (4 x 200 Free)
- **200 Medley Relay** (4 x 50 — Back, Breast, Fly, Free)
- **400 Medley Relay** (4 x 100 — Back, Breast, Fly, Free)

You can filter by team and date range to narrow the calculation.

**How the relay calculator works:**

- It pulls each swimmer's best time for the relevant distance and stroke from your saved results
- It considers three time sources: **individual event times**, **lead-off relay splits**, and **first-50 splits** from 100-yard individual or lead-off events (for 50-yard relay legs)
- The **lead-off leg** of each relay can only use leadoff-eligible times (individual swims or lead-off relay splits — not mid-relay splits, since those have the benefit of a flying start)
- For **medley relays**, it searches across the top candidates for each stroke to find the four-swimmer combination with the lowest total time, correctly handling swimmers who are fast in multiple strokes
- For **freestyle relays**, it picks the fastest leadoff-eligible swimmer first, then the next three fastest

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python not found" | Reinstall Python and make sure "Add to PATH" is checked (Windows) |
| "No module named PySide6" | Double-click the launcher again. It reinstalls missing libraries automatically |
| "No such file or directory: requirements.txt" | Command Prompt/Terminal was opened in the wrong folder. See "Folder inside a folder?" in Windows Step 3 |
| App opens but window is blank | Try resizing the window, or close and reopen |
| PDF won't load | Make sure it's a HY-TEK Meet Manager results PDF (not a start list or psych sheet) |
