import os
import importlib
from utils import asttools as parser
from utils.codec import instructionset, instructioncategories
from utils.eval import computeunary, computebinary

opcodetemplates = {}

def buildliteral(n):
    return {
        "Type": "NumberLiteral",
        "Token": {"Type": "Number", "LeadingWhite": "", "Source": str(n)},
        "GetFirstToken": lambda: None,
        "GetLastToken": lambda: None
    }

aliasknown = None
aliasunknown = None

def traceflow(enum, tokens, clause=None, parent=None):
    clause = clause or tokens["Clauses"]
    cond = clause["Condition"]
    elseclauses = clause["ElseClauseList"]
    if cond["Type"] != "BinopExpr" or cond["Lhs"]["Type"] != "VariableExpr":
        return parent
    if cond["Lhs"]["Variable"]["Name"] != tokens["Enum"]:
        return parent
    if cond["Rhs"]["Type"] == "UnopExpr":
        val = computeunary(cond["Rhs"])
        if val is not None:
            cond["Rhs"] = buildliteral(val)
        else:
            return None
    elif cond["Rhs"]["Type"] != "NumberLiteral":
        raise RuntimeError("unhandled comparison")
    
    def extractbody(clause):
        if clause["Body"]["StatementList"][0]["Type"] == "IfStat":
            return traceflow(enum, tokens, clause["Body"]["StatementList"][0], clause["Body"]["StatementList"])
        return clause["Body"]["StatementList"]
    
    if computebinary(enum, cond["Token_Op"]["Source"], cond["Rhs"]["Token"]["Source"]):
        return extractbody(clause)
    
    for i in range(len(elseclauses)):
        clause = elseclauses[i]
        cond = clause["Condition"]
        if clause["ClauseType"] == "elseif":
            if cond["Rhs"]["Type"] == "UnopExpr":
                val = computeunary(cond["Rhs"])
                if val is not None:
                    cond["Rhs"] = buildliteral(val)
                else:
                    return None
            elif cond["Rhs"]["Type"] != "NumberLiteral":
                raise RuntimeError("unhandled comparison")
            if computebinary(enum, cond["Token_Op"]["Source"], cond["Rhs"]["Token"]["Source"]):
                return extractbody(clause)
        elif clause["ClauseType"] == "else":
            return extractbody(clause)
    return None

