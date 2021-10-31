#!/usr/bin/env python3
# =========================================================================== #

import subprocess as sp
from subprocess import PIPE, CompletedProcess
from dataclasses import dataclass
from pathlib import Path
import logging

from kotai.types import CmdResult, ExitCode, Timeout

# --------------------------------------------------------------------------- #

@dataclass
class Jotai():

    constraintsPath: Path
    descriptorPath: Path
    jotaiBinPath: Path = Path('./build/lib/Jotai')

    def cmd(self) -> list[str]:
        return Timeout['Jotai'] + [
            f'{self.jotaiBinPath}',
            f'{self.constraintsPath}',
            f'{self.descriptorPath}',
        ]

    def _run(self) -> sp.CompletedProcess[bytes]:
        return sp.run(self.cmd(), stdout=PIPE, stderr=PIPE)


    def runcmd(self) -> CmdResult:
        proc = self._run()
        return _cmdresult(proc)



def _cmdresult(proc: CompletedProcess[bytes]) -> CmdResult:
    match proc.returncode:
        case 0:  # success
            try:
                genBench = proc.stdout.decode('utf-8')
            except UnicodeDecodeError as ude:
                logging.error(f'{ude}: jotai: UnicodeDecodeError')
                return (f'{ude}', ExitCode.ERR)
            else:
                return (genBench, ExitCode.OK)
        case _:  # failure
            try:
                procErrMsg = proc.stderr.decode('utf-8')
            except UnicodeDecodeError as ude:
                logging.error(f'{ude}: jotai: UnicodeDecodeError')
                return (f'{ude}', ExitCode.ERR)
            else:
                logging.error(f'Jotai error: {procErrMsg=}')
                return (procErrMsg, ExitCode.ERR)