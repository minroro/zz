from .contact import ContactInfo, extract_contacts
from .criteria import ChannelCriteria
from .models import ChannelInfo

__all__ = [
    "ChannelCriteria",
    "ChannelInfo",
    "ContactInfo",
    "extract_contacts",
    "ChannelSearcher",
    "find_channels",
    "discover_channels",
    "DiscoveryResult",
    "DiscoveredChannel",
    "IntentPlan",
    "JudgeVerdict",
]


def __getattr__(name: str):
    # Lazy-load symbols that depend on third-party SDKs so the rest of the
    # package stays importable in environments without them installed.
    if name == "ChannelSearcher":
        from .search import ChannelSearcher

        return ChannelSearcher
    if name == "find_channels":
        from .pipeline import find_channels

        return find_channels
    if name in {"discover_channels", "DiscoveryResult", "DiscoveredChannel"}:
        from . import discover

        return getattr(discover, name)
    if name in {"IntentPlan", "JudgeVerdict"}:
        from . import llm

        return getattr(llm, name)
    raise AttributeError(f"module 'youtube_finder' has no attribute {name!r}")
