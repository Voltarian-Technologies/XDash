from cx_Freeze import setup, Executable

setup(
    name="XDash",
    description="Manage your Xbox 360 Content for Xenia Canary Emulator with ease.",
    author="VoltacceptYT, Xenia Contributors",
    executables=[Executable("xdash.py", base="gui", icon="assets/icon.ico", target_name="XDash.exe")],
    options={
        "build_exe": {
            "packages": [
                "customtkinter",
                "tkinter",
                "PIL",
                "os",
                "sys",
                "json",
                "subprocess",
                "pathlib",
                "toml",
                "threading",
                "time",
                "ctypes",
                "collections",
                "win32ui",
                "win32con",
                "win32gui",
                "win32process",
                "win32api",
                "mss",
                "sdl2",
                "sdl2.joystick",
                "numpy",
                "comtypes"
            ],
            "include_files": [
                "assets/",
                "docs/",
                "Xenia/",
                "XDash HDD/",
                "xdash.config.toml",
                "README.md",
                "LICENSE"
            ],
            "build_exe": "dist"
        }
    }
)
