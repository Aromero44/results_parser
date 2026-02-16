import os
import sys
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gui import main
    main()
except Exception:
    # pythonw.exe has no console, so show errors in a message box
    import ctypes
    error = traceback.format_exc()
    ctypes.windll.user32.MessageBoxW(0, error, "HY-TEK Results - Error", 0x10)
