from typing import NamedTuple, Literal
from enum import Enum
from pathlib import Path
from subprocess import CompletedProcess
import logging

class ExitCode(Enum):
    OK = 0,
    ERR = 1,  # Generic error

SysExitCode = ExitCode | str

# Arguments received by the worker function (compiling+running+stats)
class ProcArgs(NamedTuple):
    cFile: Path          # Name of the file to be compiled
    clean: bool = False # Whether existing files are to be cleaned or not

CmdResult = tuple[str, ExitCode]

# Wrapper to subprocess.run that decodes and handles exceptions
def cmdresult(self, proc: CompletedProcess[bytes]) -> CmdResult:
    if proc.returncode == 0:
        try: proc_out = proc.stdout.decode('utf-8')
        except Exception as e:
            logging.error(f'proc_out: {e}')
            return (f'{e}', ExitCode.ERR)
        else: return (proc_out, ExitCode.OK)

    try: proc_err = proc.stderr.decode('utf-8')
    except Exception as e:
        logging.error(f'{e}')
        return (f'{e}', ExitCode.ERR)
    else:
        logging.error(f'{proc_err=}')  # decoded stderr from process
        return (proc_err, ExitCode.ERR)

Timeout = {
    'ClangPluginPrintDescriptors' : ['timeout', '3s'],
    'Konstrain'                   : ['timeout', '3s'],
    'Jotai'                       : ['timeout', '3s'],
    'Clang'                       : ['timeout', '3s'],
    'cfggrind_asmmap'             : ['timeout', '3s'],
    'valgrind_with_cfggrind'      : ['timeout', '3s'],
    'cfggrind_info'               : ['timeout', '3s'],
}

CStdHeaderName = Literal[
    'assert.h',
    'complex.h',
    'ctype.h',
    'errno.h',
    'fenv.h',
    'float.h',
    'inttypes.h',
    'iso646.h',
    'limits.h',
    'locale.h',
    'math.h',
    'setjmp.h',
    'signal.h',
    'stdalign.h',
    'stdarg.h',
    'stdatomic.h',
    'stdbool.h',
    'stddef.h',
    'stdint.h',
    'stdio.h',
    'stdlib.h',
    'stdnoreturn.h',
    'string.h',
    'tgmath.h',
    'threads.h',
    'time.h',
    'uchar.h',
    'wchar.h',
    'wctype.h',
]