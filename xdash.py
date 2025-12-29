import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageTk
import os
import sys
import json
import subprocess
from pathlib import Path
import toml
import threading
import time
import ctypes
from ctypes import wintypes, byref
import win32gui
import win32process
import win32api
import win32con
import mss
import win32ui

# Try to import SDL2 for DirectInput support
try:
    import sdl2
    import sdl2.joystick as sdljoystick
    SDL2_AVAILABLE = True
except ImportError:
    SDL2_AVAILABLE = False
    print("SDL2 not available. DirectInput controller support disabled.")

# Windows API for XInput
XINPUT_DLL = ctypes.windll.xinput1_4 if hasattr(ctypes.windll, 'xinput1_4') else ctypes.windll.xinput9_1_0

# XInput constants
XINPUT_GAMEPAD_DPAD_UP = 0x0001
XINPUT_GAMEPAD_DPAD_DOWN = 0x0002
XINPUT_GAMEPAD_DPAD_LEFT = 0x0004
XINPUT_GAMEPAD_DPAD_RIGHT = 0x0008
XINPUT_GAMEPAD_START = 0x0010
XINPUT_GAMEPAD_BACK = 0x0020
XINPUT_GAMEPAD_LEFT_THUMB = 0x0040
XINPUT_GAMEPAD_RIGHT_THUMB = 0x0080
XINPUT_GAMEPAD_LEFT_SHOULDER = 0x0100
XINPUT_GAMEPAD_RIGHT_SHOULDER = 0x0200
XINPUT_GAMEPAD_A = 0x1000
XINPUT_GAMEPAD_B = 0x2000
XINPUT_GAMEPAD_X = 0x4000
XINPUT_GAMEPAD_Y = 0x8000

# XInput structures
class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [
        ("wButtons", wintypes.WORD),
        ("bLeftTrigger", wintypes.BYTE),
        ("bRightTrigger", wintypes.BYTE),
        ("sThumbLX", wintypes.SHORT),
        ("sThumbLY", wintypes.SHORT),
        ("sThumbRX", wintypes.SHORT),
        ("sThumbRY", wintypes.SHORT),
    ]

class XINPUT_STATE(ctypes.Structure):
    _fields_ = [
        ("dwPacketNumber", wintypes.DWORD),
        ("Gamepad", XINPUT_GAMEPAD),
    ]

class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [
        ("wLeftMotorSpeed", wintypes.WORD),
        ("wRightMotorSpeed", wintypes.WORD),
    ]

# XInput function prototypes
XInputGetState = XINPUT_DLL.XInputGetState
XInputGetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
XInputGetState.restype = wintypes.DWORD

XInputSetState = XINPUT_DLL.XInputSetState
XInputSetState.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_VIBRATION)]
XInputSetState.restype = wintypes.DWORD

class WindowCapture:
    """Enhanced window capture using Windows APIs for off-screen windows"""
    
    def __init__(self):
        self.capturing = False
        self.capture_thread = None
        self.target_hwnd = None
        self.callback = None
        self.fps = 60
        self.frame_time = 1.0 / self.fps
        self.print_window_available = hasattr(ctypes.windll.user32, 'PrintWindow')
        
        if self.print_window_available:
            print("PrintWindow API available for window capture")
        else:
            print("PrintWindow API not available, using fallback methods")
    
    def get_window_rect(self, hwnd):
        """Get window rectangle including borders and title bar"""
        try:
            # Get window rect
            rect = win32gui.GetWindowRect(hwnd)
            
            # Check if window is minimized
            if win32gui.IsIconic(hwnd):
                # Get the restored window position from window placement
                placement = win32gui.GetWindowPlacement(hwnd)
                if placement[1] == win32con.SW_SHOWMINIMIZED:
                    rect = placement[4]  # Normal position rect
            
            return rect
        except:
            return None
    
    def capture_window_mss(self, hwnd):
        """Method 1: Capture using MSS (works for on-screen windows)"""
        try:
            rect = self.get_window_rect(hwnd)
            if not rect:
                return None
            
            # Convert rect to monitor index
            monitor = {
                "top": rect[1],
                "left": rect[0],
                "width": rect[2] - rect[0],
                "height": rect[3] - rect[1]
            }
            
            # Create MSS instance in the current thread
            with mss.mss() as sct:
                # Capture the region
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                return img
        except Exception as e:
            return None
    
    def capture_window_printwindow(self, hwnd):
        """Method 2: Capture using PrintWindow API (works for off-screen windows)"""
        try:
            # Get window dimensions
            rect = win32gui.GetWindowRect(hwnd)
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            if width <= 0 or height <= 0:
                return None
            
            # Get window device context
            hwnd_dc = win32gui.GetWindowDC(hwnd)
            
            # Create memory DC
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            
            # Create bitmap
            save_bitmap = win32ui.CreateBitmap()
            save_bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
            
            # Select bitmap into DC
            save_dc.SelectObject(save_bitmap)
            
            # Use PrintWindow with PW_RENDERFULLCONTENT flag (works for layered windows)
            # PW_RENDERFULLCONTENT = 0x00000002
            result = ctypes.windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)
            
            if result == 1:
                # Get bitmap info
                bmpinfo = save_bitmap.GetInfo()
                bmpstr = save_bitmap.GetBitmapBits(True)
                
                # Create PIL Image from bitmap data
                img = Image.frombuffer(
                    'RGB',
                    (bmpinfo['bmWidth'], bmpinfo['bmHeight']),
                    bmpstr, 'raw', 'BGRX', 0, 1
                )
                
                # Cleanup
                win32gui.DeleteObject(save_bitmap.GetHandle())
                save_dc.DeleteDC()
                mfc_dc.DeleteDC()
                win32gui.ReleaseDC(hwnd, hwnd_dc)
                
                return img
            
            # Cleanup on failure
            win32gui.DeleteObject(save_bitmap.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)
            
            return None
            
        except Exception as e:
            print(f"PrintWindow capture error: {e}")
            return None
    
    def capture_window_dwm(self, hwnd):
        """Method 3: Try DWM thumbnail API (for Windows Aero)"""
        try:
            # Import DWM API
            dwmapi = ctypes.windll.dwmapi
            DWM_TNP_VISIBLE = 0x8
            DWM_TNP_RECTDESTINATION = 0x1
            
            # Create thumbnail
            thumb = ctypes.c_void_p()
            hr = dwmapi.DwmRegisterThumbnail(
                ctypes.wintypes.HWND(0),  # Destination (we'll capture to memory)
                ctypes.wintypes.HWND(hwnd),
                ctypes.byref(thumb)
            )
            
            if hr != 0 or not thumb:
                return None
            
            # Get thumbnail properties
            from ctypes import wintypes
            
            class DWM_THUMBNAIL_PROPERTIES(ctypes.Structure):
                _fields_ = [
                    ("dwFlags", wintypes.DWORD),
                    ("rcDestination", wintypes.RECT),
                    ("rcSource", wintypes.RECT),
                    ("opacity", wintypes.BYTE),
                    ("fVisible", wintypes.BOOL),
                    ("fSourceClientAreaOnly", wintypes.BOOL)
                ]
            
            props = DWM_THUMBNAIL_PROPERTIES()
            props.dwFlags = DWM_TNP_VISIBLE | DWM_TNP_RECTDESTINATION
            props.fVisible = True
            
            # Get window rect
            rect = win32gui.GetWindowRect(hwnd)
            props.rcDestination.left = 0
            props.rcDestination.top = 0
            props.rcDestination.right = rect[2] - rect[0]
            props.rcDestination.bottom = rect[3] - rect[1]
            
            # Update thumbnail
            dwmapi.DwmUpdateThumbnailProperties(thumb, ctypes.byref(props))
            
            # Note: DWM thumbnail doesn't give us direct pixel access easily
            # This method is complex and may not be worth implementing fully
            
            dwmapi.DwmUnregisterThumbnail(thumb)
            return None
            
        except Exception as e:
            return None
    
    def capture_window(self, hwnd):
        """Try multiple capture methods to get window content"""
        # First, ensure window is in a capturable state
        self._prepare_window_for_capture(hwnd)
        
        # Try PrintWindow first (best for off-screen)
        if self.print_window_available:
            img = self.capture_window_printwindow(hwnd)
            if img:
                return img
        
        # Try MSS (good for on-screen windows)
        img = self.capture_window_mss(hwnd)
        if img:
            return img
        
        # Last resort: Try alternative methods
        return None
    
    def _prepare_window_for_capture(self, hwnd):
        """Ensure window is ready to be captured"""
        try:
            # Make sure window is not minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.1)  # Give window time to restore
            
            # Make sure window is visible (not hidden)
            if not win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
            
            # Force a redraw to update window content
            win32gui.UpdateWindow(hwnd)
            
            # Bring to front without activating (keep focus on our app)
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )
            
            # Set back to normal z-order but keep visible
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_NOTOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | 
                win32con.SWP_NOACTIVATE
            )
            
        except Exception as e:
            print(f"Error preparing window for capture: {e}")
    
    def start_capture(self, hwnd, callback):
        """Start capturing window at specified FPS"""
        self.target_hwnd = hwnd
        self.callback = callback
        self.capturing = True
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
    
    def _capture_loop(self):
        """Main capture loop"""
        last_capture_time = time.time()
        consecutive_failures = 0
        max_failures = 10
        
        while self.capturing and self.target_hwnd:
            try:
                current_time = time.time()
                elapsed = current_time - last_capture_time
                
                # Wait for next frame time
                if elapsed < self.frame_time:
                    time.sleep(self.frame_time - elapsed)
                
                # Capture frame
                img = self.capture_window(self.target_hwnd)
                if img and self.callback:
                    self.callback(img)
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        print(f"Too many capture failures ({consecutive_failures}). Stopping capture.")
                        self.stop_capture()
                
                last_capture_time = current_time
                
            except Exception as e:
                print(f"Capture loop error: {e}")
                time.sleep(0.1)
    
    def stop_capture(self):
        """Stop capturing"""
        self.capturing = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)

