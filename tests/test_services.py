import copy
import json
from pathlib import Path
import shutil

import pytest

from uripack_refactor.cli import main
from uripack_refactor.common import UripackError, load_document
from uripack_refactor.contracts import validate
from uripack_refactor.executor import apply_plan, verify_artifact
from uripack_refactor.planner import build_plan, validate_plan

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def service_sample(tmp_path):
    source = tmp_path / 'source'
    shutil.copytree(ROOT / 'examples/service-source', source)
    request = load_document(ROOT / 'examples/standalone-services.yaml')
    return source, tmp_path / 'result', request


def test_service_plan_is_deterministic_and_inert(service_sample, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('planner executed a command'))
    source, target, request = service_sample
    before = {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()}
    plan = build_plan(request, source, target)
    assert plan == build_plan(request, source, target)
    assert plan['schema'] == 'uripack.refactor-plan/v2'
    validate_plan(plan)
    assert not target.exists()
    assert before == {p.relative_to(source): p.read_bytes() for p in source.rglob('*') if p.is_file()}
    for unit in request['units']:
        prefix = f"packs/{unit['id']}/"
        outputs = {o['target']: o['content'] for o in plan['operations'] if o['kind'] == 'write'}
        manifest = json.loads(outputs[prefix + 'uripack.json'])
        runtime = manifest['layers']['runtime']
        assert runtime['identity_ref'] == '#/layers/identity/public_uris/0'
        assert not runtime['build']['executed'] and not runtime['production_binding_verified']
        assert runtime['dependencies'][0]['sha256']
        assert 'USER 65532:65532' in outputs[prefix + 'Dockerfile']
        assert 'CMD []' in outputs[prefix + 'Dockerfile']


def test_service_materialization_and_tamper_detection(service_sample, guard):
    source, target, request = service_sample
    plan = build_plan(request, source, target)
    apply_plan(plan, guard)
    assert [action for action, _ in guard.calls] == ['admit', 'tool', 'publish', 'complete']
    assert verify_artifact(plan)['status'] == 'passed'
    (target / 'packs/python-count/Dockerfile').write_text('FROM scratch\n')
    with pytest.raises(UripackError) as error:
        verify_artifact(plan)
    assert error.value.code == 'UPK-INTEGRITY-001'


def test_service_guard_denial_does_not_materialize(service_sample, guard):
    guard.deny = 'admit'
    source, target, request = service_sample
    with pytest.raises(UripackError):
        apply_plan(build_plan(request, source, target), guard)
    assert not target.exists()


@pytest.mark.parametrize('field,value', [
    ('base_image', 'python:latest'), ('base_image', 'python@sha256:' + 'a'*64 + '\nRUN bad'),
    ('workdir', '../python'), ('workdir', '/python'), ('workdir', 'python//'),
    ('workdir', 'missing'), ('workdir', 'python\nRUN bad'),
    ('dependency_file', '../requirements.lock'), ('dependency_file', 'missing.lock'),
    ('command', []), ('command', ['python\nRUN bad']), ('ports', [8080, 8080]),
    ('ports', [65536]), ('language', 'invented'), ('authority', True),
])
def test_reject_invalid_service(service_sample, field, value):
    source, target, request = service_sample
    request['units'][0]['service'][field] = value
    with pytest.raises(UripackError):
        build_plan(request, source, target)
    assert not target.exists()


@pytest.mark.parametrize('uris', [[], ['demo://services/python/count', 'demo://services/node/count']])
def test_service_requires_one_identity(service_sample, uris):
    source, target, request = service_sample
    request['units'][0]['public_uris'] = uris
    with pytest.raises(UripackError):
        build_plan(request, source, target)


def test_reject_unresolved_tree_dependency(service_sample):
    source, target, request = service_sample
    request['units'][0]['depends_on'] = ['node-count']
    with pytest.raises(UripackError) as error:
        build_plan(request, source, target)
    assert error.value.code == 'UPK-DEPENDENCY-001'


def test_node_requires_selected_native_manifests(service_sample):
    source, target, request = service_sample
    request['units'][1]['include'] = ['node/main.mjs', 'node/package-lock.json']
    with pytest.raises(UripackError) as error:
        build_plan(request, source, target)
    assert error.value.code == 'UPK-DEPENDENCY-001'


def test_dependency_drift_requires_replanning(service_sample):
    source, target, request = service_sample
    plan = build_plan(request, source, target)
    with (source / 'python/requirements.lock').open('a') as f:
        f.write('# drift\n')
    with pytest.raises(UripackError) as error:
        validate_plan(plan)
    assert error.value.code == 'UPK-DRIFT-001'


def test_v1_rejects_service_and_v2_cli_reports_actual_version(service_sample, tmp_path, capsys):
    _, _, request = service_sample
    old = copy.deepcopy(request)
    old['schema'] = 'uripack.refactor-request/v1'
    with pytest.raises(UripackError):
        validate('request', old)
    path = tmp_path / 'request.json'
    path.write_text(json.dumps(request))
    assert main(['validate-request', str(path)]) == 0
    assert json.loads(capsys.readouterr().out)['schema'] == 'uripack.refactor-request/v2'
