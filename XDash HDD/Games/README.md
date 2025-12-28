<p align="center">
    <a href="https://github.com/Voltarian-Technologies/XDash/">
        <img height="256px" src="../../docs/images/banner.png" />
    </a>
</p>

# Xbox 360 Game Compatibility

This `XDash HDD/Games/` folder is where you can place your Xbox 360 compatible games for use with XDash. The system supports both extracted game folders (`.xex` format) and disc image files (`.iso` format).

## How to Add Your Games

### Step 1: Place Your Games
Copy your Xbox 360 compatible games to this folder in one of these formats:

- **Extracted Game Folders**: Place the entire game folder containing `default.xex`
- **ISO Files**: Place the `.iso` file directly in this folder

### Step 2: Update the Layout Configuration
After adding your games, you must update the `XDash HDD/layout.json` file in the root directory to make them appear in XDash.

Open `XDash HDD/layout.json` and add entries for each game in the following format directly in the JSON object:

**For extracted game folders:**
```json
"Game Name": "Games/Game Folder/default.xex"
```

**For ISO files:**
```json
"Game Name": "Games/Game Name.iso"
```

### Example Configuration
Here's an example of what your `layout.json` might look like after adding several games:

```json
{
    "Dashboard": "Dashboard/$flash_dash.xex",
    "Skyrim": "Games/Skyrim/default.xex",
    "Halo 3": "Games/Halo 3/default.xex",
    "Gears of War": "Games/GOW/GearsOfWar.xex",
    "Forza Motorsport 4": "Games/Forza4.iso",
    "Call of Duty: Modern Warfare 2": "Games/MW2.iso"
}
```

## Important Notes

1. **Game Names**: Use descriptive names that will help you identify the games in XDash
2. **File Paths**: Ensure the paths in `layout.json` match exactly where you placed the files
3. **Compatibility**: Not all Xbox 360 games are compatible - check compatibility lists for your system
4. **Storage Space**: Consider your available storage when adding large ISO files

## Troubleshooting

If a game doesn't appear in XDash:
- Verify the file path in `layout.json` is correct
- Check that the game file/folder is in the correct location
- Ensure the game is compatible with your Xbox 360 system
- Restart XDash to refresh the game list

---

*Note: This documentation is part of the XDash project by Voltarian Technologies.*