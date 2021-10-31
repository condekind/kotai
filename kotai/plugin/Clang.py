#!/usr/bin/env python3
# =========================================================================== #

import subprocess as sp
from subprocess import PIPE, CompletedProcess
from dataclasses import dataclass
from pathlib import Path
import logging

from kotai.types import ExitCode, CmdResult, Timeout

# --------------------------------------------------------------------------- #

@dataclass
class Clang():

    ifile: Path
    ofile: Path
    clang: Path = Path('clang')
    optFlag: str = 'O0'

    def cmd(self) -> list[str]:
        return Timeout['Clang'] + [
            f'{self.clang}',
            '-g',
            '-ggdb',
            '-Xclang',
            '-disable-O0-optnone',
            f'-{self.optFlag}',
            '-std=c2x',
            '-Wall',
            '-fno-stack-protector',
            '-no-pie',
            '-o', f'{self.ofile}',
            f'{self.ifile}',
        ]

    def _run(self) -> sp.CompletedProcess[bytes]:
        return sp.run(self.cmd(), stdout=PIPE, stderr=PIPE)


    def runcmd(self) -> CmdResult:
        proc = self._run()
        return _cmdresult(proc)



def _cmdresult(proc: CompletedProcess[bytes]) -> CmdResult:
    match proc.returncode:
        case 0:
            try:
                clangout = proc.stdout.decode('utf-8')
            except UnicodeDecodeError as ude:
                logging.error(f'clang: {ude}')
                return ('UnicodeDecodeError', ExitCode.ERR)
            else:
                return (clangout, ExitCode.OK)
        case _:
            try:
                procErrMsg = proc.stderr.decode('utf-8')
            except UnicodeDecodeError as ude:
                logging.error(f'clang: {ude}')
                return ('UnicodeDecodeError', ExitCode.ERR)
            else:
                logging.error(f'clang: {procErrMsg=}')
                return (procErrMsg, ExitCode.ERR)