def resolveinstruction(instructions, operands, pc, tokens, nolocal=False):
    def validate(src, thorough):
        def match(a, b):
            if a["Type"] != b["Type"]:
                if b["Type"] == "NumberLiteral" and a["Type"] == "UnopExpr":
                    val = computeunary(a)
                    if val is not None:
                        a = buildliteral(val)
                    else:
                        return False
                else:
                    return False
            if a["Type"] == "AssignmentStat":
                return listmatch(a["Rhs"], b["Rhs"]) and listmatch(a["Lhs"], b["Lhs"])
            elif a["Type"] == "IndexExpr":
                names = True
                if thorough and "Variable" in a["Base"] and a["Base"]["Variable"] is not None and b["Base"]["Type"] == "VariableExpr":
                    names = a["Base"]["Variable"]["Name"] == b["Base"]["Token"]["Source"]
                return names and match(a["Base"], b["Base"]) and match(a["Index"], b["Index"])
            elif a["Type"] == "VariableExpr":
                return True
            elif a["Type"] == "NumberLiteral":
                return a["Source"] == b["Source"]
            elif a["Type"] == "LocalVarStat":
                return listmatch(a["ExprList"], b["ExprList"])
            elif a["Type"] == "CallExprStat":
                e1 = a["Expression"]
                e2 = b["Expression"]
                return match(e1["Base"], e2["Base"]) and listmatch(e1["FunctionArguments"]["ArgList"], e2["FunctionArguments"]["ArgList"])
            elif a["Type"] == "CallExpr":
                return match(a["Base"], b["Base"]) and listmatch(a["FunctionArguments"]["ArgList"], b["FunctionArguments"]["ArgList"])
            elif a["Type"] == "BinopExpr":
                t1 = a["Token_Op"]
                t2 = b["Token_Op"]
                return t1["Source"] == t2["Source"] and match(a["Rhs"], b["Rhs"]) and match(a["Lhs"], b["Lhs"])
            elif a["Type"] == "DoStat":
                return listmatch(a["Body"]["StatementList"], b["Body"]["StatementList"])
            elif a["Type"] == "ReturnStat":
                return listmatch(a["ExprList"], b["ExprList"])
            elif a["Type"] == "NilLiteral":
                return True
            elif a["Type"] == "TableLiteral":
                return True
            elif a["Type"] == "NumericForStat":
                return listmatch(a["RangeList"], b["RangeList"]) and listmatch(a["Body"]["StatementList"], b["Body"]["StatementList"])
            elif a["Type"] == "ParenExpr":
                return match(a["Expression"], b["Expression"])
            elif a["Type"] == "UnopExpr":
                return a["Token_Op"]["Source"] == b["Token_Op"]["Source"] and match(a["Rhs"], b["Rhs"])
            elif a["Type"] == "IfStat":
                if not match(a["Condition"], b["Condition"]):
                    return False
                if thorough and not listmatch(a["Body"]["StatementList"], b["Body"]["StatementList"]):
                    return False
                o1 = a["ElseClauseList"]
                o2 = b["ElseClauseList"]
                if len(o1) != len(o2):
                    return False
                for i in range(len(o1)):
                    if o1[i]["ClauseType"] != o2[i]["ClauseType"]:
                        return False
                    if not listmatch(o1[i]["Body"]["StatementList"], o2[i]["Body"]["StatementList"]):
                        return False
                return listmatch(a["Body"]["StatementList"], b["Body"]["StatementList"])
            return False
        
        def listmatch(a, b):
            if len(a) != len(b):
                return False
            for i in range(len(a)):
                if not match(a[i], b[i]):
                    return False
            return True
        
        if nolocal:
            src = src.replace("local", "")
            src = aliasknown(src)
            sample = parser.loadast(src)
            return listmatch(instructions, sample["StatementList"])
    
    def isjump(s):
        if s["Type"] != "AssignmentStat":
            return False
        r = s["Rhs"][0]
        l = s["Lhs"][0]
        return (r["Type"] == "BinopExpr" and
                r["Lhs"]["Type"] == "VariableExpr" and
                r["Lhs"]["Variable"]["Name"] == tokens["InstrPoint"] and
                r["Rhs"]["Type"] == "NumberLiteral" and
                r["Rhs"]["Token"]["Source"] == "1" and
                l["Type"] == "VariableExpr" and
                l["Variable"]["Name"] == tokens["InstrPoint"])
    
    for opname in opcodetemplates:
        variants = opcodetemplates[opname]
        for v in variants.values():
            if ("Match" in v and v["Match"]) or ("String" in v and validate(v["String"], v.get("Thorough", False))):
                operands[pc]["PC"] = pc
                inst = v["Create"]
                inst["OpCode"] = instructionset.index(opname)
                inst["OpName"] = instructionset[inst["OpCode"]]
                inst["Type"] = instructioncategories[inst["OpCode"]]
                return inst
    
    if any(isjump(s) for s in instructions):
        container = {
            "Instructions": [],
            "SuperInstruction": True,
            "MatchedInstructions": [],
            "SubCount": sum(1 for s in instructions if isjump(s))
        }
        sub = []
        container["Instructions"].append(sub)
        idx = 0
        while idx < len(instructions):
            stmt = instructions[idx]
            if isjump(stmt):
                idx += 1
                sub = []
                container["Instructions"].append(sub)
                continue
            elif stmt["Type"] == "LocalVarStat":
                idx += 1
                continue
            else:
                sub.append(stmt)
                idx += 1
        for i in range(len(container["Instructions"])):
            sublist = container["Instructions"][i]
            matched = resolveinstruction(sublist, operands, pc + i, tokens, True)
            if matched is not None:
                matched["Enum"] = i
                container["MatchedInstructions"].append(matched)
            else:
                container["MatchedInstructions"].append({
                    "PlaceHolder": True,
                    "Enum": i
                })
        return container
    return None

