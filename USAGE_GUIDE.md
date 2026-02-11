# TUI-Typer Usage Guide

## History Command

### Overview
The `history` command displays all previously executed commands in the TUI session.

### Usage

1. **Start the TUI application:**
   ```bash
   python cli.py interactive
   ```

2. **Execute some commands:**
   ```
   > version
   > help
   > list-commands
   ```

3. **View command history:**
   ```
   > history
   ```
   
   **Output:**
   ```
   Command History:
     1: version
     2: help
     3: list-commands
   ```

### Features

- **Persistent History**: Commands are saved to `~/.tui-typer_history`
- **Numbered Display**: Each command is numbered for easy reference
- **Maximum Limit**: Default maximum of 100 commands (configurable)
- **Arrow Key Navigation**: 
  - **↑ (Up)**: Navigate to previous command
  - **↓ (Down)**: Navigate to next command

### Command Line Help

You can also view help for the history command:
```bash
python cli.py history --help
```

Output:
```
Usage: root history [OPTIONS]

 Display the command history.

╭─ Options ─────────────────────────────────────╮
│ --help          Show this message and exit.   │
╰───────────────────────────────────────────────╯
```

## Command Loader with Typer Options

### Overview
The command loader now extracts and stores all Typer options (parameters) for each command, enabling better help display and command introspection.

### What's Included

Each loaded command now has access to:
- **Command name**
- **Description**
- **Parameters** (options, arguments)
- **Whether it's a command group**
- **Parent command** (for subcommands)

### Example Usage in Code

```python
from tui_typer.commands.loader import load_commands
from cli import cli

# Load all commands with their parameters
commands = load_commands(cli)

# Access a command
version_cmd = commands['version']
print(f"Name: {version_cmd.name}")
print(f"Description: {version_cmd.description}")
print(f"Parameters: {version_cmd.params}")

# Access a subcommand
serialize_excel = commands['serialize excel']
print(f"Subcommand: {serialize_excel.name}")
print(f"Parent: {serialize_excel.parent}")
print(f"Params: {serialize_excel.params}")
```

### Benefits

1. **Better Help Display**: The TUI can show detailed information about command options
2. **Command Introspection**: Applications can inspect available options programmatically
3. **Auto-completion**: Future features can use params for command auto-completion
4. **Validation**: Parameters can be validated before execution

## Configuration

### Config File Location
- Default: `~/.tui-typer.ini`
- Can be specified: `python cli.py interactive --config /path/to/config.ini`

### History File Location
- Default: `~/.tui-typer_history`
- Configurable in the config file

### Config File Format
```ini
[general]
app_name = tui-typer
history_file = ~/.tui-typer_history
max_history = 100

[display]
theme = default
show_timestamps = false
```

## Testing

### Run Tests
```bash
# Comprehensive test suite
python test_history.py

# Verification test
python verify_implementation.py
```

### Expected Output
```
✅ All tests passed!
```

## Troubleshooting

### Issue: Config file error
**Error:** `File contains no section headers`

**Solution:** This was fixed in the implementation. If you encounter this:
1. Delete the old config file: `rm ~/.tui-typer.ini`
2. Let the app create a new one on next run

### Issue: History not saving
**Solution:** 
1. Check write permissions on `~/.tui-typer_history`
2. Verify the history file path in config

### Issue: Commands not loading
**Solution:**
1. Check that `cli.py` has all commands registered
2. Run `python cli.py list-commands` to see available commands

## Architecture

### File Structure
```
tui-typer/
├── app.py                    # Main TUI application
├── cli.py                    # CLI commands definition
├── tui_typer/
│   ├── commands/
│   │   ├── base.py          # Command base class with params
│   │   ├── loader.py        # Command loader with options
│   │   ├── history.py       # History management
│   │   └── config.py        # Configuration management
│   └── ui/
│       └── ...
└── test_history.py          # Test suite
```

### Data Flow

1. **Command Entry**: User types command in TUI
2. **History Save**: Command added to HistoryManager
3. **Dispatch**: Command dispatched to Typer CLI
4. **Execution**: Typer executes the command
5. **Output**: Results displayed in TUI

## Future Enhancements

Possible improvements with the new params support:
- Command auto-completion based on available options
- Interactive option prompts
- Command validation before execution
- Custom help formatting using param metadata
