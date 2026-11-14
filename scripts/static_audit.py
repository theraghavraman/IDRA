#!/usr/bin/env python3
"""Limited transparent AST audit, not a substitute for Ruff/mypy/security review."""
import ast
import importlib.util
import json
import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
issues=[];files=0
for path in sorted((root/'src').rglob('*.py')):
    files+=1
    try:
        source=path.read_text(encoding='utf-8');tree=ast.parse(source,filename=str(path))
        compile(tree,str(path),'exec')
    except (SyntaxError,UnicodeError) as exc:
        issues.append({'file':str(path.relative_to(root)),'code':'SYNTAX','line':getattr(exc,'lineno',None)})
        continue
    for node in ast.walk(tree):
        if isinstance(node,ast.Call):
            name=ast.unparse(node.func)
            if name in {'eval','exec','os.system','os.popen'}:
                issues.append({'file':str(path.relative_to(root)),'code':'UNSAFE_EXECUTION','line':node.lineno})
            if any(k.arg=='shell' and isinstance(k.value,ast.Constant) and k.value.value is True for k in node.keywords):
                issues.append({'file':str(path.relative_to(root)),'code':'SHELL_TRUE','line':node.lineno})
report={'status':'passed' if not issues else 'failed','python_modules_parsed':files,'issues':issues,
 'checks':['AST parse','Python compile','direct eval/exec/os.system/os.popen calls','literal shell=True calls'],
 'ruff':'NOT_RUN' if importlib.util.find_spec('ruff') is None else 'AVAILABLE_SEPARATE_RUN_REQUIRED',
 'mypy':'NOT_RUN' if importlib.util.find_spec('mypy') is None else 'AVAILABLE_SEPARATE_RUN_REQUIRED',
 'limitations':['This audit does not check import resolution, complete typing, style, dependency CVEs, or all data flows.']}
(root/'reports').mkdir(exist_ok=True)
(root/'reports/static-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
sys.exit(bool(issues))
