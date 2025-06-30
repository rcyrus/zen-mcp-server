"""
Research Tool for Zen MCP Server.

A SimpleTool that provides fast, effective web search capabilities using Perplexity Sonar models.
Optimized for technical documentation, development resources, and current information retrieval.
"""

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from tools.shared.base_models import ToolRequest
from tools.simple.base import SimpleTool

logger = logging.getLogger(__name__)


class ResearchRequest(ToolRequest):
    """
    Request model for ResearchTool.

    Extends ToolRequest with research-specific parameters for controlling
    Perplexity search behavior and result formatting.
    """

    query: str = Field(
        ...,
        description="Search query or question for web research. Be specific for better results.",
    )

    domain_filter: Optional[list[str]] = Field(
        default=None,
        description="Domains to focus search on (e.g., ['stackoverflow.com', 'github.com']). Use '-' prefix to exclude.",
    )

    recency_filter: Optional[str] = Field(
        default=None,
        description="How recent the information should be: 'hour', 'day', 'week', 'month', 'year'",
    )

    search_mode: Optional[str] = Field(
        default="medium",
        description="Search quality vs speed trade-off: 'web', 'high', 'medium', 'low'",
    )

    return_related_questions: Optional[bool] = Field(
        default=True,
        description="Include suggested related questions for further research",
    )

    max_tokens: Optional[int] = Field(
        default=2048,
        ge=100,
        le=4096,
        description="Maximum tokens for response. Higher values allow more comprehensive results",
    )


class Source(BaseModel):
    """
    Model representing a source of information from web search.

    Captures key metadata about each source including title, URL,
    publication date, and optional snippet content.
    """

    title: Optional[str] = Field(None, description="Title of the source document or page")
    url: str = Field(..., description="URL of the source")
    date: Optional[str] = Field(None, description="Publication or last modified date")
    snippet: Optional[str] = Field(None, description="Brief excerpt or snippet from the source")


class ResearchResponse(BaseModel):
    """
    Response model for ResearchTool.

    Structures the AI's research findings with comprehensive metadata
    including sources, search efficiency metrics, and related questions.
    """

    answer: str = Field(..., description="Main research findings and analysis")

    sources: Optional[list[Source]] = Field(
        default=None,
        description="List of sources used in the research",
    )

    citations: Optional[list[str]] = Field(
        default=None,
        description="List of citation URLs (fallback if sources not available)",
    )

    related_questions: Optional[list[str]] = Field(
        default=None,
        description="Suggested questions for further research",
    )

    search_metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Search performance and quality metrics",
    )


