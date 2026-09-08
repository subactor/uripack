import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from uripack_refactor.catalog import catalog
from uripack_refactor.cli import main
from uripack_refactor.common import UripackError, canonical
from uripack_refactor.contracts import validate
from uripack_refactor.demo import demo
from uripack_refactor.exchange import llm_exchange, accept_proposal
from uripack_refactor.governance import adoption_audit

ROOT=Path(__file__).resolve().parents[1]

def test_complete_supplied_map_coverage():
    result=catalog()
    assert result['root_count']==102
    assert all(x['invocation_status']=='not-invoked' for x in result['records'])
    assert not result['automatic_installation']

def test_governance_inventory_never_claims_validation(sample):
    value=adoption_audit(sample[0])
    assert not value['official_validator_executed']
    assert value['conformance']=='not-established'

def test_model_boundary_request_only(sample):
    envelope=llm_exchange({'files':[]},'przenieś procesy')
    assert not envelope['execution_authority']
    assert envelope['output_contract']['properties']['operation']=={'const':'plan'}
    bad=copy.deepcopy(sample[2]);bad['operation']='apply'
    with pytest.raises(UripackError): accept_proposal(bad)

def test_cli_plan_writes_only_explicit_external_artifact(sample,tmp_path):
    request=tmp_path/'request.json';request.write_text(json.dumps(sample[2]))
    out=tmp_path/'evidence/plan.json'
    assert main(['plan','--request',str(request),'--source',str(sample[0]),'--target',str(sample[1]),'--out',str(out)])==0
    assert out.exists() and not sample[1].exists()
    assert main(['plan','--request',str(request),'--source',str(sample[0]),'--target',str(sample[1]),'--out',str(out)])==2

def test_cli_apply_no_demo_bypass_flag():
    with pytest.raises(SystemExit): main(['apply','--plan','x','--unsafe'])

def test_cli_plan_cannot_write_into_source(sample,tmp_path):
    request=tmp_path/'request.json';request.write_text(json.dumps(sample[2]))
    assert main(['plan','--request',str(request),'--source',str(sample[0]),'--target',str(sample[1]),'--out',str(sample[0]/'oops')])==2
    assert not (sample[0]/'oops').exists()

@pytest.mark.skipif(not shutil.which('node') or not shutil.which('tsc'),reason='Node and TypeScript compiler required for real cross-language fixture test')
def test_e2e_old_new_python_typescript():
    report=demo()
    assert report['status']=='passed' and report['source_unchanged']
    assert report['checks']['python_cases']==3 and report['checks']['typescript_cases']==3
    assert report['checks']['typescript_compiled']
    assert report['checks']['real_subactor_tools_executed']==0 and report['checks']['live_llm_calls']==0

@pytest.fixture(scope='module')
def sdk(tmp_path_factory):
    if not shutil.which('node') or not shutil.which('tsc'):
        pytest.skip('Node and TypeScript compiler unavailable')
    out=tmp_path_factory.mktemp('sdk')
    node=shutil.which('node');tsc=str(Path(shutil.which('tsc')).resolve())
    subprocess.run([node,tsc,str(ROOT/'sdk/typescript/index.ts'),'--outDir',str(out),'--strict','--module','ES2022','--target','ES2022','--declaration'],check=True,capture_output=True,timeout=30)
    (out/'package.json').write_text('{"type":"module"}')
    return node,(out/'index.js').as_uri()

@pytest.mark.parametrize('value',[{},[],None,True,-1,1.0,9007199254740991,'ą😀',{'\ue000':1,'😀':2,'a':'\n'},[1,False,{'nested':'yes'}]])
def test_cross_language_canonical_golden(sdk,value):
    script=f'import {{canonical}} from {json.dumps(sdk[1])}; process.stdout.write(canonical(JSON.parse(process.argv[1])));'
    run=subprocess.run([sdk[0],'--input-type=module','-e',script,'--',json.dumps(value,ensure_ascii=True)],capture_output=True,text=True,check=True,timeout=10)
    assert run.stdout.encode()==canonical(value)

@pytest.mark.parametrize('mutator',[
    lambda r:r,
    lambda r:{**r,'operation':'apply'},
    lambda r:{**r,'authority':True},
    lambda r:{**r,'units':[]},
    lambda r:{**r,'checks':['tests.x','tests.x']},
    lambda r:{**r,'namespace':'Invalid'},
    lambda r:{**r,'limits':{'max_files':1.5,'max_bytes':100}},
    lambda r:{**r,'limits':{'max_files':1,'max_bytes':100}},
    lambda r:{**r,'units':[{'id':'x','include':['a'],'public_uris':None}]},
    lambda r:{**r,'units':[{'id':'x','include':['a'],'shell':'no'}]},
])
def test_python_typescript_contract_conformance(sdk,sample,mutator):
    request=mutator(copy.deepcopy(sample[2]))
    try: validate('request',request);py_valid=True
    except UripackError: py_valid=False
    script=f'import {{assertRefactorRequest}} from {json.dumps(sdk[1])}; try {{assertRefactorRequest(JSON.parse(process.argv[1]));process.stdout.write("true");}} catch {{process.stdout.write("false");}}'
    run=subprocess.run([sdk[0],'--input-type=module','-e',script,'--',json.dumps(request)],capture_output=True,text=True,check=True,timeout=10)
    assert (run.stdout=='true')==py_valid

def test_cli_plan_cannot_precreate_target_for_evidence(sample,tmp_path):
    request=tmp_path/'request.json';request.write_text(json.dumps(sample[2]))
    assert main(['plan','--request',str(request),'--source',str(sample[0]),'--target',str(sample[1]),'--out',str(sample[1]/'plan.json')])==2
    assert not sample[1].exists()

def test_cli_verify_cannot_modify_the_verified_artifact(sample,plan,guard,tmp_path):
    from uripack_refactor.executor import apply_plan
    apply_plan(plan,guard)
    p=tmp_path/'plan.json';p.write_text(json.dumps(plan))
    assert main(['verify','--plan',str(p),'--out',str(sample[1]/'bad-report.json')])==2
    assert not (sample[1]/'bad-report.json').exists()
