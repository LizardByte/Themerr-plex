"""Allowlisted validation messages that can be returned to the browser."""

# standard imports
from enum import Enum


class ValidationMessage(Enum):
    """Fixed explanations for expected administrator input errors."""

    USERNAME_LENGTH = 'Use a username between 3 and 64 characters.'
    PASSWORD_LENGTH = 'Use a password between 12 and 256 characters.'
    PASSWORD_MISMATCH = 'The passwords do not match.'
    PLEX_ACCOUNT_REQUIRED = 'Connect your Plex account first.'
    PLEX_ADDRESS_INVALID = 'Enter a valid Plex server address.'
    PLEX_ADDRESS_CHARACTERS = 'The server address contains invalid characters.'
    PLEX_BASE_ADDRESS_REQUIRED = 'Use an HTTP or HTTPS address without credentials, a query, or a path.'
    PLEX_PORT_INVALID = 'Invalid server port.'
    PLEX_SERVER_UNAVAILABLE = 'This server is not available to the connected Plex account.'
    PLEX_IDENTIFIER_INVALID = 'Plex did not provide a valid machine identifier.'
    PLEX_SERVER_MISMATCH = 'This address belongs to a different Plex server.'
    SERVER_NOT_FOUND = 'Server not found.'
    SERVER_ENABLED_INVALID = 'Enabled must be a boolean.'
    SERVER_SETTING_INVALID = 'Invalid server setting.'


class ValidationError(ValueError):
    """An expected input failure with a message from the fixed public catalog."""

    def __init__(self, reason: ValidationMessage):
        """Select a public message without accepting arbitrary exception text.

        Parameters
        ----------
        reason : ValidationMessage
            Known validation failure safe to describe in the browser.

        Raises
        ------
        TypeError
            The reason is not a member of the public message catalog.
        """
        if not isinstance(reason, ValidationMessage):
            raise TypeError('Validation errors require a catalog message.')
        self.reason = reason
        super().__init__(reason.value)
