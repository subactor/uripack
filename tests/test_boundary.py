import copy
import json
from pathlib import Path
import pytest
from uripack_refactor.common import (UripackError, canonical, parse_document, parse_json,
                                     relative_path, read_regular, secret_check)
from uripack_refactor.contracts import validate
from uripack_refactor.discovery import analyze, discover, index_map

@pytest.mark.parametrize("value", [0,1,-1,9007199254740991,-9007199254740991,True,False,None,"ą😀",{"a":1,"😀":2,"\ue000":3},[1,"x"]])
def test_canonical_valid(value):
    assert parse_json(canonical(value).decode()) == value

@pytest.mark.parametrize("value", [1.5,float('nan'),float('inf'),9007199254740992,-9007199254740992,{1:"x"},("x",),"\ud800"])
def test_canonical_rejects(value):
    with pytest.raises(UripackError): canonical(value)

@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"x":{"k":1,"k":2}}','{"x":NaN}','[1.5]','{"x":'])
def test_json_strict(text):
    with pytest.raises(UripackError): parse_json(text)

@pytest.mark.parametrize("text", ['a: 1\na: 2\n','a: &x [1]\nb: *x\n','a: !!python/object/apply:os.system ["true"]','a: 1.5\n','a: 2026-01-01\n'])
def test_yaml_strict(text):
    with pytest.raises(UripackError): parse_document(text.encode(),'.yaml')

def test_yaml_valid():
    assert parse_document(b'a: 1\nb: ["x", true]\n','.yaml') == {'a':1,'b':['x',True]}

@pytest.mark.parametrize("path", ["../x","/etc/passwd","a/../b","a//b","./x",".","a\\b","a\x00b","a:b",".git/config","foo/worktrees/a",".subactor/leases/x"])
def test_paths_rejected(path):
    with pytest.raises(UripackError): relative_path(path)

@pytest.mark.parametrize("path", ["unit/main.py","a-b/package.json","ą/文.ts",".gitignore"])
def test_paths_accepted(path):
    assert str(relative_path(path)) == path

@pytest.mark.parametrize("field,value", [("operation","apply"),("authority",True),("shell","rm -rf /"),("namespace","Upper"),("units",[]),("limits",{"max_files":0,"max_bytes":50})])
def test_request_rejects_untrusted_extensions(sample,field,value):
    req=copy.deepcopy(sample[2]);req[field]=value
    with pytest.raises(UripackError): validate('request',req)

def test_request_valid(sample): validate('request',sample[2])

def test_no_imports_or_npm_scripts(sample):
    source=sample[0]
    (source/'unit/evil.py').write_text('raise RuntimeError("MUST NOT IMPORT")\n')
    report=discover(source)
    assert not report['source_code_imported']
    assert len(report['packages'])==2
    assert next(p for p in report['packages'] if p['ecosystem']=='node')['scripts']['postinstall']=='echo never-run'

def test_ast_and_uri_classification():
    item=analyze('x.py',b'import os\nfrom .util import count\nURI="demo://repo/query/count"\ndef run(x):\n return x\n')
    assert item['imports']==['os','.util']
    assert item['exports']==['run']
    assert item['uris'][0]['evidence']=='literal-candidate'
    assert not item['uris'][0]['binding_verified']

def test_declared_uri_is_not_runtime_verification():
    item=analyze('process.json',b'{"process_uri":"demo://repo/query/count"}')
    assert item['uris'][0]['evidence']=='declared-field'
    assert not item['uris'][0]['binding_verified']

def test_credential_uri_not_displayed():
    item=analyze('x.json',b'{"uri":"https://user:password@example.com/path?token=secret"}')
    assert item['uris']==[]

@pytest.mark.parametrize("name,content", [('.env',b'KEY=anything'),('id_rsa',b'anything'),('x.key',b'anything'),('x.py',b'-----BEGIN PRIVATE KEY-----')])
def test_secret_filter(name,content):
    with pytest.raises(UripackError): secret_check(name,content)

def test_safe_reader_rejects_symlink(sample,tmp_path):
    (sample[0]/'unit/link').symlink_to(tmp_path/'outside')
    with pytest.raises(UripackError): read_regular(sample[0],'unit/link')

def test_map_parser_does_not_parse_details(tmp_path):
    p=tmp_path/'map';p.write_text('# test\nM[2]:\n  a/package.json,3\n  b/pyproject.toml,4\nD:\n  fake/module.py:\n')
    result=index_map(p)
    assert result['module_count']==2 and result['root_count']==2 and result['tools_executed']==0
