"""Tests for sandbox security: AST validation and env stripping."""
from quantclaw.sandbox.security import validate_imports, strip_env


def test_safe_code_passes():
    code = "import pandas as pd\nimport numpy as np\nresult = pd.DataFrame()"
    warnings = validate_imports(code)
    assert len(warnings) == 0


def test_subprocess_import_is_critical():
    code = "import subprocess\nsubprocess.run(['ls'])"
    warnings = validate_imports(code)
    assert len(warnings) >= 1
    assert any(w.module == "subprocess" and w.critical for w in warnings)


def test_socket_import_is_critical():
    code = "import socket\nsocket.create_connection(('evil.com', 80))"
    warnings = validate_imports(code)
    assert any(w.module == "socket" and w.critical for w in warnings)


def test_urllib_import_is_critical():
    code = "from urllib.request import urlopen\nurlopen('http://evil.com')"
    warnings = validate_imports(code)
    assert any(w.module == "urllib" and w.critical for w in warnings)


def test_requests_import_is_critical():
    code = "import requests\nrequests.get('http://evil.com')"
    warnings = validate_imports(code)
    assert any(w.module == "requests" and w.critical for w in warnings)


def test_pickle_import_is_critical():
    code = "import pickle\npickle.loads(b'')"
    warnings = validate_imports(code)
    assert any(w.module == "pickle" and w.critical for w in warnings)


def test_from_shutil_import_is_critical():
    code = "from shutil import rmtree"
    warnings = validate_imports(code)
    assert any(w.module == "shutil" and w.critical for w in warnings)


def test_eval_call_is_critical():
    code = "eval('1+1')"
    warnings = validate_imports(code)
    assert any(w.module == "eval" and w.critical for w in warnings)


def test_exec_call_is_critical():
    code = "exec('x = 1')"
    warnings = validate_imports(code)
    assert any(w.module == "exec" and w.critical for w in warnings)


def test_dynamic_import_is_critical():
    code = "__import__('socket').create_connection(('x', 1))"
    warnings = validate_imports(code)
    assert any(w.module == "__import__" and w.critical for w in warnings)


def test_getattr_call_is_critical():
    # getattr() is the classic sandbox-escape primitive.
    code = "getattr(object, '__subclasses__')"
    warnings = validate_imports(code)
    assert any(w.module == "getattr" and w.critical for w in warnings)


def test_dunder_class_access_is_critical():
    # The classic escape: ().__class__.__mro__[1].__subclasses__()
    code = "x = ().__class__"
    warnings = validate_imports(code)
    assert any(w.module == "__class__" and w.critical for w in warnings)


def test_dunder_subclasses_access_is_critical():
    code = "x = cls.__subclasses__()"
    warnings = validate_imports(code)
    assert any(w.module == "__subclasses__" and w.critical for w in warnings)


def test_dunder_globals_access_is_critical():
    code = "g = func.__globals__"
    warnings = validate_imports(code)
    assert any(w.module == "__globals__" and w.critical for w in warnings)


def test_os_is_allowed():
    # `os` is allowed because system-generated wrappers need it; env stripping
    # and subprocess isolation are the primary defenses.
    code = "import os\nprint(os.getcwd())"
    warnings = validate_imports(code)
    assert len(warnings) == 0


def test_pathlib_is_allowed():
    code = "from pathlib import Path\np = Path('data')"
    warnings = validate_imports(code)
    assert len(warnings) == 0


def test_allowed_imports_pass():
    code = "import math\nimport json\nimport re\nimport datetime"
    warnings = validate_imports(code)
    assert len(warnings) == 0


def test_numpy_pandas_scipy_pass():
    code = "import numpy\nimport pandas\nimport scipy\nimport sklearn"
    warnings = validate_imports(code)
    assert len(warnings) == 0


def test_strip_env_removes_secrets():
    env = {
        "PATH": "/usr/bin",
        "HOME": "/home/user",
        "ANTHROPIC_API_KEY": "sk-ant-xxx",
        "OPENAI_API_KEY": "sk-xxx",
        "DATABASE_TOKEN": "dbtoken",
        "MY_SECRET": "shhh",
        "PYTHONPATH": "/code",
        "NORMAL_VAR": "hello",
    }
    stripped = strip_env(env)
    assert "PATH" in stripped
    assert "HOME" in stripped
    assert "PYTHONPATH" in stripped
    assert "ANTHROPIC_API_KEY" not in stripped
    assert "OPENAI_API_KEY" not in stripped
    assert "DATABASE_TOKEN" not in stripped
    assert "MY_SECRET" not in stripped
    assert "NORMAL_VAR" in stripped


def test_syntax_error_in_code():
    code = "def foo(\n"
    warnings = validate_imports(code)
    assert isinstance(warnings, list)
