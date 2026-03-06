# Coding Agent Examples

This directory contains examples of how to build a coding agent in Python.

## Files

- **agent.py** - Core agent implementation with all tools
- **agent_anthropic.py** - Integration with Anthropic Claude

## Core Concepts

### 1. Agent Architecture

A coding agent consists of:

```
┌─────────────────────────────────────────────────────────┐
│                    CODING AGENT                         │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐                  │
│  │  System      │    │    LLM       │                  │
│  │  Prompt      │───▶│  (GPT/Claude)│                  │
│  └──────────────┘    └──────┬───────┘                  │
│                             │                           │
│                      ┌──────▼───────┐                  │
│                      │  Tool Router │                  │
│                      └──────┬───────┘                  │
│                             │                           │
│  ┌──────────────────────────┼──────────────────────┐   │
│  │                    TOOLS                         │   │
│  ├──────────┬──────────┬──────────┬────────────────┤   │
│  │read_file │write_file│edit_file │ run_command    │   │
│  │list_dir  │search    │          │                │   │
│  └──────────┴──────────┴──────────┴────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### 2. The Agent Loop

```python
while not done:
    1. Send user request + conversation history to LLM
    2. LLM decides: respond OR use tools
    3. If tool_calls:
        - Execute each tool
        - Add results to conversation
        - Go to step 1
    4. If no tool_calls:
        - Return LLM response to user
        - Done!
```

### 3. Essential Tools

| Tool | Purpose |
|------|---------|
| `read_file` | Read code to understand context |
| `write_file` | Create new files |
| `edit_file` | Modify existing code |
| `run_command` | Execute shell commands (tests, installs) |
| `list_dir` | Explore project structure |
| `search_code` | Find relevant code by pattern |

### 4. Key Design Principles

1. **Security** - Sandbox file access to workspace, limit command execution
2. **Iteration** - Set max iterations to prevent infinite loops
3. **Context** - Always read before editing
4. **Validation** - Check results after making changes

## Installation

```bash
pip install openai anthropic
```

## Usage

```python
from agent import CodingAgent

# Create agent
agent = CodingAgent(workspace_path="/path/to/project")

# Run a task
response = agent.run("Add error handling to the main.py file")
print(response)
```

## Environment Variables

```powershell
# For OpenAI
$env:OPENAI_API_KEY = "sk-..."

# For Anthropic
$env:ANTHROPIC_API_KEY = "sk-ant-..."
```
