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
]


def __getattr__(name: str):
    # Lazy-load symbols that depend on google-api-python-client so the rest of
    # the package stays importable in environments without the SDK installed.
    if name == "ChannelSearcher":
        from .search import ChannelSearcher

        return ChannelSearcher
    if name == "find_channels":
        from .pipeline import find_channels

        return find_channels
    raise AttributeError(f"module 'youtube_finder' has no attribute {name!r}")