class ControllerManager:
    """Manages both XInput and DirectInput (SDL) controllers"""
    
    def __init__(self, controller_type="any"):
        self.controller_type = controller_type
        self.xinput_controllers = [False] * 4  # Track connected XInput controllers
        self.sdl_joysticks = []  # SDL joystick objects
        self.sdl_controllers = []  # Track connected SDL controllers
        self.running = False
        self.poll_thread = None
        self.last_state = {}
        self.debounce_time = 0.2  # 200ms debounce for button presses
        self.last_press_time = {}
        
        # Initialize SDL if needed
        if SDL2_AVAILABLE and controller_type in ["any", "sdl"]:
            self._init_sdl()
        
        print(f"ControllerManager initialized with type: {controller_type}")
        print(f"SDL2 available: {SDL2_AVAILABLE}")
    
    def _init_sdl(self):
        """Initialize SDL2 for DirectInput support"""
        try:
            sdl2.SDL_Init(sdl2.SDL_INIT_JOYSTICK | sdl2.SDL_INIT_GAMECONTROLLER)
            # Load controller mappings if available
            try:
                mapping_file = Path("gamecontrollerdb.txt")
                if mapping_file.exists():
                    with open(mapping_file, 'rb') as f:
                        sdl2.SDL_GameControllerAddMappingsFromRW(sdl2.SDL_RWFromFile(f.name, b"rb"), 1)
            except:
                pass
            
            self._scan_sdl_controllers()
            print(f"SDL2 initialized. Found {len(self.sdl_controllers)} controllers")
        except Exception as e:
            print(f"Failed to initialize SDL2: {e}")
    
    def _scan_sdl_controllers(self):
        """Scan for connected SDL controllers"""
        self.sdl_controllers = []
        self.sdl_joysticks = []
        
        try:
            sdl2.SDL_JoystickUpdate()
            num_joysticks = sdl2.SDL_NumJoysticks()
            
            for i in range(num_joysticks):
                if sdl2.SDL_IsGameController(i):
                    controller = sdl2.SDL_GameControllerOpen(i)
                    if controller:
                        joystick = sdl2.SDL_GameControllerGetJoystick(controller)
                        name = sdl2.SDL_GameControllerName(controller)
                        if name:
                            name = name.decode('utf-8', errors='ignore')
                        else:
                            name = f"Controller {i}"
                        
                        self.sdl_controllers.append({
                            'index': i,
                            'name': name,
                            'controller': controller,
                            'joystick': joystick
                        })
                        self.sdl_joysticks.append(joystick)
                        
                        print(f"SDL Controller {i}: {name}")
        except Exception as e:
            print(f"Error scanning SDL controllers: {e}")
    
    def _scan_xinput_controllers(self):
        """Scan for connected XInput controllers"""
        for i in range(4):
            state = XINPUT_STATE()
            result = XInputGetState(i, byref(state))
            self.xinput_controllers[i] = (result == 0)
    
    def get_controller_state(self, controller_index=0):
        """Get combined controller state from both XInput and SDL"""
            
        state = {
            'buttons': {},
            'axes': {},
            'hats': {},
            'connected': False,
            'type': None
        }
        
        # Check XInput controllers if enabled
        if self.controller_type in ["any", "xinput"]:
            xinput_state = self._get_xinput_state(controller_index)
            if xinput_state['connected']:
                state.update(xinput_state)
                state['type'] = 'xinput'
        
        # Check SDL controllers if XInput not found or "any" mode
        if (not state['connected'] or self.controller_type == "any") and self.controller_type in ["any", "sdl"]:
            sdl_state = self._get_sdl_state(controller_index)
            if sdl_state['connected']:
                # Merge states, preferring SDL if both connected in "any" mode
                if state['connected'] and self.controller_type == "any":
                    # Merge button states (OR operation)
                    for btn, value in sdl_state['buttons'].items():
                        if btn in state['buttons']:
                            state['buttons'][btn] = state['buttons'][btn] or value
                        else:
                            state['buttons'][btn] = value
                    
                    # Merge axes (use average or prefer one)
                    for axis, value in sdl_state['axes'].items():
                        if axis in state['axes']:
                            # Use the larger absolute value
                            if abs(value) > abs(state['axes'][axis]):
                                state['axes'][axis] = value
                        else:
                            state['axes'][axis] = value
                else:
                    state.update(sdl_state)
                    state['type'] = 'sdl'
        
        return state
    
    def _get_xinput_state(self, controller_index):
        """Get state of XInput controller"""
        state = XINPUT_STATE()
        result = XInputGetState(controller_index, byref(state))
        
        if result == 0:  # Controller connected
            gamepad = state.Gamepad
            
            # Map buttons
            buttons = {
                'back': bool(gamepad.wButtons & XINPUT_GAMEPAD_BACK),
                'start': bool(gamepad.wButtons & XINPUT_GAMEPAD_START),
                'a': bool(gamepad.wButtons & XINPUT_GAMEPAD_A),
                'b': bool(gamepad.wButtons & XINPUT_GAMEPAD_B),
                'x': bool(gamepad.wButtons & XINPUT_GAMEPAD_X),
                'y': bool(gamepad.wButtons & XINPUT_GAMEPAD_Y),
                'start': bool(gamepad.wButtons & XINPUT_GAMEPAD_START),
                'back': bool(gamepad.wButtons & XINPUT_GAMEPAD_BACK),
                'leftshoulder': bool(gamepad.wButtons & XINPUT_GAMEPAD_LEFT_SHOULDER),
                'rightshoulder': bool(gamepad.wButtons & XINPUT_GAMEPAD_RIGHT_SHOULDER),
                'leftstick': bool(gamepad.wButtons & XINPUT_GAMEPAD_LEFT_THUMB),
                'rightstick': bool(gamepad.wButtons & XINPUT_GAMEPAD_RIGHT_THUMB),
                'dpup': bool(gamepad.wButtons & XINPUT_GAMEPAD_DPAD_UP),
                'dpdown': bool(gamepad.wButtons & XINPUT_GAMEPAD_DPAD_DOWN),
                'dpleft': bool(gamepad.wButtons & XINPUT_GAMEPAD_DPAD_LEFT),
                'dpright': bool(gamepad.wButtons & XINPUT_GAMEPAD_DPAD_RIGHT),
            }
            
            # Map axes (normalize to -1.0 to 1.0)
            deadzone = 0.2
            axes = {
                'leftx': self._apply_deadzone(gamepad.sThumbLX / 32767.0, deadzone),
                'lefty': self._apply_deadzone(-gamepad.sThumbLY / 32767.0, deadzone),  # Invert Y
                'rightx': self._apply_deadzone(gamepad.sThumbRX / 32767.0, deadzone),
                'righty': self._apply_deadzone(-gamepad.sThumbRY / 32767.0, deadzone),  # Invert Y
                'lefttrigger': gamepad.bLeftTrigger / 255.0,
                'righttrigger': gamepad.bRightTrigger / 255.0,
            }
            
            return {
                'connected': True,
                'buttons': buttons,
                'axes': axes,
                'hats': {},  # XInput doesn't have separate hats
            }
        
        return {'connected': False}
    
    def _get_sdl_state(self, controller_index):
        """Get state of SDL controller"""
        if not SDL2_AVAILABLE or controller_index >= len(self.sdl_controllers):
            return {'connected': False}
        
        try:
            sdl2.SDL_JoystickUpdate()
            controller_info = self.sdl_controllers[controller_index]
            controller = controller_info['controller']
            joystick = controller_info['joystick']
            
            buttons = {}
            axes = {}
            hats = {}
            
            # Get button states using SDL_GameControllerGetButton with proper SDL2 constants
            button_mapping = {
                'a': sdl2.SDL_CONTROLLER_BUTTON_A,  # A button
                'b': sdl2.SDL_CONTROLLER_BUTTON_B,  # B button
                'x': sdl2.SDL_CONTROLLER_BUTTON_X,  # X button
                'y': sdl2.SDL_CONTROLLER_BUTTON_Y,  # Y button
                'back': sdl2.SDL_CONTROLLER_BUTTON_BACK,  # Back/Select
                'start': sdl2.SDL_CONTROLLER_BUTTON_START,  # Start
                'leftshoulder': sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER,  # LB
                'rightshoulder': sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,  # RB
                'leftstick': sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK,  # Left stick press
                'rightstick': sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK,  # Right stick press
                'dpup': sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP,  # D-Pad Up
                'dpdown': sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN,  # D-Pad Down
                'dpleft': sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT,  # D-Pad Left
                'dpright': sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT,  # D-Pad Right
            }
            
            # Check each button in the mapping
            for btn_name, btn_constant in button_mapping.items():
                try:
                    button_state = sdl2.SDL_GameControllerGetButton(controller, btn_constant)
                    buttons[btn_name] = bool(button_state)
                except:
                    buttons[btn_name] = False
            
            # Get axis states using SDL_GameControllerGetAxis
            # Check common axes up to 6
            axis_indices = [
                sdl2.SDL_CONTROLLER_AXIS_LEFTX,
                sdl2.SDL_CONTROLLER_AXIS_LEFTY,
                sdl2.SDL_CONTROLLER_AXIS_RIGHTX,
                sdl2.SDL_CONTROLLER_AXIS_RIGHTY,
                sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT,
                sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT
            ]
            
            for i, axis_enum in enumerate(axis_indices):
                try:
                    axis_value = sdl2.SDL_GameControllerGetAxis(controller, axis_enum)
                    axes[f'axis{i}'] = axis_value / 32767.0 if axis_value >= 0 else axis_value / 32768.0
                except:
                    pass
            
            # Get hat states using joystick interface (fallback for controllers without button D-pad)
            num_hats = sdl2.SDL_JoystickNumHats(joystick)
            for i in range(num_hats):
                try:
                    hat_value = sdl2.SDL_JoystickGetHat(joystick, i)
                    hats[f'hat{i}'] = hat_value
                except:
                    pass
            
            # Map axes to common names
            mapped_axes = {}
            if 'axis0' in axes:
                mapped_axes['leftx'] = axes['axis0']
            if 'axis1' in axes:
                mapped_axes['lefty'] = -axes['axis1']  # Invert Y
            if 'axis2' in axes:
                mapped_axes['rightx'] = axes['axis2']
            if 'axis3' in axes:
                mapped_axes['righty'] = -axes['axis3']  # Invert Y
            if 'axis4' in axes:
                # Trigger axes go from -32768 to 32767, normalize to 0-1
                mapped_axes['lefttrigger'] = (axes['axis4'] + 1.0) / 2.0
            if 'axis5' in axes:
                mapped_axes['righttrigger'] = (axes['axis5'] + 1.0) / 2.0
            
            return {
                'connected': True,
                'buttons': buttons,  # Already mapped with proper names
                'axes': mapped_axes,
                'hats': hats,
            }
            
        except Exception as e:
            print(f"Error getting SDL controller state: {e}")
            import traceback
            traceback.print_exc()
            return {'connected': False}
    
    def _apply_deadzone(self, value, deadzone):
        """Apply deadzone to axis value"""
        if abs(value) < deadzone:
            return 0.0
        return value
    
    def start_polling(self, callback, interval=0.05):
        """Start polling controllers in a separate thread"""
        self.running = True
        self.poll_thread = threading.Thread(target=self._poll_loop, args=(callback, interval), daemon=True)
        self.poll_thread.start()
    
    def _poll_loop(self, callback, interval):
        """Main polling loop"""
        last_scan_time = 0
        scan_interval = 2.0  # Scan for new controllers every 2 seconds
        
        while self.running:
            try:
                current_time = time.time()
                
                # Periodically scan for new controllers
                if current_time - last_scan_time > scan_interval:
                    if self.controller_type in ["any", "xinput"]:
                        self._scan_xinput_controllers()
                    if SDL2_AVAILABLE and self.controller_type in ["any", "sdl"]:
                        self._scan_sdl_controllers()
                    last_scan_time = current_time
                
                # Get controller state and call callback
                state = self.get_controller_state(0)
                callback(state)
                
                time.sleep(interval)
                
            except Exception as e:
                print(f"Error in controller polling loop: {e}")
                time.sleep(interval)
    
    def stop_polling(self):
        """Stop the polling thread gracefully"""
        self.running = False
        
        # Don't try to join from within the poll thread
        # The thread will exit naturally when self.running becomes False
        
        # Cleanup SDL in main thread
        if SDL2_AVAILABLE:
            for controller_info in self.sdl_controllers:
                if 'controller' in controller_info:
                    try:
                        sdl2.SDL_GameControllerClose(controller_info['controller'])
                    except:
                        pass
            try:
                sdl2.SDL_Quit()
            except:
                pass


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        # Set appearance mode and default color theme
        ctk.set_appearance_mode("light")

        # Configure window for 1080p (1920x1080)
        self.title("XDash - Xbox 360 Content Manager for Xenia Canary")
        
        # Set window size to 1080p
        self.window_width = 1920
        self.window_height = 1080
        
        # Center window on screen
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        center_x = int((screen_width - self.window_width) / 2)
        center_y = int((screen_height - self.window_height) / 2)
        
        self.geometry(f"{self.window_width}x{self.window_height}+{center_x}+{center_y}")
        self.resizable(False, False)
        
        self.configure(fg_color="#f0f3f9")
        
        # Get the script directory
        if getattr(sys, 'frozen', False):
            # If running as compiled executable
            self.script_dir = Path(sys.executable).parent
        else:
            # If running as Python script
            self.script_dir = Path(__file__).parent
        
        print(f"Script directory: {self.script_dir}")
        
        # Store window dimensions for later use
        self.window_width = self.window_width
        self.window_height = self.window_height
        
        # Define paths relative to script directory
        self.xenia_dir = self.script_dir / "Xenia"
        self.normal_exe_path = self.xenia_dir / "xenia_canary.exe"
        self.netplay_exe_path = self.xenia_dir / "xenia_canary_netplay.exe"
        self.hdd_storage = self.script_dir / "XDash HDD"
        self.json_path = self.hdd_storage / "layout.json"
        self.assets_dir = self.script_dir / "assets"
        self.config_path = self.script_dir / "xdash.config.toml"

        # Set Icons
        self.logo_path = self.assets_dir / "icon.png"
        self.logo_bitmap_path = self.assets_dir / "icon.ico"
        if os.path.exists(self.logo_bitmap_path):
            self.iconbitmap(self.logo_bitmap_path)
        else:
            print(f"Icon file not found: {self.logo_bitmap_path}")
        
        # Store the current executable path
        self.current_exe_path = self.normal_exe_path
        
        # Configure grid layout (4x4) for better responsiveness
        self.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.grid_rowconfigure((0, 1, 2, 3), weight=1)

        # Create assets directory if it doesn't exist
        assets_dir = self.script_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        # Load configuration
        self.config = self.load_config()
        
        # Initialize controller manager
        controller_type = self.config.get('controller_type', 'any')
        self.controller_manager = ControllerManager(controller_type)
        self.controller_state = {}
        self.focus_index = 0
        self.focusable_widgets = []
        self.last_controller_input_time = 0
        self.input_cooldown = 0.2
        
        # Track original widget styles for highlighting
        self.widget_styles = {}
        
        # Load HDD Content from JSON file
        self.hdd_content = self.load_hdd_content()
        
        # Store references to images to prevent garbage collection
        self._image_references = []
        
        # Store the selected HDD content
        self.selected_hdd_content = tk.StringVar()
        
        # Netplay mode variable
        self.netplay_mode = tk.BooleanVar(value=self.config.get('netplay', False))
        
        # Track Xenia processes
        self.xenia_process = None
        self.xenia_hwnd = None
        self.process_check_interval = 2000
        self.is_xenia_running = False
        
        # Window capture
        self.window_capture = WindowCapture()
        self.is_capturing = False
        
        # UI elements
        self.game_display = None
        self.menu_container = None
        
        # Apply initial executable mode from config BEFORE creating widgets
        self.apply_initial_exe_mode()
        
        # Create all widgets and components
        self.create_widgets()
        
        # Setup controller input handling
        self.setup_controller_input()
        
        # Start Xenia process monitoring
        self.monitor_xenia_processes()
        
        # Bind keyboard shortcuts for navigation
        self.bind('<Up>', lambda e: self.navigate_focus(-1))
        self.bind('<Down>', lambda e: self.navigate_focus(1))
        self.bind('<Return>', lambda e: self.activate_focused_widget())
        self.bind('<Escape>', lambda e: self.quit_app())
        
        # Bind mouse click to update focus
        self.bind('<Button-1>', self.handle_mouse_click)
        
        # Bind window focus events
        self.bind('<FocusIn>', lambda e: self.update_focus_display())

        # Bind window close event to quit_app
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
    
    def load_config(self):
        """Load configuration from TOML file"""
        default_config = {
            'netplay': False,
            'default_rom': '',
            'controller_type': 'any'
        }
        
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = toml.load(f)
                
                # Extract Config section
                config_section = config.get('Config', {})
                
                # Merge with defaults
                loaded_config = {
                    'netplay': config_section.get('netplay', default_config['netplay']),
                    'default_rom': config_section.get('default_rom', default_config['default_rom']),
                    'controller_type': config_section.get('controller_type', default_config['controller_type'])
                }
                
                print(f"Loaded config: {loaded_config}")
                return loaded_config
            else:
                # Create default config file
                self.save_config(default_config)
                print("Created default config file")
                return default_config
                
        except Exception as e:
            print(f"Error loading config: {e}")
            return default_config
    
    def save_config(self, config=None):
        """Save configuration to TOML file"""
        if config is None:
            config = {
                'netplay': self.netplay_mode.get(),
                'default_rom': self.selected_hdd_content.get(),
                'controller_type': self.config.get('controller_type', 'any')
            }
        
        try:
            # Create TOML structure
            toml_data = {
                'Config': {
                    'netplay': config['netplay'],
                    'default_rom': config['default_rom'],
                    'controller_type': config['controller_type']
                }
            }
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                toml.dump(toml_data, f)
            
            print(f"Saved config: {config}")
            return True
            
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def load_hdd_content(self):
        """Load HDD Content from JSON file in XDash HDD folder"""
        try:
            # Check if file exists
            if not self.json_path.exists():
                print(f"layout.json not found at: {self.json_path}")
                return "NO HDD CONTENT FOUND"
            
            # Load JSON file
            with open(self.json_path, "r", encoding='utf-8') as f:
                data = json.load(f)
            
            # Validate the data structure
            if not isinstance(data, dict):
                print(f"Invalid JSON structure: expected dict, got {type(data)}")
                return "NO HDD CONTENT FOUND"
            
            # Check if there are any HDD Content
            if not data:
                print("JSON file is empty")
                return "NO HDD CONTENT FOUND"
            
            return data
            
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON file: {e}")
            return "NO HDD CONTENT FOUND"
        except Exception as e:
            print(f"Error loading HDD Content: {e}")
            return "NO HDD CONTENT FOUND"
    
    def create_widgets(self):
        """Create and place all widgets"""
        # Create menu container (always present, but can be hidden)
        self.create_menu_widgets()
        
        # Create game display (always present, hidden by default)
        self.create_game_display()
        
        # Status indicators
        self.create_status_indicators()
    
    def create_menu_widgets(self):
        """Create menu widgets"""
        # Main menu container
        self.menu_container = ctk.CTkFrame(self, width=800, height=900,
                                        fg_color="#f0f3f9", corner_radius=0)
        
        # Center menu on window
        x_pos = (self.window_width - 800) // 2
        y_pos = (self.window_height - 900) // 2
        self.menu_container.place(x=x_pos, y=y_pos)
        
        # Banner Background
        self.bannerBackground = ctk.CTkFrame(self.menu_container, width=776, height=274, corner_radius=12, 
                                            fg_color="#ffffff", border_width=1, 
                                            border_color="#e2e8f0")
        self.bannerBackground.place(x=12, y=12)
        
        # Xenia Logo
        self.xeniaLogoFile = self.load_image(str(self.logo_path), (200, 200))
        self.xeniaLogo = ctk.CTkLabel(self.menu_container, image=self.xeniaLogoFile, text="", 
                                    width=200, height=200, fg_color="#ffffff")
        self.xeniaLogo.place(x=28, y=36)
        
        # Title Label
        self.titleLabel = ctk.CTkLabel(self.menu_container, text="XDash                                   ", 
                                    width=466, height=56, fg_color="#ffffff", 
                                    text_color="#555555", font=("Arial", 36, "bold"))
        self.titleLabel.place(x=245, y=106)
        
        # Description Label
        self.descriptionLabel = ctk.CTkLabel(self.menu_container, text="Manage your Xbox 360 Content with ease.", 
                                    width=466, height=24, fg_color="#ffffff", 
                                    text_color="#555555", font=("Arial", 24, "italic"))
        self.descriptionLabel.place(x=245, y=150)
        
        # Content Selection Frame
        self.selectionFrame = ctk.CTkFrame(self.menu_container, width=776, height=400, corner_radius=12,
                                        fg_color="#ffffff", border_width=1, 
                                        border_color="#e2e8f0")
        self.selectionFrame.place(x=12, y=300)
        
        # Check if HDD Content were loaded successfully
        if isinstance(self.hdd_content, str) and self.hdd_content == "NO HDD CONTENT FOUND":
            self.create_error_widgets()
        else:
            self.create_hdd_content_widgets()
   
    def create_game_display(self):
        """Create game display that will show embedded Xenia"""
        # Game display frame (full window)
        self.game_display = ctk.CTkLabel(
            self,
            text="",
            fg_color="black"
        )
        # Will be shown when game launches
        self.game_display.place_forget()
    
    def create_status_indicators(self):
        """Create status indicators"""
        # Controller status indicator
        self.controller_status = ctk.CTkLabel(
            self.menu_container,
            text="Controller: Disconnected",
            text_color="#6b7280",
            font=("Arial", 10)
        )
        self.controller_status.place(x=20, y=870)
        
        # Game status indicator (shown when game is running)
        self.game_status = ctk.CTkLabel(
            self,
            text="  Press Back + Start Buttons to Exit Game  ",
            text_color="#555555",
            corner_radius=8,
            font=("Arial", 16),
            fg_color="#f0f3f9"
        )
        self.game_status.place_forget()  # Hidden initially
    
    def create_error_widgets(self):
        """Create widgets for when no HDD Content are found"""
        # Error icon
        error_icon = "ERROR"
        
        # Error message
        self.errorLabel = ctk.CTkLabel(
            self.selectionFrame,
            text=f"{error_icon}\nNO HDD CONTENT FOUND",
            text_color="#dc2626",
            font=("Arial", 24, "bold"),
            justify="center"
        )
        self.errorLabel.place(relx=0.5, rely=0.3, anchor="center")
        
        # Instructions with actual path
        self.instructionsLabel = ctk.CTkLabel(
            self.selectionFrame,
            text=f"Please ensure layout.json exists at:\n{self.json_path}\n\n" +
                 "File should contain JSON in this format:\n" +
                 "{\n" +
                 '  "Content Name": "path/to/dash.xex",\n' +
                 '  "Another Content Name": "another/path.xex"\n' +
                 "}\n\n" +
                 f"xenia_canary.exe location: {self.normal_exe_path}",
            text_color="#555555",
            font=("Arial", 12),
            justify="left",
            wraplength=700
        )
        self.instructionsLabel.place(relx=0.5, rely=0.6, anchor="center")
        
        # Retry button
        self.retryButton = ctk.CTkButton(
            self.selectionFrame,
            text="Retry Load",
            command=self.retry_load_hdd_content,
            width=200,
            height=50,
            font=("Arial", 14, "bold"),
            fg_color="#3b82f6",
            hover_color="#2563eb",
            text_color="#ffffff",
            corner_radius=8,
            border_width=2,
            border_color="#3b82f6"
        )
        self.retryButton.place(relx=0.5, rely=0.85, anchor="center")
        
        # Store original style
        self.widget_styles[self.retryButton] = {
            'fg_color': "#3b82f6",
            'border_color': "#3b82f6",
            'border_width': 2,
            'text_color': "#ffffff"
        }
        
        # Add widgets to focusable list
        self.focusable_widgets = [self.retryButton]
        
        # Set initial focus
        self.set_focus(0)
    
    def create_hdd_content_widgets(self):
        """Create widgets for when HDD Content are loaded successfully"""
        # Content Selection Label
        self.selectionLabel = ctk.CTkLabel(self.selectionFrame, text="Select Content",
                                          text_color="#374151",
                                          font=("Arial", 26, "bold"),
                                          anchor="w")
        self.selectionLabel.place(x=30, y=25)
        
        # Content selection row
        self.create_rom_selection_row()
        
        # Mode selection checkboxes
        self.create_mode_checkboxes()
        
        # Launch Button
        self.launchButton = ctk.CTkButton(
            self.selectionFrame,
            text="Launch Content",
            command=self.launch_selected_rom,
            width=716,
            height=64,
            font=("Arial", 20, "bold"),
            corner_radius=10,
            fg_color="#3b82f6",
            hover_color="#2563eb",
            text_color="#ffffff",
            border_width=2,
            border_color="#3b82f6"
        )
        self.launchButton.place(x=30, y=200)
        
        # Store original style for launch button
        self.widget_styles[self.launchButton] = {
            'fg_color': "#3b82f6",
            'border_color': "#3b82f6",
            'border_width': 2,
            'text_color': "#ffffff"
        }
        
        # Add widgets to focusable list in navigation order
        self.focusable_widgets = [
            self.contentDropdown,
            self.setDefaultButtonTop,
            self.netplayCheckbox,
            self.launchButton
        ]
        
        # Set initial focus
        self.set_focus(0)
    
    def create_rom_selection_row(self):
        """Create the HDD content selection dropdown with set default button"""
        # Modern Dropdown (Combobox)
        self.contentDropdown = ctk.CTkComboBox(
            self.selectionFrame,
            values=list(self.hdd_content.keys()),
            variable=self.selected_hdd_content,
            width=556,
            height=56,
            font=("Arial", 16),
            dropdown_font=("Arial", 14),
            corner_radius=10,
            border_color="#d1d5db",
            border_width=2,
            button_color="#3b82f6",
            button_hover_color="#2563eb",
            fg_color="#ffffff",
            text_color="#1f2937",
            dropdown_fg_color="#ffffff",
            dropdown_text_color="#374151",
            dropdown_hover_color="#f3f4f6",
            state="readonly",
            justify="left",
            hover=True
        )
        self.contentDropdown.place(x=30, y=80)
        
        # Store original style
        self.widget_styles[self.contentDropdown] = {
            'border_color': "#d1d5db",
            'border_width': 2,
            'fg_color': "#ffffff"
        }
        
        # Set Default Content Button
        self.setDefaultButtonTop = ctk.CTkButton(
            self.selectionFrame,
            text="★ Set Default",
            command=self.set_default_rom,
            width=150,
            height=56,
            font=("Arial", 14, "bold"),
            fg_color="#f59e0b",
            hover_color="#d97706",
            text_color="#ffffff",
            corner_radius=10,
            border_width=2,
            border_color="#f59e0b"
        )
        self.setDefaultButtonTop.place(x=596, y=80)
        
        # Store original style
        self.widget_styles[self.setDefaultButtonTop] = {
            'fg_color': "#f59e0b",
            'border_color': "#f59e0b",
            'border_width': 2,
            'text_color': "#ffffff"
        }
        
        # Set initial selection
        if self.hdd_content:
            # Try to use the default HDD content from config
            default_rom = self.config.get('default_rom', '')
            if default_rom in self.hdd_content:
                self.selected_hdd_content.set(default_rom)
            else:
                # Fall back to first HDD content
                first_dashboard = list(self.hdd_content.keys())[0]
                self.selected_hdd_content.set(first_dashboard)
                
                # Update config with first HDD content if no default is set
                if not default_rom:
                    self.config['default_rom'] = first_dashboard
                    self.save_config()
    
    def create_mode_checkboxes(self):
        """Create the mode selection checkboxes"""
        # Netplay Mode Checkbox
        self.netplayCheckbox = ctk.CTkCheckBox(
            self.selectionFrame,
            text="Enable Netplay Mode (Experimental)",
            variable=self.netplay_mode,
            command=self.toggle_exe_mode,
            font=("Arial", 14),
            text_color="#374151",
            fg_color="#3b82f6",
            hover_color="#2563eb",
            border_width=2,
            border_color="#d1d5db",
            corner_radius=6
        )
        self.netplayCheckbox.place(x=30, y=150)
        
        # Store original style
        self.widget_styles[self.netplayCheckbox] = {
            'border_color': "#d1d5db",
            'border_width': 2,
            'fg_color': "#3b82f6"
        }
    
    def set_default_rom(self):
        """Set the currently selected HDD content as default"""
        selected = self.selected_hdd_content.get()
        if selected and selected in self.hdd_content:
            self.config['default_rom'] = selected
            if self.save_config():
                print(f"Set default HDD content to: {selected}")
    
    def apply_initial_exe_mode(self):
        """Apply the initial executable mode based on config (called before creating widgets)"""
        if self.config.get('netplay', False):
            self.current_exe_path = self.netplay_exe_path
            mode_name = "Netplay"
        else:
            self.current_exe_path = self.normal_exe_path
            mode_name = "Normal"
        
        print(f"Initial mode: {mode_name}, Using executable: {self.current_exe_path.name}")
    
    def toggle_exe_mode(self):
        """Toggle between normal and netplay executables"""
        # Apply the selected mode
        self.apply_exe_mode()
        
        # Update config
        self.config['netplay'] = self.netplay_mode.get()
        self.save_config()
    
    def apply_exe_mode(self):
        """Apply the current executable mode based on checkbox states"""
        if self.netplay_mode.get():
            self.current_exe_path = self.netplay_exe_path
            mode_name = "Netplay"
        else:
            self.current_exe_path = self.normal_exe_path
            mode_name = "Normal"
        
        print(f"Mode: {mode_name}, Using executable: {self.current_exe_path.name}")
    
    def retry_load_hdd_content(self):
        """Retry loading HDD Content and refresh the UI"""
        # Clear the selection frame
        for widget in self.selectionFrame.winfo_children():
            widget.destroy()
        
        # Reload HDD Content
        self.hdd_content = self.load_hdd_content()
        
        # Recreate widgets based on load result
        if isinstance(self.hdd_content, str) and self.hdd_content == "NO HDD CONTENT FOUND":
            self.create_error_widgets()
        else:
            self.create_hdd_content_widgets()
    
    def find_xenia_window(self, process_id):
        """Find Xenia window by process ID - enhanced version"""
        def callback(hwnd, hwnds):
            try:
                # Get process ID for this window
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
                if found_pid == process_id:
                    # Get window class name
                    class_name = win32gui.GetClassName(hwnd)
                    title = win32gui.GetWindowText(hwnd)
                    
                    # Common Xenia window patterns
                    is_xenia_window = (
                        "xenia" in title.lower() or 
                        "Xenia" in title or
                        title.endswith(".xex") or
                        "Direct3D" in class_name or
                        class_name.startswith("WindowsForms10") or
                        class_name.startswith("SDL_app") or
                        class_name == "MainWindow" or
                        "GLFW" in class_name or
                        len(title) > 0  # Any window with a title from this process
                    )
                    
                    if is_xenia_window:
                        hwnds.append(hwnd)
                        return False  # Stop searching when found
            except:
                pass
            return True  # Continue searching
        
        hwnds = []
        win32gui.EnumWindows(callback, hwnds)
        return hwnds[0] if hwnds else None
    
    def move_window_offscreen(self, hwnd):
        """Move window to off-screen position"""
        try:
            # Get screen dimensions
            screen_width = win32api.GetSystemMetrics(0)
            screen_height = win32api.GetSystemMetrics(1)
            
            # Position window far off-screen (right side)
            offscreen_x = screen_width + 10000
            offscreen_y = 100
            
            # Move window off-screen
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                offscreen_x,
                offscreen_y,
                1280,
                720,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE
            )
            
            print(f"Moved Xenia window off-screen to: ({offscreen_x}, {offscreen_y})")
            return True
        except Exception as e:
            print(f"Error moving window off-screen: {e}")
            return False
    
    def update_game_display(self, image):
        """Update the game display with new image"""
        try:
            # Resize image to fill the window while maintaining aspect ratio
            target_width = self.window_width
            target_height = self.window_height
            
            # Calculate aspect ratio preserving resize
            img_width, img_height = image.size
            ratio = min(target_width / img_width, target_height / img_height)
            new_width = int(img_width * ratio)
            new_height = int(img_height * ratio)
            
            # Resize image
            image = image.resize((new_width, new_height), Image.LANCZOS)
            
            # Create a black background image
            background = Image.new('RGB', (target_width, target_height), (0, 0, 0))
            
            # Paste the resized image in the center
            paste_x = (target_width - new_width) // 2
            paste_y = (target_height - new_height) // 2
            background.paste(image, (paste_x, paste_y))
            
            # Convert to CTkImage
            ctk_img = ctk.CTkImage(light_image=background, dark_image=background, 
                                size=(target_width, target_height))
            
            # Update label in main thread
            self.after(0, lambda: self.game_display.configure(image=ctk_img, text=""))
            
        except Exception as e:
            print(f"Error updating game display: {e}")   
 
    def show_game(self):
        """Show the game display and hide the menu"""
        if self.menu_container:
            self.menu_container.place_forget()
        
        if self.game_display:
            self.game_display.place(x=0, y=0, relwidth=1, relheight=1)
        
        if self.game_status:
            # Show game status at top-left corner
            self.game_status.place(x=12, y=12)
        
        print("Showing game")
    
    def show_menu(self):
        """Show the menu and hide game display"""
        if self.game_display:
            self.game_display.place_forget()
        
        if self.game_status:
            self.game_status.place_forget()
        
        if self.menu_container:
            # Re-center menu on window
            x_pos = (self.window_width - 800) // 2
            y_pos = (self.window_height - 900) // 2
            self.menu_container.place(x=x_pos, y=y_pos)
        
        print("Showing menu")
    
    def launch_selected_rom(self):
        """Launch the selected HDD content with embedding"""
        selected_name = self.selected_hdd_content.get()
        
        if not selected_name or selected_name not in self.hdd_content:
            return
        
        selected_rom = self.hdd_content[selected_name]
        selected_rom_path = self.hdd_storage / selected_rom
        
        # Check if the executable exists
        if not self.current_exe_path.exists():
            error_msg = f"Executable not found: {self.current_exe_path}"
            print(error_msg)
            self.show_error_popup("Executable Not Found", 
                                 f"Cannot find:\n{self.current_exe_path}\n\nPlease ensure the Xenia directory contains the required executable.")
            return
        
        # Check if the HDD content file exists
        if not selected_rom_path.exists():
            error_msg = f"Content file not found: {selected_rom_path}"
            print(error_msg)
            self.show_error_popup("Content Not Found", 
                                 f"Cannot find:\n{selected_rom_path}\n\nPlease check the path in layout.json.")
            return
        
        print(f"Launching: {selected_name}")
        print(f"Executable: {self.current_exe_path}")
        print(f"Content: {selected_rom_path}")
        
        try:
            # Show launching message
            self.show_info_popup("Launching", f"Launching {selected_name}...")
            
            # Launch Xenia process
            self.xenia_process = subprocess.Popen(
                [str(self.current_exe_path), str(selected_rom_path)],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            print(f"Xenia process started with PID: {self.xenia_process.pid}")

            # Setup window capture and show game
            self.setup_window_capture()

            # Close the info popup
            self.destroy_popup()
            
        except Exception as e:
            error_msg = f"Launch error: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            self.show_error_popup("Launch Failed", error_msg)
    
    def setup_window_capture(self):
        """Setup window capture after Xenia launches"""
        if not self.xenia_process:
            return
        
        try:
            print(f"Searching for Xenia window (PID: {self.xenia_process.pid})")
            
            # Try multiple times to find the window
            self.xenia_hwnd = None
            
            for attempt in range(30):  # 15 seconds total
                print(f"Attempt {attempt + 1}/30...")
                
                # Find window by process ID
                self.xenia_hwnd = self.find_xenia_window(self.xenia_process.pid)
                
                # Alternative: Find by window title
                if not self.xenia_hwnd:
                    windows = []
                    
                    def enum_windows_callback(hwnd, windows_list):
                        try:
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            if pid == self.xenia_process.pid:
                                title = win32gui.GetWindowText(hwnd)
                                class_name = win32gui.GetClassName(hwnd)
                                
                                # Look for Xenia window patterns
                                if (title and ('.xex' in title or 'Xenia' in title or 
                                            'Direct3D' in class_name or 
                                            'SDL_app' in class_name)):
                                    windows_list.append(hwnd)
                        except:
                            pass
                        return True
                    
                    win32gui.EnumWindows(enum_windows_callback, windows)
                    if windows:
                        self.xenia_hwnd = windows[0]
                
                if self.xenia_hwnd:
                    # Get window info
                    title = win32gui.GetWindowText(self.xenia_hwnd)
                    class_name = win32gui.GetClassName(self.xenia_hwnd)
                    print(f"Found window: '{title}' (Class: {class_name})")
                    
                    # Position window off-screen but ensure it's visible and not minimized
                    self.position_window_for_capture(self.xenia_hwnd)
                    
                    # Show game display
                    self.show_game()
                    
                    # Start capturing
                    self.is_capturing = True
                    self.window_capture.start_capture(self.xenia_hwnd, self.update_game_display)
                    print("Window capture started successfully!")
                    return
                
                time.sleep(0.5)
            
            print("Failed to find Xenia window")
            self.show_error_popup("Window Not Found", 
                                "Could not find Xenia window. The game may have failed to launch.")
            
        except Exception as e:
            print(f"Error setting up capture: {e}")
            import traceback
            traceback.print_exc()
            self.show_error_popup("Capture Setup Failed", str(e))

    def position_window_for_capture(self, hwnd):
        """Position window for optimal capture (off-screen, borderless, and visible)"""
        try:
            # Get screen dimensions
            screen_width = win32api.GetSystemMetrics(0)
            screen_height = win32api.GetSystemMetrics(1)
            
            # Set window to borderless (no title bar, no borders)
            self.make_window_borderless(hwnd)
            
            # Position window just outside visible area (right side)
            offscreen_x = screen_width  # Start at screen edge
            offscreen_y = 0
            
            # Ensure window is not minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            
            # Make sure window is visible but not activated
            win32gui.ShowWindow(hwnd, win32con.SW_SHOWNOACTIVATE)
            
            # Set window position and size (borderless fullscreen equivalent)
            # Use standard 16:9 resolution for compatibility
            window_width = 1280
            window_height = 720
            
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                offscreen_x,
                offscreen_y,
                window_width,
                window_height,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )
            
            print(f"Positioned borderless Xenia window at: ({offscreen_x}, {offscreen_y}) - Size: {window_width}x{window_height}")
            
            # Give window time to reposition
            time.sleep(0.3)
            
            return True
            
        except Exception as e:
            print(f"Error positioning window: {e}")
            import traceback
            traceback.print_exc()
            return False

    def make_window_borderless(self, hwnd):
        """Remove window borders, title bar, and menu bar completely - also remove from taskbar"""
        try:
            # Get current window style
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            
            # Remove ALL window decorations:
            new_style = style & ~(
                win32con.WS_CAPTION | 
                win32con.WS_THICKFRAME | 
                win32con.WS_SYSMENU |
                win32con.WS_MINIMIZEBOX |
                win32con.WS_MAXIMIZEBOX |
                win32con.WS_BORDER |
                win32con.WS_DLGFRAME |
                win32con.WS_OVERLAPPEDWINDOW
            )
            
            # Set to pure popup style (no borders, no title, no menu)
            new_style = win32con.WS_POPUP | win32con.WS_VISIBLE | win32con.WS_CLIPSIBLINGS | win32con.WS_CLIPCHILDREN
            
            # Set new window style
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
            
            # Get and modify extended styles
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            
            # Remove various extended styles
            ex_style &= ~(
                win32con.WS_EX_DLGMODALFRAME | 
                win32con.WS_EX_CLIENTEDGE | 
                win32con.WS_EX_STATICEDGE |
                win32con.WS_EX_WINDOWEDGE |
                win32con.WS_EX_OVERLAPPEDWINDOW |
                win32con.WS_EX_PALETTEWINDOW |
                win32con.WS_EX_TOOLWINDOW |
                win32con.WS_EX_APPWINDOW  # This removes from taskbar!
            )
            
            # Add styles to hide from taskbar and alt+tab
            ex_style |= (
                win32con.WS_EX_LAYERED |
                win32con.WS_EX_TOOLWINDOW  # This also helps hide from taskbar
            )
            
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
            
            # Remove window menu if it exists
            try:
                hmenu = win32gui.GetMenu(hwnd)
                if hmenu:
                    win32gui.SetMenu(hwnd, 0)
                    win32gui.DestroyMenu(hmenu)
                    print("Removed window menu")
            except:
                pass
            
            # Force remove any remaining menu bar
            try:
                win32gui.PostMessage(hwnd, win32con.WM_SYSCOMMAND, win32con.SC_RESTORE, 0)
            except:
                pass
            
            print("Window set to completely borderless and removed from taskbar")
            
            # Force window to redraw with new style
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED |
                win32con.SWP_NOACTIVATE
            )
            
            # Additional pass to ensure window is fully borderless
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED |
                win32con.SWP_NOACTIVATE
            )
            
            return True
            
        except Exception as e:
            print(f"Error making window borderless: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def stop_game(self):
        """Stop the current game and return to menu"""
        print("Stopping game...")
        
        if self.is_capturing:
            self.is_capturing = False
            self.window_capture.stop_capture()
            print("Stopped window capture")
        
        if self.xenia_process:
            try:
                # Try graceful termination
                self.xenia_process.terminate()
                print(f"Sent terminate signal to Xenia (PID: {self.xenia_process.pid})")
                
                # Wait a moment
                time.sleep(0.5)
                
                # Check if process ended
                if self.xenia_process.poll() is None:
                    print("Xenia didn't terminate, forcing kill...")
                    self.xenia_process.kill()
                
                # Clear references
                self.xenia_process = None
                self.xenia_hwnd = None
                print("Xenia process cleaned up")
                
            except Exception as e:
                print(f"Error stopping Xenia: {e}")
                self.xenia_process = None
                self.xenia_hwnd = None
        
        # Show menu
        self.show_menu()
        print("Returned to menu")
    
    def show_error_popup(self, title, message):
        """Show an error popup dialog"""
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry("400x200")
        popup.resizable(False, False)
        popup.transient(self)
        popup.grab_set()
        
        # Center the popup
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - popup.winfo_reqwidth()) // 2
        y = self.winfo_y() + (self.winfo_height() - popup.winfo_reqheight()) // 2
        popup.geometry(f"+{x}+{y}")
        
        # Error icon label
        error_label = ctk.CTkLabel(popup, text="⚠", font=("Arial", 48))
        error_label.pack(pady=10)
        
        # Message label
        message_label = ctk.CTkLabel(popup, text=message, font=("Arial", 12), wraplength=350)
        message_label.pack(pady=10)
        
        # OK button
        ok_button = ctk.CTkButton(popup, text="OK", command=popup.destroy, width=100,
                                 fg_color="#3b82f6", border_width=2, border_color="#3b82f6")
        ok_button.pack(pady=20)
    
    def show_info_popup(self, title, message):
        """Show an info popup dialog"""
        self.info_popup = ctk.CTkToplevel(self)
        self.info_popup.title(title)
        self.info_popup.geometry("300x150")
        self.info_popup.resizable(False, False)
        self.info_popup.transient(self)
        self.info_popup.grab_set()
        
        # Center the popup
        self.info_popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - self.info_popup.winfo_reqwidth()) // 2
        y = self.winfo_y() + (self.winfo_height() - self.info_popup.winfo_reqheight()) // 2
        self.info_popup.geometry(f"+{x}+{y}")
        
        # Message label
        message_label = ctk.CTkLabel(self.info_popup, text=message, font=("Arial", 14))
        message_label.pack(expand=True, pady=40)
    
    def destroy_popup(self):
        """Destroy the info popup if it exists"""
        if hasattr(self, 'info_popup') and self.info_popup.winfo_exists():
            self.info_popup.destroy()
    
    def load_image(self, path, size):
        """Load an image, resize it and return as CTkImage"""
        try:
            # Handle path as string or Path object
            path_str = str(path)
            
            # Check if image file exists
            if os.path.exists(path_str):
                img = Image.open(path_str)
                img = img.resize(size, Image.LANCZOS if hasattr(Image, 'LANCZOS') else Image.ANTIALIAS)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                self._image_references.append(ctk_img)  # Keep reference
                return ctk_img
            else:
                print(f"Image file not found: {path_str}")
                # Create a fallback white placeholder
                img = Image.new('RGB', size, color='#ffffff')
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                self._image_references.append(ctk_img)
                return ctk_img
        except Exception as e:
            print(f"Error loading image '{path}': {e}")
            # Create a white placeholder
            try:
                img = Image.new('RGB', size, color='#ffffff')
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=size)
                self._image_references.append(ctk_img)
                return ctk_img
            except Exception as e2:
                print(f"Failed to create error placeholder: {e2}")
                return None
    
    def check_xenia_process(self):
        """Check if Xenia process is still running"""
        if not self.xenia_process:
            return False
        
        try:
            return self.xenia_process.poll() is None
        except:
            return False
    
    def monitor_xenia_processes(self):
        """Monitor Xenia process and handle when it closes"""
        xenia_running = self.check_xenia_process()
        
        if self.is_xenia_running != xenia_running:
            self.is_xenia_running = xenia_running
            
            if not xenia_running and self.is_capturing:
                # Xenia closed while game is displayed
                print("Xenia process terminated")
                self.stop_game()
        
        # Schedule next check
        self.after(self.process_check_interval, self.monitor_xenia_processes)
    
    def setup_controller_input(self):
        """Setup controller input handling"""
        # Start controller polling
        self.controller_manager.start_polling(self.handle_controller_state)
        
        # Schedule periodic UI updates for controller status
        self.update_controller_status()
    
    def handle_controller_state(self, state):
        """Handle controller state updates"""
        self.controller_state = state
        
        # Update controller status in UI thread
        self.after(0, self.update_controller_display)
        
        # Only process input if enough time has passed since last input
        current_time = time.time()
        if current_time - self.last_controller_input_time < self.input_cooldown:
            return
        
        # Check if we should process input - ONLY check Start+Back combo when game is running
        if self.is_capturing:
            # When game is running, ONLY check for Share+Options combo (Back+Start)
            buttons = state.get('buttons', {})
            back_pressed = buttons.get('back', False)
            start_pressed = buttons.get('start', False)
            
            # Check for Share+Options combo (Back+Start) to exit
            if back_pressed and start_pressed:
                print("Share+Options pressed - stopping game")
                self.stop_game()
                self.last_controller_input_time = current_time
            # IGNORE ALL OTHER CONTROLLER INPUT WHEN GAME IS RUNNING
            return
        
        # Only process menu navigation when game is NOT running
        buttons = state.get('buttons', {})
        axes = state.get('axes', {})
        
        # D-pad/Stick navigation
        dpad_up = buttons.get('dpup', False)
        dpad_down = buttons.get('dpdown', False)
        left_stick_up = axes.get('lefty', 0) < -0.5
        left_stick_down = axes.get('lefty', 0) > 0.5
        
        nav_up = dpad_up or left_stick_up
        nav_down = dpad_down or left_stick_down
        
        if nav_up:
            self.navigate_focus(-1)
            self.last_controller_input_time = current_time
        elif nav_down:
            self.navigate_focus(1)
            self.last_controller_input_time = current_time
        
        # Handle A button press (activate)
        if buttons.get('a', False):
            self.activate_focused_widget()
            self.last_controller_input_time = current_time
        
        # Handle Start button press (launch) - only if Back is not pressed
        if buttons.get('start', False) and not buttons.get('back', False):
            self.launch_selected_rom()
            self.last_controller_input_time = current_time
        
        # Handle Back button press (set default) - only if Start is not pressed
        if buttons.get('back', False) and not buttons.get('start', False):
            self.set_default_rom()
            self.last_controller_input_time = current_time

    def update_controller_display(self):
        """Update controller status display in UI"""
        if self.controller_state.get('connected', False):
            controller_type = self.controller_state.get('type', 'Unknown')
            
            if self.is_capturing:
                # When game is running, show that only Start+Back works
                status_text = f"Controller: Game Running (Start+Back to Exit)"
                text_color = "#f59e0b"  # Orange for game mode
            else:
                status_text = f"Controller: Connected ({controller_type.upper()})"
                text_color = "#10b981"  # Green for connected
                
            self.controller_status.configure(
                text=status_text,
                text_color=text_color
            )
        else:
            self.controller_status.configure(
                text="Controller: Disconnected",
                text_color="#6b7280"
            )
    
    def update_controller_status(self):
        """Periodically update controller status"""
        self.update_controller_display()
        # Schedule next update
        self.after(1000, self.update_controller_status)
    
    def navigate_focus(self, direction):
        """Navigate focus between widgets"""
        if not self.focusable_widgets:
            return
        
        # Calculate new focus index
        new_index = (self.focus_index + direction) % len(self.focusable_widgets)
        
        # Set new focus
        self.set_focus(new_index)
    
    def set_focus(self, index):
        """Set focus to widget at index"""
        if 0 <= index < len(self.focusable_widgets):
            # Remove highlight from current widget
            self.remove_highlight()
            
            # Update focus index
            self.focus_index = index
            widget = self.focusable_widgets[index]
            
            # Highlight the focused widget
            self.highlight_widget(widget)
            
            # Special handling for different widget types
            if isinstance(widget, ctk.CTkComboBox):
                widget.focus()
            elif isinstance(widget, ctk.CTkButton):
                widget.focus()
            elif isinstance(widget, ctk.CTkCheckBox):
                widget.focus()
    
    def get_focused_widget(self):
        """Get currently focused widget"""
        if 0 <= self.focus_index < len(self.focusable_widgets):
            return self.focusable_widgets[self.focus_index]
        return None
    
    def remove_highlight(self):
        """Remove highlight from currently focused widget"""
        widget = self.get_focused_widget()
        if widget and widget in self.widget_styles:
            style = self.widget_styles[widget]
            if isinstance(widget, ctk.CTkButton):
                widget.configure(
                    border_color=style['border_color'],
                    border_width=style['border_width']
                )
            elif isinstance(widget, ctk.CTkComboBox):
                widget.configure(
                    border_color=style['border_color'],
                    border_width=style['border_width']
                )
            elif isinstance(widget, ctk.CTkCheckBox):
                widget.configure(
                    border_color=style['border_color'],
                    border_width=style['border_width']
                )
    
    def highlight_widget(self, widget):
        """Highlight the focused widget with bright yellow border"""
        highlight_color = "#fbbf24"
        highlight_width = 3
        
        if isinstance(widget, ctk.CTkButton):
            widget.configure(
                border_color=highlight_color,
                border_width=highlight_width
            )
        elif isinstance(widget, ctk.CTkComboBox):
            widget.configure(
                border_color=highlight_color,
                border_width=highlight_width
            )
        elif isinstance(widget, ctk.CTkCheckBox):
            widget.configure(
                border_color=highlight_color,
                border_width=highlight_width
            )
    
    def update_focus_display(self):
        """Update the focus display when window gets focus"""
        widget = self.get_focused_widget()
        if widget:
            self.highlight_widget(widget)
    
    def activate_focused_widget(self):
        """Activate the currently focused widget"""
        widget = self.get_focused_widget()
        if not widget:
            return
        
        if isinstance(widget, ctk.CTkButton):
            widget.invoke()
        elif isinstance(widget, ctk.CTkComboBox):
            widget.focus()
        elif isinstance(widget, ctk.CTkCheckBox):
            current_value = widget.get()
            widget.select() if not current_value else widget.deselect()
    
    def handle_mouse_click(self, event):
        """Handle mouse clicks to update focus"""
        # Find which widget was clicked
        for i, widget in enumerate(self.focusable_widgets):
            try:
                # Get widget bounds relative to main container
                if hasattr(widget, 'winfo_x'):
                    x = widget.winfo_x()
                    y = widget.winfo_y()
                    width = widget.winfo_width()
                    height = widget.winfo_height()
                    
                    # Check if click is within widget bounds
                    if (x <= event.x <= x + width and 
                        y <= event.y <= y + height):
                        self.set_focus(i)
                        break
            except:
                continue
    
    def quit_app(self):
        """Quit the application and ensure Xenia is closed"""
        print("Quitting XDash - cleaning up...")
        
        # Stop game if running
        if self.is_capturing:
            print("Stopping game capture...")
            self.is_capturing = False
            self.window_capture.stop_capture()
        
        # Terminate Xenia process if it exists
        if self.xenia_process:
            print(f"Terminating Xenia process (PID: {self.xenia_process.pid})...")
            try:
                # Try graceful termination first
                self.xenia_process.terminate()
                
                # Wait for process to end (max 3 seconds)
                for _ in range(30):
                    if self.xenia_process.poll() is not None:
                        print("Xenia terminated gracefully")
                        break
                    time.sleep(0.1)
                else:
                    # Force kill if still running
                    print("Force killing Xenia process...")
                    self.xenia_process.kill()
                    self.xenia_process.wait(timeout=2)
            except Exception as e:
                print(f"Error terminating Xenia: {e}")
            finally:
                self.xenia_process = None
                self.xenia_hwnd = None
        
        # Stop controller polling
        if hasattr(self, 'controller_manager'):
            print("Stopping controller polling...")
            self.controller_manager.stop_polling()
        
        # Destroy window
        print("Destroying window...")
        self.destroy()


if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        print(f"Error running application: {e}")
        import traceback
        traceback.print_exc()