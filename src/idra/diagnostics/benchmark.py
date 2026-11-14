"""Measured bounded ingestion workload; not a desktop throughput certification."""
from __future__ import annotations
import platform
import tempfile
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from idra.events.models import Event, Payload
from idra.storage.files import iter_jsonl
from idra.storage.journal import Journal


def measure_ingestion(count=20000, queue_size=256, minimum_seconds=0.0):
    if count < 1 or queue_size < 1 or not 0 <= minimum_seconds <= 3600:
        raise ValueError('Invalid benchmark parameters')
    with tempfile.TemporaryDirectory(prefix='idra-benchmark-') as temp:
        directory=Path(temp)
        journal=Journal(directory,queue_size=queue_size,batch_size=128,flush_interval=.05)
        journal.start()
        sid=uuid4();utc=datetime.now(timezone.utc)
        tracemalloc.start()
        started=time.perf_counter();peak_queue=0;accepted=0
        try:
            while accepted < count or time.perf_counter()-started < minimum_seconds:
                event=Event(session_id=sid,sequence=accepted,t_ns=accepted,received_t_ns=accepted,
                    utc=utc,type='mouse_move',source='synthetic',synthetic=True,
                    payload=Payload(x=100,y=100,coordinate_space='desktop'))
                if not journal.submit(event,essential=True):
                    raise RuntimeError('Benchmark could not persist all generated events')
                accepted+=1;peak_queue=max(peak_queue,journal.queue.qsize())
            journal.close(timeout=120)
            elapsed=time.perf_counter()-started
            _,peak_memory=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
            if journal.thread.is_alive():journal.close(timeout=120)
        observed=sum(1 for _ in iter_jsonl(directory/'events.jsonl'))
        if observed != accepted or journal.stats().get('dropped_events',0):
            raise RuntimeError('Benchmark lost records')
        return {'benchmark':'bounded_journal_ingestion','synthetic':True,'python':platform.python_version(),
            'platform':platform.platform(),'machine':platform.machine(),'events':observed,
            'seconds':elapsed,'events_per_second':observed/elapsed,
            'configured_queue_capacity':queue_size,'observed_peak_queue':peak_queue,
            'python_tracemalloc_peak_bytes':peak_memory,'event_journal_bytes':(directory/'events.jsonl').stat().st_size,
            'target_events_per_second':1000,'target_met':observed/elapsed>=1000,
            'dropped_events':journal.stats().get('dropped_events',0),
            'limitations':['Controlled synthetic ingestion, not real desktop or native input-hook throughput.',
                'tracemalloc excludes native allocations, media subprocesses, GPU buffers and OS page cache.',
                'No multi-hour capture, sleep/wake, display-hotplug or SSD-exhaustion hardware certification.']}
