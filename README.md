# IronBrew Lua Deobfuscator
### axomic

A tool to reverse IronBrew/AztupBrew obfuscation. converts it back to readable Lua source.

## Features

- Detects IronBrew V2.7.0, V2.7.1, and AztupBrew V2.7.2
- Renames variables and formats output
- Handles super‑instructions (multi‑opcode patterns)

## Requirements

- Python 3.6+
- `lua-parser` – see `requirements.txt`

## Installation

```
pip install -r requirements.txt
```

Main file = ```processor.py```
