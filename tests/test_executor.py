import copy
from pathlib import Path
import pytest
from uripack_refactor.common import UripackError, load_document
from uripack_refactor.executor import apply_plan, verify_artifact, STATE_PATH, _publish_no_replace
from uripack_refactor.journal import verify_chain
from conftest import RecordingGuard

def _snapshot(root):
    return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}

def test_apply_roundtrip_and_source_unchanged(sample,plan,guard):
    before=_snapshot(sample[0])
    result=apply_plan(plan,guard)
    assert result['status']=='EXTRACTED'
    assert _snapshot(sample[0])==before
    assert not result['production_cutover'] and not result['git_effects']
    assert verify_chain(result['events'])
    assert verify_artifact(plan)['status']=='passed'
    assert [a for a,_ in guard.calls]==['admit','tool','publish','complete']

def test_idempotency_does_not_repeat_tools(plan,guard):
    apply_plan(plan,guard)
    n=len(guard.calls)
    result=apply_plan(plan,guard)
    assert result['already_materialized'] and not result['replayed']
    assert len(guard.calls)==n

@pytest.mark.parametrize('action',['admit','tool','publish'])
def test_denial_no_target_and_source_unchanged(sample,plan,action):
    before=_snapshot(sample[0])
    with pytest.raises(UripackError): apply_plan(plan,RecordingGuard(deny=action))
    assert not sample[1].exists()
    assert _snapshot(sample[0])==before
    assert not list(sample[1].parent.glob('.*.uripack-stage-*'))

def test_completion_denied_preserves_artifact_for_reconciliation(sample,plan):
    with pytest.raises(UripackError,match='materialized'): apply_plan(plan,RecordingGuard(deny='complete'))
    assert sample[1].exists()
    receipt=load_document(sample[1]/STATE_PATH)
    assert receipt['status']=='MATERIALIZED_PENDING_COMPLETION'
    with pytest.raises(UripackError,match='reconcile'): apply_plan(plan,RecordingGuard())

def test_source_mutates_during_check(sample,plan):
    def hook(action,p,payload):
        if action=='tool': (sample[0]/'unit/main.py').write_text('changed')
    with pytest.raises(UripackError): apply_plan(plan,RecordingGuard(hook=hook))
    assert not sample[1].exists()

def test_verifier_cannot_mutate_artifact(sample,plan):
    def hook(action,p,payload):
        if action=='tool': (Path(payload['staging_root'])/'packs/count/tree/unit/main.py').write_text('changed')
    with pytest.raises(UripackError): apply_plan(plan,RecordingGuard(hook=hook))
    assert not sample[1].exists()

def test_verifier_cannot_add_hidden_git_effect(sample,plan):
    def hook(action,p,payload):
        if action=='tool':
            d=Path(payload['staging_root'])/'.git';d.mkdir();(d/'config').write_text('foreign')
    with pytest.raises(UripackError): apply_plan(plan,RecordingGuard(hook=hook))
    assert not sample[1].exists()

def test_verifier_wrong_artifact(sample,plan):
    class Wrong(RecordingGuard):
        def call(self,action,plan,payload=None):
            r=super().call(action,plan,payload)
            if action=='tool': r['result']['artifact_sha256']='0'*64
            return r
    with pytest.raises(UripackError): apply_plan(plan,Wrong())
    assert not sample[1].exists()

def test_existing_writer_lock_not_deleted(sample,plan,guard):
    lock=sample[1].parent/('.'+sample[1].name+'.uripack-writer.lock')
    lock.write_text('foreign')
    with pytest.raises(UripackError): apply_plan(plan,guard)
    assert lock.read_text()=='foreign'

def test_existing_target_not_overwritten(sample,plan,guard):
    sample[1].mkdir();(sample[1]/'foreign').write_text('keep')
    with pytest.raises(UripackError): apply_plan(plan,guard)
    assert (sample[1]/'foreign').read_text()=='keep'

def test_atomic_rename_will_not_replace_empty_directory(tmp_path):
    a=tmp_path/'a';b=tmp_path/'b';a.mkdir();b.mkdir()
    (a/'x').write_text('x')
    with pytest.raises(UripackError): _publish_no_replace(a,b)
    assert a.exists() and b.exists() and not list(b.iterdir())

@pytest.mark.parametrize('tamper',['change','add','delete','symlink','mode'])
def test_independent_artifact_verifier(sample,plan,guard,tamper):
    apply_plan(plan,guard)
    f=sample[1]/'packs/count/tree/unit/main.py'
    if tamper=='change': f.write_text('tampered')
    if tamper=='add': (sample[1]/'unknown').write_text('unknown')
    if tamper=='delete': f.unlink()
    if tamper=='symlink': f.unlink();f.symlink_to(sample[0]/'unit/main.py')
    if tamper=='mode': f.chmod(0o755)
    with pytest.raises(UripackError): verify_artifact(plan)

def test_journal_tamper_is_detected(plan,guard):
    result=apply_plan(plan,guard)
    events=copy.deepcopy(result['events']);events[0]['outcome']='FORGED'
    assert not verify_chain(events)
