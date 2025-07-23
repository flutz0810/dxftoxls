import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow 
import os

def main():
    if sys.platform == "win32":
        try:
            import ctypes
            pid = os.getpid()
            mask = 0xFFFFFFFF
            handle = ctypes.windll.kernel32.OpenProcess(0x0200 | 0x0400, False, pid)
            ctypes.windll.kernel32.SetProcessAffinityMask(handle, mask)
            ctypes.windll.kernel32.CloseHandle(handle)
        except Exception as e:
            print(f"Could not set process affinity: {e}")
            
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.resize(1800, 900)
    main_window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