def flatten(vmstate):
    global opcodetemplates, aliasknown, aliasunknown
    version = vmstate["Version"]
    if version == "IronBrew V2.7.0":
        path = "./modules/luaengine/opcodes/2.7.0"
    elif version in ("IronBrew V2.7.1", "AztupBrew V2.7.2"):
        path = "./modules/luaengine/opcodes/2.7.1"
    else:
        raise RuntimeError("unsupported version")
    
    for fname in os.listdir(path):
        name = fname.split(".")[0]
        opcodetemplates[name] = importlib.import_module(f"modules.luaengine.opcodes.{path.split('/')[-1]}.{name}")
    
    def knownsub(s):
        res = s.replace("OP_A", "2").replace("OP_B", "3")
        res = res.replace("InstrPoint", vmstate["Tokens"]["InstrPoint"])
        res = res.replace("Upvalues", vmstate["Tokens"]["Upvalues"])
        res = res.replace("Unpack", vmstate["Tokens"]["Unpack"])
        res = res.replace("Const", vmstate["Tokens"]["Const"])
        res = res.replace("Wrap", vmstate["Tokens"]["Wrap"])
        res = res.replace("Inst", vmstate["Tokens"]["Inst"])
        res = res.replace("Top", vmstate["Tokens"]["Top"])
        res = res.replace("Stk", vmstate["Tokens"]["Stk"])
        res = res.replace("Env", vmstate["Tokens"]["Env"])
        if version == "IronBrew V2.7.0":
            res = res.replace("OP_C", "5")
        else:
            res = res.replace("OP_C", "4")
        return res
    
    def unknownsub(s):
        res = s.replace("[2", "[OP_A").replace("[3", "[OP_B").replace("[4", "[OP_C")
        res = res.replace(vmstate["Tokens"]["InstrPoint"], "InstrPoint")
        res = res.replace(vmstate["Tokens"]["Upvalues"], "Upvalues")
        res = res.replace(vmstate["Tokens"]["Unpack"], "Unpack")
        res = res.replace(vmstate["Tokens"]["Const"], "Const")
        res = res.replace(vmstate["Tokens"]["Wrap"], "Wrap")
        res = res.replace(vmstate["Tokens"]["Inst"], "Inst")
        res = res.replace(vmstate["Tokens"]["Top"], "Top")
        res = res.replace(vmstate["Tokens"]["Stk"], "Stk")
        res = res.replace(vmstate["Tokens"]["Env"], "Env")
        if version == "IronBrew V2.7.0":
            res = res.replace("[5", "[OP_C")
        return res
    
    aliasknown = knownsub
    aliasunknown = unknownsub
    
    def parseblock(chunk):
        insts = chunk["Instructions"]
        protos = chunk["Prototypes"]
        matchedinsts = []
        tokens = vmstate["Tokens"]
        print()
        for pc in range(len(insts)):
            enum = insts[pc]["Enum"]
            found = traceflow(enum, tokens)
            if found is not None:
                entry = resolveinstruction(found, insts, pc, tokens)
                if entry is not None:
                    if entry.get("SuperInstruction"):
                        subinsts = entry["MatchedInstructions"]
                        print(f"=> unrolled super-instruction #{enum}")
                        pc += entry["SubCount"]
                        for i in range(len(subinsts)):
                            if "PlaceHolder" not in subinsts[i] or not subinsts[i]["PlaceHolder"]:
                                matchedinsts.append(subinsts[i])
                                print(f"    -> sub #{subinsts[i]['Enum']+1}: {instructionset[subinsts[i]['OpCode']].upper()}")
                            else:
                                print(f"    -> no match for sub #{subinsts[i]['Enum']+1}")
                                raise RuntimeError("unmatched sub-instruction")
                    else:
                        matchedinsts.append(entry)
                        print(f"=> matched instruction #{enum}: {instructionset[entry['OpCode']].upper()}")
                else:
                    raw = parser.displayast({"Type": "StatList", "StatementList": found, "SemicolonList": []})
                    raw = aliasunknown(raw)
                    print(raw)
                    print(f"=> no match for instruction #{enum}")
                    raise RuntimeError("unmatched instruction")
            else:
                print(f"=> no instruction found at #{enum}")
        
        for i in range(len(protos)):
            protos[i] = parseblock(protos[i])
        chunk["Instructions"] = matchedinsts
        return chunk
    
    print()
    devirtualized = parseblock(vmstate["Chunk"])
    
    def markvararg(chunk):
        for i in range(len(chunk["Instructions"])):
            inst = chunk["Instructions"][i]
            if instructionset[inst["OpCode"]] == "VarArg":
                chunk["VarArg"] = True
                continue
        for i in range(len(chunk["Prototypes"])):
            markvararg(chunk["Prototypes"][i])
    
    markvararg(devirtualized)
    return devirtualized

def dummyhelper():
    pass
