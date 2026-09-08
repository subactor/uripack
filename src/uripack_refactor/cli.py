from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys
from . import __version__
from .common import UripackError, fail, json_bytes, load_document


def _output(value: dict, filename: str | None) -> None:
    data = json_bytes(value)
    if filename:
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Deliberately no --force: an evidence file is not silently overwritten.
        with p.open("xb") as out:
            out.write(data)
    else:
        sys.stdout.write(data.decode("utf-8"))



def _check_plan_output(args, plan: dict) -> None:
    if not getattr(args, "out", None):
        return
    output = Path(args.out).resolve()
    for key in ("source_root", "target_root"):
        root = Path(plan[key]).resolve()
        if output == root or root in output.parents:
            fail("UPK-PATH-001", "Store reports outside the source and materialized artifact")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="uripack",description="Guard-mediated, copy-preserving URI process extraction")
    p.add_argument("--version",action="version",version=__version__)
    sub = p.add_subparsers(dest="command",required=True)
    m = sub.add_parser("map-index",help="Index a supplied code2llm map; never execute its contents")
    m.add_argument("map"); m.add_argument("--out")
    t = sub.add_parser("tools",help="Account for all indexed Subactor roots and discover local metadata")
    t.add_argument("--root"); t.add_argument("--out")
    i = sub.add_parser("inventory",help="Statically inventory source files and package manifests")
    i.add_argument("--root",required=True); i.add_argument("--include",action="append"); i.add_argument("--out")
    v = sub.add_parser("validate-request",help="Validate a request-only JSON/YAML DSL document")
    v.add_argument("request"); v.add_argument("--out")
    plan = sub.add_parser("plan",help="Compile an exact extraction plan without repository writes")
    plan.add_argument("--request",required=True); plan.add_argument("--source",required=True)
    plan.add_argument("--target",required=True); plan.add_argument("--out")
    a = sub.add_parser("apply",help="Extract through an operator-installed, pinned Organism Guard bridge")
    a.add_argument("--plan",required=True); a.add_argument("--guard-config",required=True); a.add_argument("--out")
    verify = sub.add_parser("verify",help="Independently verify artifact bytes and executable bits")
    verify.add_argument("--plan",required=True); verify.add_argument("--target"); verify.add_argument("--out")
    g = sub.add_parser("adoption-audit",help="Inventory governance adoption markers, without claiming conformance")
    g.add_argument("--root",required=True); g.add_argument("--out")
    llm = sub.add_parser("llm-envelope",help="Prepare a request-only exchange for a Subactor LLM adapter")
    llm.add_argument("--inventory",required=True); llm.add_argument("--intent",required=True); llm.add_argument("--out")
    tool = sub.add_parser("invoke-tool",help="Invoke an explicitly registered Subactor tool using its native versioned DSL")
    tool.add_argument("--plan",required=True); tool.add_argument("--guard-config",required=True)
    tool.add_argument("--tool-id",required=True); tool.add_argument("--operation",required=True)
    tool.add_argument("--request",required=True); tool.add_argument("--out")
    d = sub.add_parser("demo",help="Run Python/TypeScript E2E on synthetic fixtures, not live Subactor")
    d.add_argument("--out-dir")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command in {"inventory","plan","adoption-audit","tools"} and getattr(args,"out",None):
            source_arg = getattr(args,"source",None) or getattr(args,"root",None)
            if source_arg:
                source = Path(source_arg).resolve()
                output = Path(args.out).resolve()
                if output == source or source in output.parents:
                    fail("UPK-PATH-001", "Write reports outside the source repository to preserve the source snapshot")
        if args.command == "plan" and args.out:
            target = Path(args.target).resolve()
            output = Path(args.out).resolve()
            if output == target or target in output.parents:
                fail("UPK-PATH-001", "Keep plan evidence outside the new target directory")
        if args.command == "map-index":
            from .discovery import index_map
            result = index_map(args.map)
        elif args.command == "tools":
            from .catalog import catalog
            result = catalog(args.root)
        elif args.command == "inventory":
            from .discovery import discover
            result = discover(args.root,args.include)
        elif args.command == "validate-request":
            from .contracts import validate
            request = load_document(args.request)
            validate("request",request)
            result = {"valid":True,"schema":request["schema"],"execution_authority":False}
        elif args.command == "plan":
            from .planner import build_plan
            result = build_plan(load_document(args.request),args.source,args.target)
        elif args.command == "apply":
            from .executor import apply_plan
            from .guard import GuardBridge
            from .planner import validate_plan
            plan = load_document(args.plan)
            validate_plan(plan)
            _check_plan_output(args, plan)
            guard = GuardBridge(args.guard_config,plan["source_root"],plan["target_root"])
            result = apply_plan(plan,guard)
        elif args.command == "verify":
            from .executor import verify_artifact
            plan = load_document(args.plan)
            from .planner import validate_plan
            validate_plan(plan, reobserve=False)
            _check_plan_output(args, plan)
            if args.target and args.out:
                root, output = Path(args.target).resolve(), Path(args.out).resolve()
                if output == root or root in output.parents:
                    fail("UPK-PATH-001", "Store verification reports outside the verified artifact")
            result = verify_artifact(plan,args.target)
        elif args.command == "adoption-audit":
            from .governance import adoption_audit
            result = adoption_audit(args.root)
        elif args.command == "llm-envelope":
            from .exchange import llm_exchange
            result = llm_exchange(load_document(args.inventory),args.intent)
        elif args.command == "invoke-tool":
            from .guard import GuardBridge, invoke_tool
            from .planner import validate_plan
            plan = load_document(args.plan)
            validate_plan(plan)
            _check_plan_output(args, plan)
            guard = GuardBridge(args.guard_config,plan["source_root"],plan["target_root"])
            result = invoke_tool(guard,plan,args.tool_id,args.operation,load_document(args.request))
        elif args.command == "demo":
            from .demo import demo
            result = demo(args.out_dir)
        else:
            raise AssertionError("unhandled command")
        _output(result,getattr(args,"out",None))
        return 0
    except UripackError as exc:
        sys.stderr.write(json_bytes({"ok":False,"code":exc.code,"message":str(exc)}).decode())
        return 2
    except (OSError,ValueError) as exc:
        # Avoid leaking raw paths, bridge output or secrets from underlying exceptions.
        sys.stderr.write(json_bytes({"ok":False,"code":"UPK-IO-001","message":f"Operation failed ({type(exc).__name__}); no automatic retry"}).decode())
        return 2
