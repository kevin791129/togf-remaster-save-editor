class SaveError(ValueError):
    """The save (or a decoded part of it) is not in the expected format."""


class ReadOnlyError(ValueError):
    """A write to a read-only field without force."""
