"""Your own tools. run_live.py adds everything in MY_TOOLS to the registry tools.

A tool is a name, a description the model reads, a JSON schema for its
arguments, and a Python function. Raise ToolError with a message the model
can act on when something goes wrong; it goes back to the model as a result.

Exercise (see EXERCISES.md): add a tool that answers
"Which models in the registry come from arXiv:2403.15533?"
"""

from agentbook import Tool, ToolError  # noqa: F401  (ToolError is for your tools)
from agentbook.registry import STATUS, default_registry  # noqa: F401

MY_TOOLS: list[Tool] = []
