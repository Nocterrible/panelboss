"""Does the Shell accept the tray icon at all?

Spies on pystray's Shell_NotifyIcon call, shows a solid red icon for
12 seconds, prints every NIM_ call with its result and error code."""
import ctypes
import threading
import time

from PIL import Image

from pystray._util import win32
import pystray

k32 = ctypes.windll.kernel32

nim_calls = []
orig = win32.Shell_NotifyIcon


def spy(code, data):
    result = orig(code, data)
    err = k32.GetLastError()
    nim_calls.append((hex(code), bool(result), err))
    print("Shell_NotifyIcon code=%s -> %s (err %s)" % (hex(code), result, err))
    return result


win32.Shell_NotifyIcon = spy   # _win32 looks the name up at call time

img = Image.new("RGB", (32, 32))
img.putpixel((0, 0), (255, 0, 0))
draw = img.load()
for x in range(32):
    for y in range(32):
        draw[x, y] = (255, 0, 0)          # solid red; impossible to miss

icon = pystray.Icon(name="VISIBLE TEST", icon=img,
                    menu=pystray.Menu(pystray.MenuItem("Quit",
                                                       action=print)))

def show(icon):
    icon.visible = True           # the docs say the icon starts hidden


t = threading.Thread(target=lambda: icon.run(setup=show), daemon=True)
t.start()
time.sleep(12)
icon.stop()
t.join(3)
print("calls:", nim_calls)