class ResearchTool(SimpleTool):
    """
    Fast web research tool using Perplexity Sonar models.

    Provides targeted web search capabilities with rich metadata including:
    - Search domain filtering (focus on technical sites)
    - Temporal filtering (recent, fresh information)
    - Quality optimization (balanced search vs performance)
    - Source citations and verification
    - Related questions for deeper exploration

    Ideal for:
    - Technical documentation lookup
    - Framework/library research
    - Best practices discovery
    - Current development trends
    - API reference verification
    """

    def get_name(self) -> str:
        """Return the tool name."""
        return "research"

    def get_description(self) -> str:
        """Return the tool description."""
        return "Fast web research using Perplexity Sonar for technical information and current developments"

    def get_request_model(self):
        """Return the request model class."""
        return ResearchRequest

    def get_tool_fields(self) -> dict[str, dict[str, Any]]:
        """
        Define the input schema for ResearchTool.

        Returns:
            Dict mapping field names to JSON schema definitions
        """
        return {
            "query": {
                "type": "string",
                "description": "Search query or question for web research. Be specific for better results.",
            },
            "domain_filter": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Domains to focus search on (e.g., ['stackoverflow.com', 'github.com']). Use '-' prefix to exclude.",
                "default": [],
            },
            "recency_filter": {
                "type": "string",
                "enum": ["hour", "day", "week", "month", "year"],
                "description": "How recent the information should be. Default: no filter (all time)",
            },
            "search_mode": {
                "type": "string",
                "enum": ["web", "high", "medium", "low"],
                "description": "Search quality vs speed trade-off. 'web' for comprehensive, 'high' for detailed, 'medium' balanced, 'low' for fast",
                "default": "medium",
            },
            "return_related_questions": {
                "type": "boolean",
                "description": "Include suggested related questions for further research",
                "default": True,
            },
            "max_tokens": {
                "type": "integer",
                "minimum": 100,
                "maximum": 4096,
                "description": "Maximum tokens for response. Higher values allow more comprehensive results",
                "default": 2048,
            },
        }

    def get_required_fields(self) -> list[str]:
        """Return list of required field names."""
        return ["query"]

    def get_default_model(self) -> str:
        """Return the default model for this tool."""
        return "sonar-pro"

    def get_system_prompt(self) -> str:
        """Get the system prompt for research tasks."""
        from systemprompts.research_prompt import RESEARCH_PROMPT

        return RESEARCH_PROMPT

    async def prepare_prompt(self, request) -> str:
        """
        Prepare the prompt for web research.

        Args:
            request: Validated ResearchRequest object

        Returns:
            Formatted prompt for the AI model
        """
        query = request.query

        # Build prompt with research context
        prompt = f"""Please research this query using web search: {query}

Research Guidelines:
- Focus on accurate, up-to-date information
- Prioritize authoritative sources (official docs, well-known tech sites)
- Include specific examples and practical information
- Provide clear citations and source references
- Synthesize information from multiple sources when relevant

Query to research: {query}"""

        return prompt

    def get_perplexity_params(self, request) -> dict[str, Any]:
        """
        Extract Perplexity-specific parameters from the request.

        Args:
            request: Validated request object

        Returns:
            Dictionary of Perplexity API parameters
        """
        params = {}
        # Domain filtering
        if hasattr(request, "domain_filter") and request.domain_filter:
            params["search_domain_filter"] = request.domain_filter

        # Recency filtering
        if hasattr(request, "recency_filter") and request.recency_filter:
            params["search_recency_filter"] = request.recency_filter

        # Search mode
        if hasattr(request, "search_mode") and request.search_mode:
            params["search_mode"] = request.search_mode
        else:
            params["search_mode"] = "medium"  # Default balanced mode

        # Related questions
        if hasattr(request, "return_related_questions"):
            params["return_related_questions"] = request.return_related_questions
        else:
            params["return_related_questions"] = True  # Default enabled

        # Max tokens
        if hasattr(request, "max_tokens") and request.max_tokens:
            params["max_tokens"] = request.max_tokens
        else:
            params["max_tokens"] = 2048  # Default

        return params

    def format_response(self, response: str, request, model_info: Optional[dict] = None) -> str:
        """
        Format the research response with robust extraction and display of all possible source URLs (citations, source_urls, citation_urls, search_results).
        """
        formatted_response = response

        # Add source information if available
        # Extraction et affichage des citations : priorité aux search_results (titre+url)
        all_urls = []
        seen = set()
        search_results_structured = []
        if model_info and "metadata" in model_info:
            metadata = model_info["metadata"]
            # 1. search_results (format structuré recommandé)
            if "search_results" in metadata and metadata["search_results"]:
                for r in metadata["search_results"]:
                    url = r.get("url")
                    title = r.get("title")
                    if url and url not in seen:
                        if title:
                            search_results_structured.append((title, url))
                        all_urls.append(url)
                        seen.add(url)
            # 2. autres champs (compatibilité ascendante)
            url_sets = []
            if "citations" in metadata and metadata["citations"]:
                url_sets.append(metadata["citations"])
            if "source_urls" in metadata and metadata["source_urls"]:
                url_sets.append(metadata["source_urls"])
            if "citation_urls" in metadata and metadata["citation_urls"]:
                url_sets.append(metadata["citation_urls"])
            if "sources" in metadata and metadata["sources"]:
                sources_urls = []
                for src in metadata["sources"]:
                    url = src.get("url")
                    if url:
                        sources_urls.append(url)
                if sources_urls:
                    url_sets.append(sources_urls)
            for url_list in url_sets:
                for url in url_list:
                    if url and url not in seen:
                        all_urls.append(url)
                        seen.add(url)
        # 3. Extraction des URLs Markdown du texte brut
        import re

        markdown_urls = re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", response)
        for _, url in markdown_urls:
            if url and url not in seen:
                all_urls.append(url)
                seen.add(url)

        # Affichage citations : priorité search_results (titre+url), sinon URLs brutes
        if model_info and "metadata" in model_info:
            metadata = model_info["metadata"]
            if search_results_structured:
                formatted_response += "\n\n## Sources\n"
                # Ajout de la date si disponible dans search_results
                for i, (title, url) in enumerate(search_results_structured, 1):
                    # Chercher la date dans search_results d'origine
                    date_str = None
                    for r in metadata.get("search_results", []):
                        if r.get("title") == title and r.get("url") == url:
                            date_str = r.get("date")
                            break
                    if date_str:
                        formatted_response += f"\n{i}. [{title}]({url}) ({date_str})"
                    else:
                        formatted_response += f"\n{i}. [{title}]({url})"
            elif all_urls:
                formatted_response += "\n\n## Citations\n"
                for i, url in enumerate(all_urls, 1):
                    formatted_response += f"\n{i}. {url}"

            # Post-traitement : remplacer les lignes de sources brutes par le format Markdown si possible
            def replace_sources_block(text, all_urls):
                pattern = r"(\*\*?Sources cit[ée]es? ?:?\*\*?\n)((?:.+\n?)+)"
                match = re.search(pattern, text, re.IGNORECASE)
                if not match:
                    return text
                block_start, block_content = match.group(1), match.group(2)
                lines = block_content.strip().split("\n")
                new_lines = []
                url_idx = 0
                for line in lines:
                    if re.search(r"\[.+\]\(https?://", line):
                        new_lines.append(line)
                        continue
                    if url_idx < len(all_urls):
                        m = re.match(r"\[\d+\] ?(.+)", line)
                        title = m.group(1).strip() if m else line.strip()
                        url = all_urls[url_idx]
                        new_lines.append(f"[{title}]({url})")
                        url_idx += 1
                    else:
                        new_lines.append(line)
                new_block = block_start + "\n".join(new_lines) + "\n"
                return text[: match.start()] + new_block + text[match.end() :]

            formatted_response = replace_sources_block(formatted_response, all_urls)

            # Add related questions if available
            if "related_questions" in metadata:
                related_questions = metadata["related_questions"]
                if related_questions:
                    formatted_response += "\n\n## Related Questions\n"
                    for question in related_questions:
                        formatted_response += f"\n{question}"

            # Add search efficiency info if available
            if "search_efficiency" in metadata:
                efficiency = metadata["search_efficiency"]
                queries_count = metadata.get("search_queries_count", "unknown")
                formatted_response += f"\n\n---\n*Search efficiency: {efficiency:.2f} | Queries used: {queries_count}*"

        return formatted_response

    async def execute(self, arguments: dict[str, Any]) -> list:
        """
        Execute the research tool with Perplexity-specific parameters.

        This overrides the base execute method to inject Perplexity parameters
        before calling the parent implementation.
        """
        # Create request object to access parameters
        request_model = self.get_request_model()
        request = request_model(**arguments)

        # Get Perplexity-specific parameters
        perplexity_params = self.get_perplexity_params(request)

        # Inject Perplexity parameters into arguments
        enhanced_arguments = {**arguments, **perplexity_params}

        # Call parent execute with enhanced arguments
        return await super().execute(enhanced_arguments)
