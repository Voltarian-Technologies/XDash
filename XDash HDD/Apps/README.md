<p align="center">
    <a href="https://github.com/Voltarian-Technologies/XDash/">
        <img height="256px" src="../../docs/images/banner.png" />
    </a>
</p>

# Xbox 360 App Compatibility

This `XDash HDD/Apps/` folder is where you can place your Xbox 360 compatible apps for use with XDash. The system supports both extracted app folders (`.xex` format) and disc image files (`.iso` format).

## How to Add Your Apps

### Step 1: Place Your Apps
Copy your Xbox 360 compatible apps to this folder in one of these formats:

- **Extracted App Folders**: Place the entire app folder containing `default.xex`
- **ISO Files**: Place the `.iso` file directly in this folder

### Step 2: Update the Layout Configuration
After adding your apps, you must update the `XDash HDD/layout.json` file in the root directory to make them appear in XDash.

Open `XDash HDD/layout.json` and add entries for each app in the following format directly in the JSON object:

**For extracted app folders:**
```json
"App Name": "Apps/App Folder/default.xex"
```

**For ISO files:**
```json
"App Name": "Apps/App Name.iso"
```

### Example Configuration
Here's an example of what your `layout.json` might look like after adding several apps:

```json
{
    "Dashboard": "Dashboard/$flash_dash.xex",
    "Netflix": "Apps/Netflix/default.xex",
    "YouTube": "Apps/YouTube/YouTube.xex",
    "VLC Player": "Apps/VLC/VLC.xex",
    "Kodi": "Apps/Kodi.iso",
    "Web Browser": "Apps/Browser.iso"
}
```

## Important Notes

1. **App Names**: Use descriptive names that will help you identify the apps in XDash
2. **File Paths**: Ensure the paths in `layout.json` match exactly where you placed the files
3. **Compatibility**: Not all Xbox 360 apps are compatible - check compatibility lists for your system
4. **Storage Space**: Consider your available storage when adding large ISO files

## Troubleshooting

If an app doesn't appear in XDash:
- Verify the file path in `layout.json` is correct
- Check that the app file/folder is in the correct location
- Ensure the app is compatible with your Xbox 360 system
- Restart XDash to refresh the app list

---

*Note: This documentation is part of the XDash project by Voltarian Technologies.*