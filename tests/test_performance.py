import pytest
from idra.diagnostics.benchmark import measure_ingestion

@pytest.mark.performance
def test_sustained_bounded_ingestion_persists_all_events():
    r=measure_ingestion(3000,queue_size=64,minimum_seconds=1)
    assert r['events']>=3000
    assert r['seconds']>=1
    assert r['observed_peak_queue']<=64
    assert r['dropped_events']==0
    # Throughput is reported, not asserted against a hardware-dependent universal rate.
    assert r['events_per_second']>0
