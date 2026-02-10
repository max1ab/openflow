class AgentError(Exception):
    """Base error for all agent-related exceptions."""


class AgentConfigError(AgentError):
    """Raised when agent parameters are invalid."""


class AgentExecutionError(AgentError):
    """Raised when provider execution fails."""


class AgentParseError(AgentError):
    """Raised when provider output cannot be parsed."""
