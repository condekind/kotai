#!/usr/bin/env python3
# =========================================================================== #

from pathlib import Path
from shutil import which

from kotai.kotypes import CmdResult, runproc, failure

# --------------------------------------------------------------------------- #

class CFGgrind:

    # ---------------------------- Static attrs. ---------------------------- #

    exe: dict[str, Path] = {
        'valgrind':        Path('valgrind'),
        'cfggrind_asmmap': Path('cfggrind_asmmap'),
        'cfggrind_info':   Path('cfggrind_info'),
    }

    timeout: float = 3.0

    # ---------------------------- Member attrs. ---------------------------- #

    __slots__ = (
        'binPath',
        'benchFn',
        'mapFilePath',
        'cfgOutFilePath',
        'cfggInfoOutPath',
    )

    # ----------------------------------------------------------------------- #
    def __init__(self, binPath: Path, benchFn: str):
        self.binPath = b if (b := which(binPath)) else ''
        self.benchFn = benchFn

        ''' path/to/benchName.d/benchName_optFlag.map '''
        self.mapFilePath: Path = Path(str(self.binPath) + '.map')

        ''' path/to/benchName.d/benchName_optFlag.cfg '''
        self.cfgOutFilePath: Path = Path(str(self.binPath) + '.cfg')

        ''' path/to/benchName.d/benchName_optFlag.map '''
        self.cfggInfoOutPath: Path = Path(str(self.binPath) + '.info')
    # ----------------------------------------------------------------------- #

    def _run_cfggrind_asmmap(self, timeout: float, *args: str) -> CmdResult:
        proc_args = [
            f'{CFGgrind.exe["cfggrind_asmmap"]}',
            f'{self.binPath}',
        ]
        #print(f'cfgg_asmmap: {proc_args}')
        return runproc(proc_args, timeout, ofpath=self.mapFilePath)


    def _run_valgrind_memcheck(self, timeout: float, *args: str) -> CmdResult:
        proc_args = [
            f'{CFGgrind.exe["valgrind"]}',
            '--tool=memcheck',
            '--error-exitcode=1',
            f'{self.binPath}',
        ] + [*args]  # e.g., switch-case 'idx'
        #print(f'valgrind: {proc_args}')
        return runproc(proc_args, timeout)


    def _run_valgrind(self, timeout: float, *args: str) -> CmdResult:
        self.cfgOutFilePath = Path(str(self.cfgOutFilePath).replace('.cfg', f'_{args[0]}.cfg', 1))
        proc_args = [
            f'{CFGgrind.exe["valgrind"]}',
            '--tool=cfggrind',
            f'--cfg-outfile={self.cfgOutFilePath}',
            f'--instrs-map={self.mapFilePath}',
            f'{self.binPath}',
        ] + [*args]  # e.g., switch-case 'idx'
        #print(f'valgrind: {proc_args}')
        return runproc(proc_args, timeout)


    def _run_cfggrind_info(self, timeout: float, *args: str) -> CmdResult:
        self.cfggInfoOutPath = Path(str(self.cfggInfoOutPath).replace('.info', f'_{args[0]}.info', 1))
        proc_args = [
            f'{CFGgrind.exe["cfggrind_info"]}',
            '-f', f'{Path(self.binPath).name}::{self.benchFn}',
            '-s', 'functions',
            '-m', 'json',
            f'{self.cfgOutFilePath}'
        ] 
        #print(f'cfgg_info: {proc_args}')
        return runproc(proc_args, timeout, ofpath=self.cfggInfoOutPath)


    def runcmd(self, *args: str) -> CmdResult:
        cfggMapRes = self._run_cfggrind_asmmap(CFGgrind.timeout, *args)
        if cfggMapRes.err == failure:
            return cfggMapRes

        valgrindMemcheckRes = self._run_valgrind_memcheck(CFGgrind.timeout, *args)
        if valgrindMemcheckRes.err == failure:
            return valgrindMemcheckRes

        valgrindRes = self._run_valgrind(CFGgrind.timeout, *args)
        if valgrindRes.err == failure:
            return valgrindRes

        return self._run_cfggrind_info(CFGgrind.timeout, *args)



# =========================================================================== #
