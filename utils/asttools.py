import lua_parser
from lua_parser import ast as lua_ast
import re

class token:
    def __init__(self, type_, leading_white, source):
        self.Type = type_
        self.LeadingWhite = leading_white
        self.Source = source

class astnode:
    def __init__(self, type_):
        self.Type = type_
        self.Token = None
        self.GetFirstToken = lambda: None
        self.GetLastToken = lambda: None

def _convert_node(node):
    if node is None:
        return None
    typ = type(node).__name__
    if typ == "Chunk":
        return {"Type": "Chunk", "StatementList": [_convert_node(stmt) for stmt in node.body]}
    elif typ == "Function":
        return {
            "Type": "Function",
            "Name": _convert_node(node.name),
            "Parameters": [_convert_node(p) for p in node.params],
            "Body": _convert_node(node.body)
        }
    elif typ == "Assign":
        return {
            "Type": "AssignmentStat",
            "Lhs": [_convert_node(v) for v in node.targets],
            "Rhs": [_convert_node(v) for v in node.values]
        }
    elif typ == "LocalAssign":
        return {
            "Type": "LocalVarStat",
            "ExprList": [_convert_node(v) for v in node.values] if node.values else []
        }
    elif typ == "Name":
        return {"Type": "VariableExpr", "Variable": {"Name": node.id}}
    elif typ == "Number":
        return {"Type": "NumberLiteral", "Token": {"Type": "Number", "LeadingWhite": "", "Source": str(node.n)}}
    elif typ == "String":
        return {"Type": "StringLiteral", "Token": {"Type": "String", "LeadingWhite": "", "Source": node.s}}
    elif typ == "Nil":
        return {"Type": "NilLiteral"}
    elif typ == "True":
        return {"Type": "BooleanLiteral", "Token": {"Type": "Boolean", "LeadingWhite": "", "Source": "true"}}
    elif typ == "False":
        return {"Type": "BooleanLiteral", "Token": {"Type": "Boolean", "LeadingWhite": "", "Source": "false"}}
    elif typ == "BinOp":
        return {
            "Type": "BinopExpr",
            "Lhs": _convert_node(node.left),
            "Rhs": _convert_node(node.right),
            "Token_Op": {"Source": node.op}
        }
    elif typ == "UnaryOp":
        return {
            "Type": "UnopExpr",
            "Rhs": _convert_node(node.operand),
            "Token_Op": {"Source": node.op}
        }
    elif typ == "Call":
        return {
            "Type": "CallExpr",
            "Base": _convert_node(node.func),
            "FunctionArguments": {"ArgList": [_convert_node(a) for a in node.args]}
        }
    elif typ == "Index":
        return {
            "Type": "IndexExpr",
            "Base": _convert_node(node.obj),
            "Index": _convert_node(node.index)
        }
    elif typ == "Parens":
        return {"Type": "ParenExpr", "Expression": _convert_node(node.expr)}
    elif typ == "Return":
        return {"Type": "ReturnStat", "ExprList": [_convert_node(v) for v in node.values] if node.values else []}
    elif typ == "If":
        return {
            "Type": "IfStat",
            "Condition": _convert_node(node.cond),
            "Body": {"StatementList": [_convert_node(s) for s in node.then_body]},
            "ElseClauseList": [_convert_node(s) for s in node.else_body] if node.else_body else []
        }
    elif typ == "While":
        return {
            "Type": "WhileStat",
            "Condition": _convert_node(node.cond),
            "Body": {"StatementList": [_convert_node(s) for s in node.body]}
        }
    elif typ == "Repeat":
        return {
            "Type": "RepeatStat",
            "Condition": _convert_node(node.cond),
            "Body": {"StatementList": [_convert_node(s) for s in node.body]}
        }
    elif typ == "For":
        return {
            "Type": "NumericForStat",
            "RangeList": [_convert_node(node.start), _convert_node(node.end), _convert_node(node.step) if node.step else None],
            "Body": {"StatementList": [_convert_node(s) for s in node.body]}
        }
    elif typ == "ForIn":
        return {
            "Type": "GenericForStat",
            "Names": [_convert_node(v) for v in node.names],
            "ExprList": [_convert_node(v) for v in node.exprs],
            "Body": {"StatementList": [_convert_node(s) for s in node.body]}
        }
    elif typ == "FuncDef":
        return {
            "Type": "FunctionDef",
            "Name": _convert_node(node.name),
            "Parameters": [_convert_node(p) for p in node.params],
            "Body": _convert_node(node.body)
        }
    elif typ == "Table":
        return {
            "Type": "TableLiteral",
            "Fields": [_convert_node(f) for f in node.fields] if hasattr(node, 'fields') else []
        }
    elif typ == "TableField":
        return {
            "Type": "TableField",
            "Key": _convert_node(node.key) if node.key else None,
            "Value": _convert_node(node.value)
        }
    else:
        return {"Type": typ, "Raw": repr(node)}

