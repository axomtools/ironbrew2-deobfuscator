import re
import importlib
from .transform import extractcontext, parsebytecode, emitcode
from .flatten import flatten
from utils import asttools as parser

def detect(source):
    p1 = re.compile(r"return table\.concat[_\-a-zA-Z0-9]+")
    p2 = re.compile(r"return [_\-a-zA-Z0-9]+true, ?\{\}, ?[_\-a-zA-Z0-9]+\(\);?")
    p3 = re.compile(r"bit and bit\.bxor or function[_\-a-zA-Z0-9]+, ?[_\-a-zA-Z0-9]+")
    p4 = re.compile(r"local [_\-a-zA-Z0-9]+ = .*table\.concat")
    return bool(p1.search(source) or p2.search(source) or p3.search(source) or p4.search(source))

def execute(astroot):
    import sys
    sys.stdout.write("> extracting vm state...")
    vmstate = extractcontext(astroot["StatementList"], True)
    sys.stdout.write("> decoding bytecode...")
    vmstate = parsebytecode(vmstate, True)
    parser.resolvearithmetic(astroot)
    sys.stdout.write("> flattening vm...")
    vmstate = flatten(vmstate)
    return emitcode(vmstate)

enginename = "luadecompiler"
