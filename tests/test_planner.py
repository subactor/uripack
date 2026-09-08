import copy
from pathlib import Path
import pytest
from uripack_refactor.common import UripackError, digest
from uripack_refactor.planner import build_plan, validate_plan

def test_deterministic_plan(sample,plan):
    assert build_plan(sample[2],sample[0],sample[1])==plan
    assert not sample[1].exists()
    assert plan['request_sha256']==digest(sample[2])
    assert sum(o['kind']=='copy' for o in plan['operations'])==5

def test_plan_includes_six_layers(plan):
    import json
    pack=next(o for o in plan['operations'] if o['target']=='packs/count/uripack.json')
    value=json.loads(pack['content'])
    assert set(value['layers'])=={'identity','contracts','implementations','dependencies','provenance','verification'}
    assert value['layers']['implementations']['languages']==['python','typescript']
    assert len(value['layers']['implementations']['native_packages'])==2
    assert not value['layers']['identity']['runtime_binding_verified']

@pytest.mark.parametrize('change',['edit','add','delete','chmod'])
def test_source_drift(sample,plan,change):
    f=sample[0]/'unit/main.py'
    if change=='edit': f.write_text('changed')
    if change=='add': (sample[0]/'unit/new.py').write_text('new')
    if change=='delete': f.unlink()
    if change=='chmod': f.chmod(0o755)
    with pytest.raises(UripackError): validate_plan(plan)

def test_foreign_unselected_work_is_preserved_not_falsely_hashed(sample,plan):
    (sample[0]/'unrelated.txt').write_text('new foreign work')
    validate_plan(plan)

def test_missing_public_uri(sample):
    req=copy.deepcopy(sample[2]);req['units'][0]['public_uris']=['missing://uri/query/x']
    with pytest.raises(UripackError,match='not found'): build_plan(req,sample[0],sample[1])

def test_duplicate_uri_owner(sample):
    req=copy.deepcopy(sample[2]);req['units'][0]['include']=['unit/main.py']
    req['units'].append({'id':'other','include':['unit/main.ts'],'public_uris':['demo://repository/query/count']})
    with pytest.raises(UripackError,match='multiple extraction owners'): build_plan(req,sample[0],sample[1])

def test_overlapping_units(sample):
    req=copy.deepcopy(sample[2]);req['units'].append({'id':'other','include':['unit/main.py']})
    with pytest.raises(UripackError,match='multiple units'): build_plan(req,sample[0],sample[1])

@pytest.mark.parametrize('deps',[['missing'],['count']])
def test_graph_rejected(sample,deps):
    req=copy.deepcopy(sample[2]);req['units'][0]['depends_on']=deps
    with pytest.raises(UripackError): build_plan(req,sample[0],sample[1])

def test_duplicate_unit_id(sample):
    req=copy.deepcopy(sample[2]);req['units'].append({'id':'count','include':['unit/main.py']})
    with pytest.raises(UripackError): build_plan(req,sample[0],sample[1])

@pytest.mark.parametrize('limits',[{'max_files':1,'max_bytes':10000},{'max_files':100,'max_bytes':1}])
def test_budget(sample,limits):
    req=copy.deepcopy(sample[2]);req['limits']=limits
    with pytest.raises(UripackError,match='budget'): build_plan(req,sample[0],sample[1])

def test_symlink_directory_not_followed(sample,tmp_path):
    (sample[0]/'unit/link').symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(UripackError): build_plan(sample[2],sample[0],sample[1])

def test_case_collision(sample):
    (sample[0]/'unit/MAIN.py').write_text('x=1')
    with pytest.raises(UripackError,match='collision'): build_plan(sample[2],sample[0],sample[1])

def test_target_inside_source(sample):
    with pytest.raises(UripackError,match='disjoint'): build_plan(sample[2],sample[0],sample[0]/'target')

def test_plan_tamper(plan):
    p=copy.deepcopy(plan);p['operations'][0]['sha256']='0'*64
    with pytest.raises(UripackError,match='digest'): validate_plan(p)

def test_rehashed_forged_operation_is_rejected(plan):
    p=copy.deepcopy(plan);o=next(o for o in p['operations'] if o['kind']=='write')
    o['target']='arbitrary-authority.json'
    p['plan_sha256']=digest({k:v for k,v in p.items() if k!='plan_sha256'})
    with pytest.raises(UripackError,match='replan'): validate_plan(p)

def test_secret_source_blocks_plan(sample):
    (sample[0]/'unit/.env').write_text('SECRET=test')
    with pytest.raises(UripackError): build_plan(sample[2],sample[0],sample[1])

def test_local_ts_import_warning(sample):
    (sample[0]/'unit/main.ts').write_text('import {x} from "./absent.js";\n')
    req=copy.deepcopy(sample[2]);req['units'][0]['public_uris']=[]
    p=build_plan(req,sample[0],sample[1])
    assert any('Unresolved local JS/TS import' in w for w in p['warnings'])
