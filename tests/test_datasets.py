import json
import threading
import pytest
from idra.datasets.export import ExportError, assign_split, export_dataset, verify_export
from idra.datasets.quality import validate_session
from idra.events.models import SegmentationConfig
from idra.media.ffmpeg import Cancelled
from idra.segmentation.trajectories import trajectories
from idra.storage.files import iter_jsonl


def rewrite(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def test_quality_on_real_fixture(recorded):
    repo, sid = recorded
    report = validate_session(repo, sid, full_decode=True)
    assert report['errors'] == 0, report
    assert (repo.path(sid)/'reports/quality.json').is_file()
    assert (repo.path(sid)/'reports/quality.html').is_file()


def test_quality_detects_deliberately_broken_fixture(recorded):
    repo, sid = recorded
    path = repo.path(sid)
    rows = list(iter_jsonl(path/'events.jsonl'))
    rows.append(rows[0])
    rows[1]['payload']['in_capture'] = True
    rows[1]['payload']['x_px'] = 99999
    rows[1]['payload']['y_px'] = 99999
    rows.append({'bad':'schema'})
    rewrite(path/'events.jsonl', rows)
    frames = list(iter_jsonl(path/'frames.jsonl'))
    shot = next(f['screenshot'] for f in frames if f['screenshot'])
    (path/shot).unlink()
    report = validate_session(repo, sid)
    codes = report['issue_counts']
    assert {'DUPLICATE_EVENT','INVALID_COORDINATES','EVENT_SCHEMA','MISSING_SCREENSHOT'} <= codes.keys()
    assert report['errors'] >= 4


def test_timestamp_disorder_is_not_silently_corrected(recorded):
    repo, sid = recorded
    path = repo.path(sid)
    rows = list(iter_jsonl(path/'events.jsonl'))
    rows[-1]['t_ns'] = 0
    rewrite(path/'events.jsonl', rows)
    report = validate_session(repo,sid)
    assert report['issue_counts']['OCCURRENCE_ORDER'] > 0


def test_bad_frame_index_and_hash_detected(recorded):
    repo, sid = recorded
    path = repo.path(sid)
    rows = list(iter_jsonl(path/'frames.jsonl'))
    rows[0]['index'] = 12
    rows[0]['sha256'] = '0'*64
    rewrite(path/'frames.jsonl', rows)
    result = validate_session(repo,sid)
    assert result['issue_counts']['FRAME_INDEX_GAP'] > 0
    assert result['issue_counts']['SCREENSHOT_CHECKSUM'] > 0


def test_trajectories_are_stable_bounded_and_not_inferred(recorded):
    repo,sid = recorded
    config=SegmentationConfig(max_actions=2)
    first = list(trajectories(repo.path(sid),repo.load(sid),config))
    second = list(trajectories(repo.path(sid),repo.load(sid),config))
    assert first and first == second
    assert all(len(t.actions) <= 2 for t in first)
    assert all(a.type != 'mouse_move' for t in first for a in t.actions)
    assert all(t.task_completion in {'user_marked_complete','unconfirmed','interrupted'} for t in first)
    assert all(a.outcome == 'not_inferred' for t in first for a in t.actions)


def test_session_split_stable_and_valid():
    assert assign_split('session-a') == assign_split('session-a')
    assert assign_split('anything', (1,0,0)) == 'train'
    assert assign_split('anything', (0,1,0)) == 'validation'
    assert assign_split('anything', (0,0,1)) == 'test'
    with pytest.raises(ValueError):
        assign_split('bad',(0.9,0.2,0))


def test_metadata_only_export_reimport_and_session_split(recorded,tmp_path):
    repo,sid = recorded
    target=tmp_path/'dataset'
    result=export_dataset(repo,[sid],target)
    assert result['verification']['status']=='passed'
    assert not result['manifest']['media_included']
    assert not list((target/'sessions').rglob('*.mkv'))
    assert not list((target/'sessions').rglob('*.png'))
    frames=list(iter_jsonl(target/'frames.jsonl'))
    assert all(f['screenshot'] is None and not f['media_available'] for f in frames)
    splits=list(iter_jsonl(target/'splits.jsonl'))
    assert len({s['split'] for s in splits}) == 1
    assert verify_export(target)['counts']['events'] > 0


def test_media_export_requires_review_then_copies_valid_assets(recorded,tmp_path):
    repo,sid = recorded
    target=tmp_path/'reviewed'
    with pytest.raises(PermissionError):
        export_dataset(repo,[sid],target,include_media=True)
    result=export_dataset(repo,[sid],target,include_media=True,media_reviewed=True)
    assert result['manifest']['media_review_attested']
    assert result['verification']['counts']['assets'] > 0
    assert list(target.rglob('*.mkv')) and list(target.rglob('*.png'))
    assert verify_export(target)['status']=='passed'


def test_dataset_tampering_rejected(recorded,tmp_path):
    repo,sid=recorded
    target=tmp_path/'tamper'
    export_dataset(repo,[sid],target)
    with (target/'events.jsonl').open('a') as f:
        f.write('{}\n')
    with pytest.raises(ExportError,match='checksum'):
        verify_export(target)


def test_media_asset_tampering_rejected(recorded,tmp_path):
    repo,sid=recorded
    target=tmp_path/'tamper-media'
    export_dataset(repo,[sid],target,include_media=True,media_reviewed=True)
    shot=next(target.rglob('*.png'))
    shot.write_bytes(b'corrupt')
    with pytest.raises(ExportError):
        verify_export(target)


def test_dataset_cancelled_export_is_atomic(recorded,tmp_path):
    repo,sid=recorded
    cancel=threading.Event();cancel.set()
    target=tmp_path/'cancelled'
    with pytest.raises(Cancelled):
        export_dataset(repo,[sid],target,cancel=cancel)
    assert not target.exists()
    assert not list(tmp_path.glob('.cancelled.*.partial'))


def test_invalid_session_blocks_export(recorded,tmp_path):
    repo,sid=recorded
    (repo.path(sid)/'events.jsonl').write_text('{}\n')
    target=tmp_path/'invalid'
    with pytest.raises(ExportError):
        export_dataset(repo,[sid],target)
    assert not target.exists()


def test_task_mode_explicitly_warns_about_leakage(recorded,tmp_path):
    repo,sid=recorded
    result=export_dataset(repo,[sid],tmp_path/'task-split',split_unit='task')
    assert result['manifest']['splitting']['same_session_across_splits_possible']
