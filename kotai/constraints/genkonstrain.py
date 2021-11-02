#!/usr/bin/env python3
# =========================================================================== #

from pathlib import Path
from typing import Literal

from kotai.types import runproc, CmdResult

# --------------------------------------------------------------------------- #

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

# --------------------------------------------------------------------------- #

class Konstrain:

    # ---------------------------- Static attrs. ---------------------------- #
    exe: dict[str, Path] = {
        'konstrain': Path('kotai/constraints/konstrain/target/'
                          'konstrain-1.0-SNAPSHOT-jar-with-dependencies.jar')
                          .resolve(),
    }

    timeout: float = 3.0

    # ---------------------------- Member attrs. ---------------------------- #

    __slots__ = (
        'descriptor',
        'ket',
        'ofile',
    )

    def __init__(self, descriptor: Path, ket: KonstrainExecType, ofile: Path,):
        self.descriptor: Path       = descriptor
        self.ket: KonstrainExecType = ket
        self.ofile: Path            = ofile

    def runcmd(self, *args: str) -> CmdResult:
        proc_args = [
            'java', '-jar', f'{Konstrain.exe["konstrain"]}',
            str(self.descriptor),
            str(self.ket),
        ] + [*args]
        return runproc(proc_args, Konstrain.timeout,
                       ofpath=self.ofile, breakLines=True)



# =========================================================================== #
