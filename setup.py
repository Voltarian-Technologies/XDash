from cx_Freeze import setup, Executable

setup(
    name="XDash",
    description="Manage your Xbox 360 Content for Xenia Canary Emulator with ease.",
    author="VoltacceptYT, Xenia Contributors",
    executables=[Executable("xdash.py", base="gui", icon="assets/icon.ico", target_name="XDash.exe")],
    options={
        "build_exe": {
            "packages": [
                # GUI + Core
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

                # SDL2 / DirectInput
                "sdl2",
                "sdl2.ext",
                "sdl2.joystick",

                # XInput (ctypes already included)
                "ctypes.wintypes",
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
