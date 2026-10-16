"""One solution to exercise 2: a tool that lists the models extracted from one paper."""

from agentbook import Tool, ToolError
from agentbook.registry import STATUS, default_registry


def models_from_paper(arxiv_id: str) -> dict:
    reg = default_registry()
    arxiv_id = arxiv_id.removeprefix("arXiv:").strip()
    hits = [{"model_id": mid, "name": e["name"], "family": e["family"], "enriched": e["enriched"]}
            for mid, e in sorted(reg.index.items()) if e["arxiv"] == arxiv_id]
    if not hits:
        raise ToolError(f"No models from arXiv:{arxiv_id} in the registry. Check the ID "
                        "(e.g. 2403.15533), or use search_models with words from the title.")
    return {"arxiv": arxiv_id, "models": hits, "status": STATUS}


MODELS_FROM_PAPER = Tool(
    "models_from_paper",
    "List the dark-matter models the registry extracted from one arXiv paper, with their IDs, "
    "names, families and whether the card is enriched. Use it when the user names a paper; "
    "use search_models when they describe a model.",
    {"type": "object", "properties": {
        "arxiv_id": {"type": "string", "description": "arXiv ID, e.g. '2403.15533' or 'hep-ph/9901234'."}},
     "required": ["arxiv_id"], "additionalProperties": False},
    models_from_paper)
