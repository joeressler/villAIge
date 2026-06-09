from simulation_core.world import World

__all__ = ["TickEngine", "World"]


def __getattr__(name: str):
    if name == "TickEngine":
        from simulation_core.tick_engine import TickEngine

        return TickEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
