#!/usr/bin/env python3
# =========================================================================== #

import subprocess as sp
from subprocess import PIPE
from dataclasses import dataclass
from pathlib import Path

from kotai.types import ExitCode, CmdResult, cmdresult, Timeout

# --------------------------------------------------------------------------- #

@dataclass
class CFGgrind:

    cFile: Path
    benchFn: str
    # binPath:        Path  # {bench}_{optFlag}
    # mapFilePath:    Path  # {bench}_{optFlag}.map
    # cfgOutFilePath: Path  # {bench}_{optFlag}_case-{idx}.cfg
    optFlag: str    = 'O0'
    valgrind        = Path('valgrind')
    cfggrind_asmmap = Path('cfggrind_asmmap')
    cfggrind_info   = Path('cfggrind_info')


    def __post_init__(self, ):

        ''' benchName '''
        self.bench = self.cFile.stem

        ''' path/to/benchName.d '''
        self.cFileMetaDir = self.cFile.with_suffix('.d')

        ''' path/to/benchName.d/benchName_optFlag '''
        self.binPath = self.cFileMetaDir / (self.bench + f'_{self.optFlag}')

        ''' path/to/benchName.d/benchName_optFlag.map '''
        self.mapFilePath = Path(str(self.binPath) + '.map')

        ''' path/to/benchName.d/benchName_optFlag.cfg '''
        self.cfgOutFilePath = Path(str(self.binPath) + '.cfg')

    def _run_cfggrind_asmmap(self,) -> CmdResult:
        proc_args = Timeout['cfggrind_asmmap'] + [
            'cfggrind_asmmap',
            f'{self.binPath}',
        ]
        res, err = cmdresult(self, sp.run(proc_args, stdout=PIPE, stderr=PIPE))
        if err == ExitCode.OK:
            with open(self.mapFilePath, 'w') as mapFileHandle:
                mapFileHandle.write(res)
            return (res, err)
        return ('', err)

    def _run_valgrind_with_cfggrind(self, *args: str) -> CmdResult:
        proc_args = Timeout['valgrind_with_cfggrind'] + [
            f'{self.valgrind}',
            '--tool=cfggrind',
            f'--cfg-outfile={self.cfgOutFilePath}',
            f'--instrs-map={self.mapFilePath}',
            f'./{self.binPath}',
        ] + [*args]  # 'idx'
        return cmdresult(self, sp.run(proc_args, stdout=PIPE, stderr=PIPE))


    def _run_cfggrind_info(self,) -> CmdResult:
        proc_args = Timeout['cfggrind_info'] + [
            'cfggrind_info',
            '-f', f'{self.binPath.name}::{self.benchFn}',
            '-s', 'functions',
            '-m', 'json',
            f'{self.cfgOutFilePath}'
        ]
        return cmdresult(self, sp.run(proc_args, stdout=PIPE, stderr=PIPE))


    def runcmd(self) -> CmdResult:
        cfggMapRes , err = self._run_cfggrind_asmmap()
        if err != ExitCode.OK:
            return (cfggMapRes, err)

        valgrindRes, err = self._run_valgrind_with_cfggrind()
        if err != ExitCode.OK:
            return (valgrindRes, err)

        cfggInfoRes, err = self._run_cfggrind_info()
        if err != ExitCode.OK:
            return (cfggInfoRes, err)

        return ('Success', ExitCode.OK)