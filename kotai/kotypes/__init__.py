#!/usr/bin/env python3
# =========================================================================== #

from typing import Callable, Final, Generic, Iterator, Iterable, NamedTuple, Literal, Any, TypeAlias, TypeGuard, TypeVar, final
from enum import Enum
from pathlib import Path
import subprocess as sp
import logging

def noop(*args: Any, **kwargs: Any): pass


# ----------------------------------- Logging ------------------------------- #
'''
Reference:
https://docs.python.org/3/library/logging.html

Tutorial:
https://docs.python.org/3/howto/logging.html

You better read the above, since I didn't. I just came up with some twisted
hackery to avoid calling expensive functions when we're not logging stuff.
'''

#https://docs.python.org/3.10/howto/logging.html#logging-levels
LogLevel = Literal['critical', 'error', 'warning', 'info', 'debug']
'''Valid log levels (except NOTSET, since there's no function for it)'''

_RealLog: Final[dict[LogLevel, Callable[..., None]]] = {
    'critical' : logging.critical,  # 50
    'error'    : logging.error,     # 40
    'warning'  : logging.warning,   # 30
    'info'     : logging.info,      # 20
    'debug'    : logging.debug,     # 10
}
_FakeLog: Final[dict[LogLevel, Callable[..., None]]] = {
    'critical' : noop,
    'error'    : noop,
    'warning'  : noop,
    'info'     : noop,
    'debug'    : noop,
}

Log: dict[LogLevel, Callable[..., None]]
'''
If logging is enabled, maps a string `'foo'` to the function `logging.foo(...)`

If logging is disabled, maps `foo` to a noop.

In both cases, `'foo'` must be a valid logging level, all lowercase.
'''

def setLog(on: bool) -> None:
    global Log
    if on: Log = _RealLog
    else : Log = _FakeLog


# ---------------------------------- Konstrain ------------------------------ #

KonstrainExecType = Literal['', 'all', 'int-bounds', 'big-arr', 'big-arr-10x',]
'''String literals representing the "ExecTypes" we accept from the user'''

KonstrainExecTypes: Final[list[KonstrainExecType]] = [
    'int-bounds',
    'big-arr',
    'big-arr-10x',
]
'''List of all non-abstract (implemented) KonstrainExecTypes'''


# ------------------------------------ CComp -------------------------------- #

# String literals representing OptLevels we accept from the user
OptLevel = Literal['', 'all', 'O0', 'O1', 'O2', 'O3', 'Ofast', 'Os', 'Oz',]

# List of all non-abstract (implemented) OptLevels
OptLevels: Final[list[OptLevel]] = ['O0', 'O1', 'O2', 'O3', 'Ofast',
                                    'Os', 'Oz',]


# ------------------------------------ Error -------------------------------- #

@final
class ExitCode(Enum):

    @final
    def __bool__(self): return bool(self.value)

    #@final
    #class __ExitCode_OK:
    #    def __bool__(self): return True
#
    #@final
    #class __ExitCode_ERR:
    #    def __bool__(self): return False

    OK:  Final  = True
    ERR: Final  = False

# Aliases
Success: TypeAlias = Literal[ExitCode.OK]
"""Type representing Success"""

Failure: TypeAlias = Literal[ExitCode.ERR]
"""Type representing Failure"""

success: Final[Success] = ExitCode.OK
'''Value representing success'''

failure: Final[Failure] = ExitCode.ERR
'''Value representing failure'''

class BenchInfo:
    __slots__ = (
                 'cFilePath',
                 'fnName',
                 'ketList',
                 'optLevelList',
                 'exitCodes',
                 'descriptor'
                 )

    def __init__(self,
                 cFilePath: Path,
                 fnName: str = '',
                 ketList: list[KonstrainExecType] = [],
                 optLevelList: list[OptLevel] = [],
                 exitCodes: dict[Any, ExitCode] = {},
                 descriptor: str = '',
            ) -> None:

        self.cFilePath: Path                  = cFilePath
        self.fnName: str                      = fnName
        self.ketList: list[KonstrainExecType] = ketList
        self.optLevelList: list[OptLevel]     = optLevelList
        self.exitCodes: dict[Any, ExitCode]   = exitCodes
        self.descriptor: str                  = descriptor

    #def __bool__(self): return bool(self.exitCode)
    def __bool__(self): return any(self.exitCodes.values())

    def setExitCodes(self, exitCodes: dict[Any, ExitCode]) -> None:
        self.exitCodes = exitCodes

    def Err(self, key:Any, logmsg: str = '', level: LogLevel = 'debug'):
        self.exitCodes = {key: failure}
        if logmsg: Log[level](logmsg)
        return self


# TypeGuard for BenchInfo
def valid(result: BenchInfo | ExitCode) -> TypeGuard[BenchInfo] : return bool(result)

def foo(result: BenchInfo | Failure) -> str:
    if valid(result):
        return 'valid'
    else:
        return 'invalid'

SysExitCode = ExitCode | str

# CmdResult just models (result,errcode) as (str,int)
class CmdResult(NamedTuple):
    msg: str
    err: ExitCode = failure


# When returning, if logging is desired, this allows `return logret(msg, ret)`
def logret(msg: Any, ret: CmdResult = CmdResult('', ExitCode.ERR),
           level: LogLevel = 'error') -> CmdResult:
    ''' Calls logging.<level> with msg and propagates ret'''
    Log[level](f'{msg}')
    return ret


class LogThen:

    @staticmethod
    def Ok(msg: str, level: LogLevel = 'info') -> Success:
        Log[level](f'{msg}')
        return success

    @staticmethod
    def Err(msg: str, level: LogLevel = 'error') -> Failure:
        Log[level](f'{msg}')
        return failure


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



_T_co = TypeVar("_T_co", covariant=True)
_T1 = TypeVar("_T1")
_T2 = TypeVar("_T2")
class unzip(Iterator[_T_co], Generic[_T_co]):
    '''
    Opposite of zip(), as the example shows:
    ```
    res = [(out, err) for out, err in fn(...)]
    >>> [(out0, err0), (out1, err1), (out2, err2)]

    [_ for _ in unzip(res)]
    >>> [(out0, out1, out2), (err0, err1, err2)]
    ```

    You can also see this as "transpose", however it was made for and only
    tested for [N,2] -> [2,N] dimensions. The type checker will likely complain
    for other values.

    See https://github.com/python/typeshed/blob/master/stdlib/builtins.pyi for
    ideas on how to extend the type annotations if you need it.
    '''
    def __new__(cls, iterable: Iterable[tuple[_T1 | _T2]]
                ) -> Iterable[ Iterable[_T1 | _T2] ]:
        return zip(*iterable)


# =========================================================================== #
