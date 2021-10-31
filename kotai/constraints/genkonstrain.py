#!/usr/bin/env python3

import subprocess as sp
from subprocess import PIPE, CompletedProcess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import logging

from kotai.types import ExitCode, Timeout

KonstrainExecType = Literal[
    'all',
    'int-bounds',
    'big-arr',
    'big-arr-10x'
]
KonstrainExecTypes: list[KonstrainExecType] = [
    'int-bounds',
    'big-arr',
    'big-arr-10x'
]
KonstrainResult = tuple[list[str], ExitCode]

@dataclass
class Konstrain:

    ifile:      Path
    descriptor: Path
    execType:   KonstrainExecType = 'all'
    timeout     = 30
    jarPath = Path(('kotai/constraints/konstrain/target/'
        'konstrain-1.0-SNAPSHOT-jar-with-dependencies.jar')).resolve()

    def cmd(self) -> list[str]:
        return Timeout['Konstrain'] + [
            'timeout',      f'{self.timeout}',
            'java', '-jar', f'{self.jarPath}',
            str(self.descriptor),
            str(self.execType),
        ]


    def _run(self) -> sp.CompletedProcess[bytes]:
        return sp.run(self.cmd(), stdout=PIPE, stderr=PIPE)


    def runcmd(self) -> KonstrainResult:
        proc = self._run()
        return _cmdresult(proc)



def _cmdresult(proc: CompletedProcess[bytes]) -> KonstrainResult:
    match proc.returncode:
        case 0:
            try:
                constraints = proc.stdout.decode('utf-8')
            except UnicodeDecodeError:
                logging.error('UnicodeDecodeError')
                return (['UnicodeDecodeError'], ExitCode.ERR)
            else:
                _result = list(map(
                    lambda c:
                        c.rstrip(" ,\n"),filter(
                            lambda c:
                                c, constraints.split("\n"))))

                return (_result, ExitCode.OK)
        case _:
            try:
                procErrMsg = proc.stderr.decode('utf-8')
            except UnicodeDecodeError:
                logging.error('UnicodeDecodeError')
                return (['UnicodeDecodeError'], ExitCode.ERR)
            else:
                logging.error(f'Konstrain error: {procErrMsg=}')
                return (procErrMsg.split(), ExitCode.ERR)