def loadast(script):
    try:
        tree = lua_parser.parse(script)
        return _convert_node(tree)
    except Exception as e:
        raise RuntimeError(f"Parse error: {e}")

def refineast(ast, options):
    if options.get("RenameVariables"):
        rename_map = {}
        counter = 0
        def rename(node):
            nonlocal counter
            if isinstance(node, dict):
                if node.get("Type") == "VariableExpr" and "Variable" in node and "Name" in node["Variable"]:
                    name = node["Variable"]["Name"]
                    if name not in rename_map:
                        counter += 1
                        rename_map[name] = f"v{counter}"
                    node["Variable"]["Name"] = rename_map[name]
                else:
                    for key, value in node.items():
                        if isinstance(value, (dict, list)):
                            rename(value)
            elif isinstance(node, list):
                for item in node:
                    rename(item)
        rename(ast)
    if options.get("Format"):
        pass
    return ast

def refineastnode(ast, options):
    return refineast(ast, options)

def _serialize_node(node):
    if isinstance(node, dict):
        typ = node.get("Type")
        if typ == "Chunk":
            return "\n".join(_serialize_node(s) for s in node.get("StatementList", []))
        elif typ == "AssignmentStat":
            lhs = ", ".join(_serialize_node(v) for v in node.get("Lhs", []))
            rhs = ", ".join(_serialize_node(v) for v in node.get("Rhs", []))
            return f"{lhs} = {rhs}"
        elif typ == "LocalVarStat":
            exprs = ", ".join(_serialize_node(v) for v in node.get("ExprList", []))
            return f"local {exprs}" if exprs else "local"
        elif typ == "VariableExpr":
            return node["Variable"]["Name"]
        elif typ == "NumberLiteral":
            return node["Token"]["Source"]
        elif typ == "StringLiteral":
            return f'"{node["Token"]["Source"]}"'
        elif typ == "NilLiteral":
            return "nil"
        elif typ == "BooleanLiteral":
            return node["Token"]["Source"]
        elif typ == "BinopExpr":
            lhs = _serialize_node(node["Lhs"])
            rhs = _serialize_node(node["Rhs"])
            op = node["Token_Op"]["Source"]
            return f"({lhs} {op} {rhs})"
        elif typ == "UnopExpr":
            rhs = _serialize_node(node["Rhs"])
            op = node["Token_Op"]["Source"]
            return f"{op}({rhs})"
        elif typ == "CallExpr":
            base = _serialize_node(node["Base"])
            args = ", ".join(_serialize_node(a) for a in node["FunctionArguments"]["ArgList"])
            return f"{base}({args})"
        elif typ == "IndexExpr":
            base = _serialize_node(node["Base"])
            idx = _serialize_node(node["Index"])
            return f"{base}[{idx}]"
        elif typ == "ParenExpr":
            return f"({_serialize_node(node['Expression'])})"
        elif typ == "ReturnStat":
            exprs = ", ".join(_serialize_node(v) for v in node.get("ExprList", []))
            return f"return {exprs}" if exprs else "return"
        elif typ == "IfStat":
            cond = _serialize_node(node["Condition"])
            body = "\n".join(_serialize_node(s) for s in node["Body"]["StatementList"])
            elseparts = []
            for elseclause in node.get("ElseClauseList", []):
                if elseclause.get("ClauseType") == "elseif":
                    econd = _serialize_node(elseclause["Condition"])
                    ebody = "\n".join(_serialize_node(s) for s in elseclause["Body"]["StatementList"])
                    elseparts.append(f"elseif {econd} then\n{ebody}")
                else:
                    ebody = "\n".join(_serialize_node(s) for s in elseclause["Body"]["StatementList"])
                    elseparts.append(f"else\n{ebody}")
            return f"if {cond} then\n{body}\n" + "\n".join(elseparts) + "\nend"
        elif typ == "WhileStat":
            cond = _serialize_node(node["Condition"])
            body = "\n".join(_serialize_node(s) for s in node["Body"]["StatementList"])
            return f"while {cond} do\n{body}\nend"
        elif typ == "RepeatStat":
            cond = _serialize_node(node["Condition"])
            body = "\n".join(_serialize_node(s) for s in node["Body"]["StatementList"])
            return f"repeat\n{body}\nuntil {cond}"
        elif typ == "NumericForStat":
            var = _serialize_node(node.get("Variable", {}))
            start = _serialize_node(node["RangeList"][0])
            end = _serialize_node(node["RangeList"][1])
            step = _serialize_node(node["RangeList"][2]) if len(node["RangeList"]) > 2 and node["RangeList"][2] is not None else ""
            step_str = f", {step}" if step else ""
            body = "\n".join(_serialize_node(s) for s in node["Body"]["StatementList"])
            return f"for {var} = {start}, {end}{step_str} do\n{body}\nend"
        elif typ == "GenericForStat":
            names = ", ".join(_serialize_node(v) for v in node.get("Names", []))
            exprs = ", ".join(_serialize_node(v) for v in node.get("ExprList", []))
            body = "\n".join(_serialize_node(s) for s in node["Body"]["StatementList"])
            return f"for {names} in {exprs} do\n{body}\nend"
        elif typ == "FunctionDef":
            name = _serialize_node(node["Name"]) if node.get("Name") else ""
            params = ", ".join(_serialize_node(p) for p in node.get("Parameters", []))
            body = _serialize_node(node["Body"])
            return f"function {name}({params})\n{body}\nend"
        elif typ == "TableLiteral":
            fields = []
            for f in node.get("Fields", []):
                if f.get("Key") is not None:
                    key = _serialize_node(f["Key"])
                    val = _serialize_node(f["Value"])
                    fields.append(f"[{key}] = {val}")
                else:
                    val = _serialize_node(f["Value"])
                    fields.append(val)
            return "{" + ", ".join(fields) + "}"
        else:
            return str(node)
    elif isinstance(node, list):
        return "\n".join(_serialize_node(v) for v in node)
    else:
        return str(node)

