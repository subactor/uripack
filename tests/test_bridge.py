import copy
import json
import os
from pathlib import Path
import sys
import time
import pytest
from uripack_refactor.common import UripackError, sha256
from uripack_refactor.guard import GuardBridge, bounded_run, invoke_tool
from uripack_refactor.executor import apply_plan

SCRIPT = '''import json,sys,time
r=json.load(sys.stdin)
a={"schema":"uripack.guard-response/v1","request_id":r["request_id"],"allowed":True,
"subject_sha256":r["subject_sha256"],"decision_ref":"test:protected-local-mock","lease_ref":"test:lease",
"fencing_token":1,"expires_at":int(time.time())+60,
"result":{"schema":"uripack.check-result/v1","status":"passed","subject_sha256":r["subject_sha256"],
"artifact_sha256":r["payload"].get("artifact_sha256","1"*64),"evidence_refs":["test:mock-protocol-only"]}}
PATCH
print(json.dumps(a))
'''

def make_bridge(tmp_path,sample,patch=''):
    controller=tmp_path/'protected';controller.mkdir(exist_ok=True)
    script=controller/'bridge.py';script.write_text(SCRIPT.replace('PATCH',patch))
    exe=str(Path(sys.executable).resolve())
    config={"schema":"uripack.guard-config/v1","argv":[exe,str(script)],
            "pinned_files":{exe:sha256(Path(exe).read_bytes()),str(script):sha256(script.read_bytes())},
            "required_checks":["tests.independent"],"timeout_seconds":5}
    path=controller/'config.json';path.write_text(json.dumps(config))
    return GuardBridge(path,sample[0],sample[1]),script,path

def test_actual_stdio_transport_with_explicitly_mocked_authority(tmp_path,sample,plan):
    bridge,_,_=make_bridge(tmp_path,sample)
    result=apply_plan(plan,bridge)
    assert result['status']=='EXTRACTED'
    assert result['guard'].startswith('protected-stdio:')

@pytest.mark.parametrize('patch',[
    'a["allowed"]=False',
    'a["expires_at"]=1',
    'a["subject_sha256"]="0"*64',
    'a["request_id"]="wrong"',
    'a["fencing_token"]=0',
    'a["grant_all"]=True',
    'a["lease_ref"]=""',
])
def test_bridge_invalid_response_fails_closed(tmp_path,sample,plan,patch):
    bridge,_,_=make_bridge(tmp_path,sample,patch)
    with pytest.raises(UripackError): bridge.call('admit',plan)
    assert not sample[1].exists()

def test_fencing_change_prevents_publish(tmp_path,sample,plan):
    bridge,_,_=make_bridge(tmp_path,sample,'if r["action"]=="publish": a["fencing_token"]=2')
    with pytest.raises(UripackError,match='fencing'): apply_plan(plan,bridge)
    assert not sample[1].exists()

def test_bridge_code_change_rejected(tmp_path,sample,plan):
    bridge,script,_=make_bridge(tmp_path,sample)
    script.write_text('print("changed")')
    with pytest.raises(UripackError,match='digest'): bridge.call('admit',plan)

def test_bridge_config_change_rejected(tmp_path,sample,plan):
    bridge,_,path=make_bridge(tmp_path,sample)
    path.write_text('{}')
    with pytest.raises(UripackError,match='configuration changed'): bridge.call('admit',plan)

def test_source_controlled_bridge_configuration_rejected(sample,tmp_path):
    path=sample[0]/'config.json';path.write_text('{}')
    with pytest.raises(UripackError,match='outside'): GuardBridge(path,sample[0],sample[1])

def test_no_inherited_secret_environment(monkeypatch):
    monkeypatch.setenv('SECRET_THAT_MUST_NOT_LEAK','never-pass-this')
    raw=bounded_run([sys.executable,'-c','import os;print(os.environ.get("SECRET_THAT_MUST_NOT_LEAK","absent"))'],b'')
    assert raw.strip()==b'absent'

def test_bounded_output():
    with pytest.raises(UripackError,match='output limit'):
        bounded_run([sys.executable,'-c','print("x"*200000)'],b'',max_bytes=1000)

def test_timeout_no_automatic_retry():
    with pytest.raises(UripackError,match='timed out'):
        bounded_run([sys.executable,'-c','import time;time.sleep(10)'],b'',timeout=1)

def test_arbitrary_registered_tool_transport_does_not_claim_success(tmp_path,sample,plan):
    bridge,_,_=make_bridge(tmp_path,sample)
    value=invoke_tool(bridge,plan,'subactor.diagit','inspect',{'schema':'test.native-request/v1'})
    assert value['status']=='protected-response-received' and not value['domain_success_inferred']
