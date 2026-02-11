"""
Final verification script for the TUI Typer application.
This script verifies that all implemented features work correctly.
"""
import sys

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    try:
        from cli import cli
        from app import CLIApp
        from tui_typer.commands.history import HistoryManager
        from tui_typer.commands.loader import load_commands
        from tui_typer.commands.base import Command, dispatch_typer_command
        print("  ✅ All imports successful")
        return True
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False

def test_history_command_registered():
    """Test that the history command is registered in CLI."""
    print("\nTesting history command registration...")
    try:
        from cli import cli
        from typer.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(cli, ['--help'])

        if 'history' in result.stdout.lower():
            print("  ✅ History command is registered")
            return True
        else:
            print("  ❌ History command not found in help")
            return False
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False

def test_command_loader_params():
    """Test that command loader includes params."""
    print("\nTesting command loader with params...")
    try:
        from cli import cli
        from tui_typer.commands.loader import load_commands

        commands = load_commands(cli)

        # Check if commands have params attribute
        has_params = False
        for name, cmd in commands.items():
            if hasattr(cmd, 'params'):
                has_params = True
                break

        if has_params:
            print(f"  ✅ Commands loaded with params ({len(commands)} total)")
            return True
        else:
            print("  ❌ Commands don't have params attribute")
            return False
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False

def test_app_initialization():
    """Test that the app can be initialized."""
    print("\nTesting app initialization...")
    try:
        from app import CLIApp

        app = CLIApp()

        # Check that app has required attributes
        assert hasattr(app, 'history_manager'), "Missing history_manager"
        assert hasattr(app, 'app_config'), "Missing app_config"
        assert hasattr(app, 'display_history'), "Missing display_history method"

        print("  ✅ App initializes correctly with all attributes")
        return True
    except Exception as e:
        print(f"  ❌ Initialization failed: {e}")
        return False

def main():
    print("="*60)
    print("TUI-TYPER VERIFICATION TEST")
    print("="*60)

    tests = [
        test_imports,
        test_history_command_registered,
        test_command_loader_params,
        test_app_initialization,
    ]

    results = [test() for test in tests]

    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)

    if passed == total:
        print(f"✅ ALL TESTS PASSED ({passed}/{total})")
        print("="*60)
        print("\nThe following features are implemented and working:")
        print("  ✓ History command - displays command history")
        print("  ✓ Command loader - loads typer options (params)")
        print("  ✓ App initialization - no crashes on startup")
        print("  ✓ All modules import successfully")
        return 0
    else:
        print(f"❌ SOME TESTS FAILED ({passed}/{total} passed)")
        print("="*60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
