__all__ = ["create_phase2_app"]


def __getattr__(name: str):
    if name == "create_phase2_app":
        from .phase2 import create_phase2_app

        return create_phase2_app
    raise AttributeError(name)
