"""Custom exceptions for EmberRoute.

Defines FeedError for network/feed issues and custom warning classes.
"""


class FeedError(Exception):
    """Raised when an external data feed fails, times out, or returns invalid data.

    Attributes:
        source: Name or identifier of data feed (e.g. 'NASA FIRMS', 'Open-Meteo').
        url: URL attempted.
        message: Specific failure details.
    """

    def __init__(self, message: str = "", source: str = "", url: str = "") -> None:
        self.source = source
        self.url = url
        self.message = message
        full_msg = f"[{source}] {message} ({url})" if source else message
        super().__init__(full_msg)


class StaleCacheWarning(UserWarning):
    """Warning emitted when serving expired cache data on feed failure."""

    pass