def displayast(ast):
    if ast is None:
        return ""
    if isinstance(ast, dict) and ast.get("Type") == "Chunk":
        return _serialize_node(ast)
    return _serialize_node(ast)

def resolvearithmetic(ast):
    def fold(node):
        if isinstance(node, dict):
            typ = node.get("Type")
            if typ == "BinopExpr":
                lhs = fold(node["Lhs"])
                rhs = fold(node["Rhs"])
                if lhs and rhs and isinstance(lhs, (int, float)) and isinstance(rhs, (int, float)):
                    op = node["Token_Op"]["Source"]
                    try:
                        if op == "+": result = lhs + rhs
                        elif op == "-": result = lhs - rhs
                        elif op == "*": result = lhs * rhs
                        elif op == "/": result = lhs / rhs
                        elif op == "^": result = lhs ** rhs
                        elif op == "%": result = lhs % rhs
                        else: return node
                        return {"Type": "NumberLiteral", "Token": {"Type": "Number", "LeadingWhite": "", "Source": str(result)}}
                    except:
                        return node
                return node
            elif typ == "UnopExpr":
                rhs = fold(node["Rhs"])
                if isinstance(rhs, (int, float)):
                    op = node["Token_Op"]["Source"]
                    if op == "-": result = -rhs
                    elif op == "not": result = not rhs
                    else: return node
                    return {"Type": "NumberLiteral" if isinstance(result, (int, float)) else "BooleanLiteral",
                            "Token": {"Type": "Number" if isinstance(result, (int, float)) else "Boolean",
                                      "LeadingWhite": "", "Source": str(result)}}
                return node
            else:
                for key, value in node.items():
                    if isinstance(value, (dict, list)):
                        node[key] = fold(value)
                return node
        elif isinstance(node, list):
            return [fold(item) for item in node]
        return node
    return fold(ast)
