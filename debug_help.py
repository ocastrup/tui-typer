"""Debug script to see what's actually happening with --help."""

from typer.testing import CliRunner

from cli import cli

runner = CliRunner()

print("Testing serialize excel --help directly:")
print("=" * 60)
result = runner.invoke(cli, ["serialize", "excel", "--help"])
print(f"Exit code: {result.exit_code}")
print(f"Stdout length: {len(result.stdout)}")
print(f"Stderr length: {len(result.stderr) if result.stderr else 0}")
print("\nStdout content:")
print(result.stdout)
if result.stderr:
    print("\nStderr content:")
    print(result.stderr)
print("=" * 60)

print("\n\nTesting version --help directly:")
print("=" * 60)
result = runner.invoke(cli, ["version", "--help"])
print(f"Exit code: {result.exit_code}")
print(f"Stdout length: {len(result.stdout)}")
print("\nStdout content:")
print(result.stdout)
print("=" * 60)
