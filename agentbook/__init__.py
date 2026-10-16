"""agentbook: a small agent harness for Tutorial 1, Building a Tool-Using Agent.

    from agentbook import FakeModel, call, ToolRegistry, run_agent, registry_tools
    tools = ToolRegistry(registry_tools())
    result = run_agent(FakeModel([...]), tools, "Which observables constrain ...?")
"""

from .loop import AgentResult, run_agent
from .models import (AnthropicModel, FakeModel, Model, ModelResponse, OpenAIModel, Usage,
                     call, text_block, tool_result_block, tool_use_block)
from .registry import Registry, STATUS, default_registry, registry_tools
from .tools import Tool, ToolError, ToolRegistry, truncate
from .tracing import Tracer, format_messages, format_trace, load_trace, print_trace, summarize_trace

__all__ = [
    "AgentResult", "run_agent", "AnthropicModel", "FakeModel", "Model", "ModelResponse",
    "OpenAIModel", "Usage", "call", "text_block", "tool_result_block", "tool_use_block",
    "Registry", "STATUS", "default_registry", "registry_tools", "Tool", "ToolError",
    "ToolRegistry", "truncate", "Tracer", "format_messages", "format_trace", "load_trace", "print_trace",
    "summarize_trace",
]
