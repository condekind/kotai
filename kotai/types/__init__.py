#!/usr/bin/env python3
# =========================================================================== #

from typing import Callable, NamedTuple, Literal, Any
from enum import Enum
from pathlib import Path
import subprocess as sp
import logging


# (cf: Path, fn: str)
BenchInfo = dict[Any, Any]
FileWithFnName = tuple[Any, Any]


class ExitCode(Enum):
    OK  = 0,
    ERR = 1,  # Generic error
SysExitCode = ExitCode | str


LogLevel = Literal['info', 'warning', 'error', 'critical', 'debug']
Log: dict[LogLevel, Callable[..., None]] = {
    'info'     : logging.info,
    'warning'  : logging.warning,
    'error'    : logging.error,
    'critical' : logging.critical,
    'debug'    : logging.debug,
}


# Arguments received by the worker function (compiling+running+stats)
class ProcArgs(NamedTuple):
    cFile: Path          # Name of the file to be compiled
    clean: bool = False # Whether existing files are to be cleaned or not


# CmdResult just models (result,errcode) as (str,int)
class CmdResult(NamedTuple):
    msg: str
    err: ExitCode = ExitCode.ERR


# When returning, if logging is desired, this allows `return logret(msg, ret)`
def logret(msg: Any, ret: CmdResult = CmdResult('', ExitCode.ERR),
           level: LogLevel = 'error'):
    ''' Calls logging.<level> with msg and propagates ret'''
    Log[level](f'{msg}')
    return ret


#def res2utf8(proc: CompletedProcess[bytes], errIsOut: bool) -> CmdResult:
def res2utf8(out: bytes, err: bytes, errIsOut: bool) -> CmdResult:
    '''
    subprocess.run() Result To UTF-8 (plus ExitCode)

    Tries to decode stdout/stderr of the completed process, logging the steps
    when appropriate. Both successful outputs and raised exceptions are
    converted into error-values (str, ExitCode). The value of proc.returncode
    dictates whether stdout or stderr are used.
    '''
    outStream = err if errIsOut else out

    try: pout = outStream.decode('utf-8')
    except Exception as e: return logret(e)
    else: return CmdResult(pout, ExitCode.OK)

def out2file(ret: CmdResult, ofpath: Path, breakLines: bool) -> CmdResult:
    try:
        with open(ofpath, 'w+', encoding='utf-8') as fout:

            if breakLines:
                txt = [ line+'\n' for l
                        in ret.msg.replace('\r','').split('\n')
                        if (line := l.strip(' ,')) ]
                fout.writelines(txt)

            else:
                fout.write(ret.msg)

    # Common exceptions(s): OSError, ValueError, IOError
    except Exception as e:
        return logret(e)
    else:
        return ret

def runproc(proc_args: list[str], timeout: float,
            ofpath: Path | None = None, breakLines: bool = False) -> CmdResult:
    '''
    Wrapper to subprocces.run that tries to: run, decode, write, return
    Exceptions raised are converted to error-values

    - runs command with args and a timeout, provided in proc_args and timeout
    - decodes the result
    - writes it to ofpath when defined, and
    - returns it with the proper ExitCode
    '''

    try: proc = sp.Popen(proc_args, text=True, close_fds=True,
                         stdout=sp.PIPE, stderr=sp.PIPE, encoding='utf-8')

    # Common exceptions(s): OSError, ValueError
    except Exception as e:
        return logret(e)

    # Common exceptions(s): TimeoutExpired
    try: proc.communicate(timeout=timeout)
    except Exception as e: logging.error(f'{e}:"{proc.args}"')

    proc.kill()  # After this point, proc.returncode can't be None
    out, err = proc.communicate()  # Results
    if out: logging.debug(f'{out=}')
    if err: logging.error(f'{err=}')

    res = CmdResult(out, ExitCode.ERR if proc.returncode else ExitCode.OK)
    return out2file(res, ofpath, breakLines) if ofpath else res



# =========================================================================== #
