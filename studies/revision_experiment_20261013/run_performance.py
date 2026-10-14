#!/usr/bin/env python3
import os,sys,socket
from pathlib import Path
os.environ['PYTHON_DOTENV_DISABLED']='1';sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'source_snapshot'));sys.path.insert(0,str(ROOT))
def denied(*args,**kwargs):raise RuntimeError('Network disabled')
socket.socket.connect=denied;socket.create_connection=denied
from benchmark.performance import run_performance
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--results',default='results/performance');a=p.parse_args()
    run_performance(ROOT/a.results)
