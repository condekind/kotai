#!/usr/bin/env python3

import subprocess as sp
from subprocess import PIPE, CompletedProcess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
import logging

from kotai.types import CmdResult, ExitCode, Timeout

ConstraintKind = Literal['int-bounds', 'loops', 'big-arr-10x', 'big-arr']


@dataclass
class ClangPluginPrintDescriptors():

    ifile:   Path
    clang:   Path = Path('clang')
    libPath: Path = Path('./build/lib/libPrintDescriptors.so')
    name:    str = 'print-descriptors'

    def cmd(self) -> list[str]:
        return Timeout['ClangPluginPrintDescriptors'] + [
            f'{self.clang}',
            '-cc1',
            '-load',
            f'{self.libPath}',
            '-plugin',
            f'{self.name}',
            f'{self.ifile}',
        ]

    def _run(self) -> sp.CompletedProcess[bytes]:
        return sp.run(self.cmd(), stdout=PIPE, stderr=PIPE)


    def runcmd(self) -> CmdResult:
        proc = self._run()
        return _cmdresult(proc)


    def __str__(self) -> str:
        return 'clang-plugin: print-descriptors'



def _cmdresult(proc: CompletedProcess[bytes]) -> CmdResult:
    match proc.returncode:
        case 0:
            try:
                desc = proc.stdout.decode('utf-8')
            except UnicodeDecodeError:
                logging.error('Print Descriptors: UnicodeDecodeError')
                return ('UnicodeDecodeError', ExitCode.ERR)
            else:
                return (desc, ExitCode.OK)
        case _:
            try:
                procErrMsg = proc.stderr.decode('utf-8')
            except UnicodeDecodeError:
                logging.error('Print Descriptors: UnicodeDecodeError')
                return ('UnicodeDecodeError', ExitCode.ERR)
            else:
                logging.error(f'Print Descriptors error: {procErrMsg=}')
                return (procErrMsg, ExitCode.ERR)