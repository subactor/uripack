"""Generate uripack-owned closed contracts; no upstream schema impersonation."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]/'src/uripack_refactor/resources'
S={'type':'string'}
SHA={'type':'string','pattern':'^[a-f0-9]{64}$'}
ID={'type':'string','pattern':'^[a-z][a-z0-9.-]{0,95}$'}
PATH={'type':'string','minLength':1,'maxLength':1024}
def obj(props, required=None):
 return {'type':'object','additionalProperties':False,'properties':props,'required':list(props) if required is None else required}
def arr(x, minimum=0, maximum=10000):
 return {'type':'array','items':x,'minItems':minimum,'maxItems':maximum,'uniqueItems':True}
limits=obj({'max_files':{'type':'integer','minimum':1,'maximum':10000},'max_bytes':{'type':'integer','minimum':1,'maximum':134217728}})
unit=obj({'id':ID,'include':arr(PATH,1,256),'public_uris':arr({'type':'string','minLength':3,'maxLength':2048},0,1000),'depends_on':arr(ID,0,100)}, ['id','include'])
request=obj({'schema':{'const':'uripack.refactor-request/v1'},'operation':{'const':'plan'},'namespace':ID,'units':arr(unit,1,100),'checks':arr(ID,0,100),'limits':limits}, ['schema','operation','namespace','units'])
copy=obj({'kind':{'const':'copy'},'source':PATH,'target':PATH,'sha256':SHA,'size':{'type':'integer','minimum':0},'mode':{'enum':[420,493]},'unit':ID})
write=obj({'kind':{'const':'write'},'target':PATH,'content':S,'sha256':SHA,'mode':{'const':420}})
plan=obj({'schema':{'const':'uripack.refactor-plan/v1'},'source_root':PATH,'target_root':PATH,'request':request,'request_sha256':SHA,'source_sha256':SHA,'operations':arr({'oneOf':[copy,write]},1,12000),'checks':arr(ID,0,100),'warnings':arr(S,0,10000),'exclusions':arr(S,0,10000),'semantics':{'const':'copy-preserving-extraction; no cutover; behavioral verification separate'},'plan_sha256':SHA})
config=obj({'schema':{'const':'uripack.guard-config/v1'},'argv':arr({'type':'string','minLength':1},1,32),'pinned_files':{'type':'object','minProperties':1,'additionalProperties':SHA},'timeout_seconds':{'type':'integer','minimum':1,'maximum':300},'required_checks':arr(ID,0,100)},['schema','argv','pinned_files','required_checks'])
response=obj({'schema':{'const':'uripack.guard-response/v1'},'request_id':S,'allowed':{'type':'boolean'},'subject_sha256':SHA,'decision_ref':{'type':'string','minLength':1},'lease_ref':{'type':'string','minLength':1},'fencing_token':{'type':'integer','minimum':1},'expires_at':{'type':'integer','minimum':1},'result':{'type':'object'}},['schema','request_id','allowed','subject_sha256','decision_ref','lease_ref','fencing_token','expires_at'])
check=obj({'schema':{'const':'uripack.check-result/v1'},'status':{'enum':['passed','failed','blocked']},'subject_sha256':SHA,'artifact_sha256':SHA,'evidence_refs':arr(S,1,100)})
for name, schema in [('request',request),('plan',plan),('guard-config',config),('guard-response',response),('check-result',check)]:
 schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':f'urn:uripack:schema:{name}:v1',**schema}
 (ROOT/f'{name}.schema.json').write_text(json.dumps(schema,indent=2)+'\n')

# V1 stays byte-for-byte stable. V2 opts into standalone service packaging.
from copy import deepcopy
service_path = {'type':'string', 'minLength':1, 'maxLength':1024,
                'pattern':r'^[A-Za-z0-9_./-]+$(?![\s\S])'}
service = obj({
 'schema': {'const':'uripack.service-profile/v1'},
 'language': {'enum':['python','node']},
 'base_image': {'type':'string', 'maxLength':512,
                'pattern':r'^[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}$(?![\s\S])'},
 'workdir': service_path,
 'command': {'type':'array','minItems':1,'maxItems':64,
             'items':{'type':'string','minLength':1,'maxLength':4096,'pattern':r'^[^\x00-\x1f\x7f]+$(?![\s\S])'}},
 'dependency_file': service_path,
 'ports': arr({'type':'integer','minimum':1,'maximum':65535},0,32),
}, ['schema','language','base_image','workdir','command','dependency_file'])
request_v2 = deepcopy(request)
request_v2['properties']['schema'] = {'const':'uripack.refactor-request/v2'}
request_v2['properties']['units']['items']['properties']['service'] = service
plan_v2 = deepcopy(plan)
plan_v2['properties']['schema'] = {'const':'uripack.refactor-plan/v2'}
plan_v2['properties']['request'] = request_v2
for name, version, schema in [('service',1,service),('request-v2',2,request_v2),('plan-v2',2,plan_v2)]:
 schema={'$schema':'https://json-schema.org/draft/2020-12/schema',
         '$id':f'urn:uripack:schema:{name.removesuffix("-v2")}:v{version}',**schema}
 (ROOT/f'{name}.schema.json').write_text(json.dumps(schema,indent=2)+'\n')
