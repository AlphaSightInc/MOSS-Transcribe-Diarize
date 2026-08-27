__all__ = ["create_app"]


def __getattr__(name: str):
    # Phase 2's account-only boot path must not import Phase 1's model/audio stack.
    # Keep the established public ``moss_transcribe_diarize.app.create_app`` export intact.
    if name == "create_app":
        from .server import create_app

        return create_app
    raise AttributeError(name)
