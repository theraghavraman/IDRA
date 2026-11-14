from idra.events.models import State

TRANSITIONS = {
    State.IDLE: {State.STARTING},
    State.STARTING: {State.RECORDING, State.STOPPING, State.FAILED},
    State.RECORDING: {State.PAUSED, State.STOPPING},
    State.PAUSED: {State.RECORDING, State.STOPPING},
    State.STOPPING: {State.COMPLETED, State.FAILED},
    State.COMPLETED: {State.STARTING},
    State.FAILED: {State.STARTING},
    State.INTERRUPTED: {State.STARTING},
}

def transition(current: State, target: State) -> State:
    if target not in TRANSITIONS[current]:
        raise RuntimeError(f"Invalid recording transition: {current.value} -> {target.value}")
    return target
