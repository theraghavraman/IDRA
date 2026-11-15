"""Deterministic bounded trajectories; no inferred task success or action descriptions."""
from __future__ import annotations

import hashlib
from uuid import uuid5

from idra.events.models import Action, SegmentationConfig, State, Trajectory
from idra.storage.repository import connect_index, iter_events, neighboring_frames

_ACTIONS = {"mouse_button_down", "mouse_button_up", "scroll", "key_press", "key_release",
            "browser_action", "browser_navigation"}

def trajectories(directory, manifest, config: SegmentationConfig | None = None, *, media_available=True):
    config = config or SegmentationConfig()
    actions, annotations = [], []
    current_description = manifest.task_description
    last_action_time = None
    annotation_overflow = 0
    config_hash = hashlib.sha256(config.model_dump_json().encode()).hexdigest()[:16]
    task_id = uuid5(manifest.session_id, "initial-task")
    conn = connect_index(directory, readonly=True)
    def make(reason, completion="unconfirmed"):
        if not actions:
            return None
        return Trajectory(session_id=manifest.session_id,
            trajectory_id=uuid5(manifest.session_id, f"{actions[0].event_id}:{actions[-1].event_id}:{config_hash}"),
            task_description=current_description, start_t_ns=actions[0].t_ns, end_t_ns=actions[-1].t_ns,
            boundary_reason=reason, task_completion="interrupted" if manifest.state != State.COMPLETED else completion,
            synthetic=manifest.synthetic, actions=list(actions), annotations=list(annotations),
            quality={"task_group_id":str(task_id), "missing_context_actions":sum(a.before_frame is None and a.after_frame is None for a in actions),
                     "annotation_context_overflow":annotation_overflow,
                     "ground_truth_success_inferred":False,
                     "unverified_browser_actions":sum(a.type == "browser_action" for a in actions),
                     "browser_human_provenance_verified":False})
    try:
        for event in iter_events(directory):
            if event.type == "state_change" and event.payload.state in {State.PAUSED, State.STOPPING}:
                result = make(event.payload.state.value.lower())
                if result:
                    yield result
                actions, annotations, last_action_time, annotation_overflow = [], [], None, 0
                continue
            if event.type == "task_boundary":
                if event.payload.boundary == "start":
                    result = make("user_task_start")
                    if result:
                        yield result
                    actions, annotations, last_action_time, annotation_overflow = [], [], None, 0
                    current_description = event.payload.text or manifest.task_description
                    task_id = uuid5(manifest.session_id, str(event.event_id))
                    annotations.append(event)
                else:
                    annotations.append(event)
                    result = make("user_task_end", "user_marked_complete")
                    if result:
                        yield result
                    actions, annotations, last_action_time, annotation_overflow = [], [], None, 0
                    task_id = uuid5(manifest.session_id, "after:" + str(event.event_id))
                continue
            if event.type == "annotation":
                if len(annotations) < 256:
                    annotations.append(event)
                else:
                    annotation_overflow += 1
                continue
            if event.type not in _ACTIONS:
                continue
            boundary = None
            if last_action_time is not None and event.t_ns - last_action_time > config.inactivity_s * 1e9:
                boundary = "inactivity"
            elif config.navigation_boundaries and event.type == "browser_navigation" and event.payload.action == "start":
                boundary = "browser_navigation"
            elif len(actions) >= config.max_actions:
                boundary = "size_limit_continuation"
            if boundary:
                result = make(boundary)
                if result:
                    yield result
                actions, annotations, annotation_overflow = [], [], 0
                if boundary != "size_limit_continuation":
                    task_id = uuid5(manifest.session_id, "boundary:" + str(event.event_id))
            before, after = neighboring_frames(conn, event.t_ns)
            # Sampling selects context indexes without rewriting canonical media.
            if config.frame_stride > 1:
                from idra.events.models import Frame
                def sampled(operator, order, target_t_ns=event.t_ns):
                    row = conn.execute(f"SELECT data FROM frames WHERE t_ns {operator} ? AND frame_index % ?=0 ORDER BY t_ns {order} LIMIT 1",
                                       (target_t_ns, config.frame_stride)).fetchone()
                    f = Frame.model_validate_json(row[0]) if row else None
                    return f if f and abs(f.t_ns-target_t_ns) <= 3_000_000_000 else None
                before, after = sampled("<=", "DESC"), sampled(">=", "ASC")
            actions.append(Action(event_id=event.event_id, t_ns=event.t_ns, type=event.type, payload=event.payload,
                before_frame=before.index if before else None, after_frame=after.index if after else None,
                context_status="media_excluded" if not media_available else "available" if before or after else "missing"))
            last_action_time = event.t_ns
        result = make("session_end")
        if result:
            yield result
    finally:
        conn.close()
