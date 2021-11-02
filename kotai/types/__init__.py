from typing import Callable, NamedTuple, Literal, Any
from enum import Enum
from pathlib import Path
import subprocess as sp
from subprocess import CompletedProcess, PIPE
import logging

class ExitCode(Enum):
    OK  = 0,
    ERR = 1,  # Generic error

SysExitCode = ExitCode | str

LogLevel = Literal[
    'info',
    'warning',
    'error',
    'critical',
    'debug',
]
Log: dict[LogLevel, Callable[..., None]] = {
    'info' : logging.info,
    'warning' : logging.warning,
    'error' : logging.error,
    'critical' : logging.critical,
    'debug' : logging.debug,
}

OptFlag = Literal[
    'O0',
    'O1',
    'O2',
    'O3',
    'Ofast',
    'Oz',
    'Os',
]

# Arguments received by the worker function (compiling+running+stats)
class ProcArgs(NamedTuple):
    cFile: Path          # Name of the file to be compiled
    clean: bool = False # Whether existing files are to be cleaned or not

class CmdResult(NamedTuple):
    msg: str
    err: ExitCode = ExitCode.ERR

ErrResult = CmdResult('', ExitCode.ERR)

class FileWithFnName(NamedTuple):
    cf: Path
    fn: str

def logret(msg: Any, ret: CmdResult = ErrResult, level: LogLevel = 'error'):
    ''' Calls logging.<level> with msg and propagates ret'''
    Log[level](f'{msg}')
    return ret

def outret(ret: CmdResult, ofpath: Path | None, ofmode: str,
           breakLines: bool) -> CmdResult:
    '''If ofpath != None, write ret.msg to it, otherwise just propagate ret'''
    if ofpath:
        try: fout = open(ofpath, ofmode)
        except Exception as e: return logret(e)
        with fout:
            if breakLines: fout.writelines([c + '\n' for l
                                 in ret.msg.replace('\r','').split('\n')
                                 if (c := l.strip())])
            else: print(ret.msg, file=fout)
    return ret

def res2utf8(proc: CompletedProcess[bytes], errIsOut: bool) -> CmdResult:
    '''
    subprocess.run() Result To UTF-8 (plus ExitCode)

    Tries to decode stdout/stderr of the completed process, logging the steps
    when appropriate. Both successful outputs and raised exceptions are
    converted into error-values (str, ExitCode). The value of proc.returncode
    dictates whether stdout or stderr are used.
    '''
    outStream = proc.stderr if errIsOut else proc.stdout

    if proc.returncode == 0:
        try: pout = outStream.decode('utf-8')
        except Exception as e: return logret(e)
        else: return CmdResult(pout, ExitCode.OK)
    else:
        try: perr = proc.stderr.decode('utf-8')
        except Exception as e: return logret(e)
        else: return logret(f'{perr=}', ret=CmdResult(perr, ExitCode.ERR))



def runproc(proc_args: list[str], timeout: float,
           ofpath: Path | None = None, ofmode: str = 'w',
           breakLines: bool = False, errIsOut: bool = False):
    '''
    Wrapper to subprocces.run that tries to: run, decode, write, return
    Exceptions raised are converted to error-values

    - runs command with args and a timeout, provided in proc_args and timeout
    - decodes the result
    - writes it to ofpath when defined, and
    - returns it with the proper ExitCode
    '''
    try: return outret(res2utf8(sp.run(proc_args, timeout=timeout,
                                       stdout=PIPE, stderr=PIPE), errIsOut),
                                ofpath, ofmode, breakLines)
    except Exception as e: return logret(e)

# # Wrapper to subprocess.run that decodes and handles exceptions
# def cmdresult(proc: CompletedProcess[bytes]) -> CmdResult:
#     if proc.returncode == 0:
#         try: proc_out = proc.stdout.decode('utf-8')
#         except Exception as e:
#             logging.error(f'proc_out: {e}')
#             return (f'{e}', ExitCode.ERR)
#         else: return (proc_out, ExitCode.OK)

#     try: proc_err = proc.stderr.decode('utf-8')
#     except Exception as e:
#         logging.error(f'{e}')
#         return (f'{e}', ExitCode.ERR)
#     else:
#         logging.error(f'{proc_err=}')  # decoded stderr from process
#         return (proc_err, ExitCode.ERR)

Timeout: dict[str,float] = {
    'ClangPluginPrintDescriptors' : 3.0,
    'Konstrain'                   : 3.0,
    'Jotai'                       : 3.0,
    'Clang'                       : 3.0,
    'cfggrind_asmmap'             : 3.0,
    'valgrind_with_cfggrind'      : 3.0,
    'cfggrind_info'               : 3.0,
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