-- Source for Scripts/main.scpt. After editing, rebuild and re-sign the app:
--   osacompile -o "HY-TEK Results.app/Contents/Resources/Scripts/main.scpt" "HY-TEK Results.app/Contents/Resources/launcher.applescript"
--   codesign --force --deep --sign - "HY-TEK Results.app"

-- The app folder is whatever folder this app sits in
set appPath to POSIX path of (path to me)
set appDir to do shell script "dirname " & quoted form of appPath

-- macOS runs a freshly downloaded app from a temporary read-only copy,
-- where the app's files can't be found
if appDir contains "/AppTranslocation/" then
	display dialog "One-time setup needed: in the app folder, open \"HY-TEK Results.command\" first (right-click it and choose Open). After that, this app will work." buttons {"OK"} default button 1 with icon caution
	return
end if

-- Find Python 3.10+ (python.org installer, then Homebrew). Apple's
-- /usr/bin/python3 is too old and may prompt to install developer tools.
set findPython to "for p in /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do if [ -x \"$p\" ] && \"$p\" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then echo \"$p\"; exit 0; fi; done; exit 1"
try
	set pythonPath to do shell script findPython
on error
	display dialog "Python 3.10 or newer was not found. Install it from python.org, then open this app again." buttons {"OK"} default button 1 with icon stop
	return
end try

-- First run: install the libraries in Terminal so the progress is visible
try
	do shell script quoted form of pythonPath & " -c 'import PySide6, pdfplumber, pandas'"
on error
	do shell script "open -a Terminal " & quoted form of (appDir & "/HY-TEK Results.command")
	return
end try

do shell script "cd " & quoted form of appDir & " && " & quoted form of pythonPath & " gui.py > /dev/null 2>&1 &"
