"""Explicit Docker integration suite; requires a running local Docker engine."""
import json

import pytest

from tests.conftest import guard as guard
from tests.test_services import service_sample as service_sample
from uripack_refactor.executor import apply_plan, verify_artifact
from uripack_refactor.planner import build_plan

@pytest.mark.parametrize('unit_id,uri', [('python-count', 'demo://services/python/count'),
                                       ('node-count', 'demo://services/node/count')])
def test_real_service_container_without_source(service_sample, guard, unit_id, uri):
    import subprocess
    import uuid
    source, target, request = service_sample
    plan = build_plan(request, source, target)
    apply_plan(plan, guard)  # Test protocol fake; not a production admission.
    verify_artifact(plan)
    source.rename(source.with_name('source-unavailable'))
    image = 'uripack-ticket001-test:' + uuid.uuid4().hex
    name = 'uripack-ticket001-test-' + uuid.uuid4().hex
    def run(args, **kwargs):
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=120, **kwargs)
    try:
        run(['docker', 'build', '--network=none', '--pull=false', '-t', image,
             str(target / 'packs' / unit_id)])
        command = ['docker', 'run', '--rm', '--name', name, '--network=none', '--read-only',
                   '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit=64',
                   '--memory=128m', '--cpus=1']
        uid = run(command + ['--entrypoint', 'id', image, '-u']).stdout.strip()
        assert uid == '65532'
        # Independent clients send the native JSON request; no source mounts or uripack runtime.
        for items in [[], ['ą', '😀', 'third']]:
            result = run(command + ['-i', image], input=json.dumps({'items': items}))
            assert json.loads(result.stdout) == {'uri': uri, 'count': len(items)}
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)
        subprocess.run(['docker', 'image', 'rm', image], capture_output=True, timeout=30)
