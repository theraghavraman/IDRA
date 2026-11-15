#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from idra.diagnostics.benchmark import measure_ingestion
from idra.storage.files import atomic_json

p=argparse.ArgumentParser()
p.add_argument('--events',type=int,default=20000)
p.add_argument('--minimum-seconds',type=float,default=5)
p.add_argument('--output',type=Path,default=Path('reports/benchmark.json'))
a=p.parse_args()
r=measure_ingestion(a.events,minimum_seconds=a.minimum_seconds)
atomic_json(a.output,r)
print(json.dumps(r,indent=2))
