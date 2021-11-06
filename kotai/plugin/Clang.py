#!/usr/bin/env python3
# =========================================================================== #

from pathlib import Path
from typing import Literal

from kotai.types import CmdResult, runproc

OptFlag = Literal['O0','O1','O2','O3','Os','Oz']

# --------------------------------------------------------------------------- #

class Clang():

    # ---------------------------- Static attrs. ---------------------------- #

    exe: dict[str, Path] = {
        'clang': Path('clang'),
    }

    timeout: float = 3.0

    OptFlags = ['O0','O1','O2','O3','Ofast','Oz','Os',]

    # ---------------------------- Member attrs. ---------------------------- #

    __slots__ = (
        'optFlag',
        'ofile',
        'ifile',
    )

    # ----------------------------------------------------------------------- #
    def __init__(self, optFlag: str, ofile: Path, ifile: Path):
        self.optFlag: str = optFlag
        self.ofile: Path  = ofile
        self.ifile: Path  = ifile
    # ----------------------------------------------------------------------- #

    def runcmd(self, *args: str) -> CmdResult:
        proc_args = [
            f'{Clang.exe["clang"]}',
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
        ] + [*args]
        return runproc(proc_args, Clang.timeout)



# =========================================================================== #
