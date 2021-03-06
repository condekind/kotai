#!/usr/bin/env python3
# =========================================================================== #

from pathlib import Path

from kotai.kotypes import CmdResult, OptLevel, runproc

# --------------------------------------------------------------------------- #

class Clang():

    # ---------------------------- Static attrs. ---------------------------- #

    exe: dict[str, Path] = {
        'clang': Path('clang'),
    }

    timeout: float = 3.0

    OptLevels = ['0','1','2','3','fast','z','s',]

    # ---------------------------- Member attrs. ---------------------------- #

    __slots__ = (
        'optLevel',
        'ofile',
        'ifile',
    )

    # ----------------------------------------------------------------------- #
    def __init__(self, optLevel: OptLevel, ofile: Path, ifile: Path):
        self.optLevel: str = optLevel
        self.ofile: Path   = ofile
        self.ifile: Path   = ifile
    # ----------------------------------------------------------------------- #

    def runcmd(self) -> CmdResult:
        if self.optLevel == 'O0':
            proc_args = [
                f'{Clang.exe["clang"]}',
                '-g',
                '-ggdb',
                '-Xclang',
                '-disable-O0-optnone',
                f'-O0',
                '-std=c2x',
                '-Wall',
                '-fno-stack-protector',
                '-no-pie',
                '-o', f'{self.ofile}',
                f'{self.ifile}',
            ]
        else:
            proc_args = [
                f'{Clang.exe["clang"]}',
                '-g',
                '-ggdb',
                f'-{self.optLevel}',
                '-std=c2x',
                '-Wall',
                '-fno-stack-protector',
                '-no-pie',
                '-o', f'{self.ofile}',
                f'{self.ifile}',
            ]
        return runproc(proc_args, Clang.timeout)



# =========================================================================== #
