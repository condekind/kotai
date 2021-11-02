#!/usr/bin/env python3
# =========================================================================== #

import argparse
import logging
from pathlib import Path
from multiprocessing import Pool

from kotai.constraints.genkonstrain import Konstrain, KonstrainExecType, KonstrainExecTypes
from kotai.plugin.PrintDescriptors import PrintDescriptors
from kotai.plugin.Jotai import Jotai
from kotai.plugin.Clang import Clang
from kotai.plugin.CFGgrind import CFGgrind
from kotai.templates.benchmark import GenBenchTemplatePrefix
from kotai.types import ExitCode, FileWithFnName, SysExitCode, OptFlag, logret
from kotai.logconf import logFmt, sep

# --------------------------------------------------------------------------- #
'''
TODOs:
    - Add checks to avoid re-running intermediate steps (check if files exist)

    - Modify Jotai.cpp to generate the new switch-based main from the prototype

    - Find a way to prepend the orig. function with __attribute__((noinline))

    - Find out which CFGgrind call creates "vgcore.XXXXXX" (temp) files and
      remove these files when they're no longer needed (or create them
      somewhere else)

    - Change wrappers so they don't need to be instantiated inside the worker
      functions. Maybe remove individual file attributes and make their methods
      static, receiving these attrs as args?
'''
# --------------------------------------------------------------------------- #

class Application:

    def __init__(self, ) -> None:

        # Attribute type annotation
        self.clean: bool
        self.inputdir: list[str]
        self.nproc: int
        self.chunksize: int
        self.buildpath: str
        self.logfile: str
        self.ketList: list[KonstrainExecType]
        validkets = KonstrainExecTypes + ['all']

        self.args = argparse.Namespace()
        cli = argparse.ArgumentParser(
            prog='python -m kotai',
            description='Jotai options'
        )
        #cli.add_argument('-B', '--buildpath', default='./build')
        cli.add_argument('-c', '--clean', action='store_true', default=False)
        cli.add_argument('-i', '--inputdir', nargs='+', required=True)
        cli.add_argument('-j', '--nproc', type=int, default=6)
        cli.add_argument('-J', '--chunksize', type=int, default=-1)
        cli.add_argument('-K', choices=validkets, default='all')
        cli.add_argument('-L', '--logfile',   default='./output/jotai.log')
        cli.parse_args(namespace=self.args)

        # [-i]
        self.inputBenchmarks = [Path(p) for p in self.args.inputdir]

        # [-j]
        self.nproc = self.args.nproc if self.args.nproc > 1 else 1

        # [-J]
        self.chunksize = self.args.chunksize if self.args.chunksize > 1 else 1

        # [-K]
        if self.args.K not in KonstrainExecTypes:
            self.ketList = [ket for ket in KonstrainExecTypes]
        else:
            self.ketList = [self.args.K]

        # [-L] Creates logfile if it doesn't exist
        with open(self.args.logfile, 'w'): pass

        # Logging defaults
        logging.basicConfig(
            filename=self.args.logfile,
            filemode='w+',
            format=logFmt,
            level=logging.INFO
        )
        logging.debug(f'{self.args=}')


    def start(self, ) -> SysExitCode:
        return _start(self)  # Defined at the end of this file

# --------------------------------------------------------------------------- #


# Deletes the files generated by this program on a previous run
def _cleanFn(cFile: Path) -> ExitCode:
    cFileMetaDir = cFile.with_suffix('.d')
    genFiles = cFileMetaDir.glob('*')
    for file in genFiles:
        try: file.unlink(missing_ok=True)
        except Exception as e:
            logging.error(f'{e}: {file=}')
            continue
    try: cFileMetaDir.rmdir()
    except Exception as e: return logret(f'{e}: {cFileMetaDir=}').err
    return logret(f'Deleted {cFileMetaDir=}', level='info').err


# Called by _genDescriptor to save the fn name found in the benchmark.
# The name is important because we gather stats later with:
# cfggrind_info -f "benchBinPath::fnName" -s functions ...
def _getFnName(desc: str) -> ExitCode | str:
    tokens = [t for t in desc.split() if t]

    if 'no-params' in tokens:        return ExitCode.ERR
    if tokens.count('function') > 1: return ExitCode.ERR

    # The fn name is the token after the 'function' keyword
    # The -1 excludes the last token, to avoid IndexError when we +1
    try: fn = tokens[tokens.index('function', 0, -1) + 1]
    except Exception:                return ExitCode.ERR
    else:                            return fn


# Worker function mapped in a multiprocessing.Pool to run PrintDescriptors
def _genDescriptor(cFile: Path) -> ExitCode | FileWithFnName:

    printDescriptorsPlugin = PrintDescriptors(cFile)
    msg, err = printDescriptorsPlugin.runcmd()

    # If error: returns before creating the descriptor file
    if err == ExitCode.ERR:
        logging.error(f'PrintDescriptors error: {msg=}')
        return ExitCode.ERR

    fnName = _getFnName(msg)
    logging.debug(f'{fnName=}')
    if fnName == ExitCode.ERR:
        return ExitCode.ERR

    # Creates the output dir for the current cFile
    cFileMetaDir = cFile.with_suffix('.d')
    try: cFileMetaDir.mkdir(parents=True, exist_ok=True)
    except PermissionError as pe:
        logging.error(f'{pe}: could not create dir {cFileMetaDir=}')
        return ExitCode.ERR

    # Creates the descriptor
    descriptorPath = cFileMetaDir / 'descriptor'
    try: descFile = open(descriptorPath, 'w')
    except PermissionError as pe:
        logging.error(f'{pe}: could not create file {descriptorPath=}')
        return ExitCode.ERR
    else:
        with descFile:
            try: print(msg, file=descFile)
            except Exception as e:
                logging.error(f'{e}: could not write to {descFile=}')
                return ExitCode.ERR

    logging.info(f'{descriptorPath=} written:\n{msg}\n{sep}')
    assert(isinstance(fnName, str))
    return FileWithFnName(cFile, fnName)


# Worker function mapped in a multiprocessing.Pool to run Konstrain
def _runKonstrain(cFile:Path, ket: KonstrainExecType) -> ExitCode | Path:
    cFileMetaDir    = cFile.with_suffix('.d')
    descriptorPath  = cFileMetaDir / 'descriptor'
    constraintsPath = cFileMetaDir / f'constraint_{ket}'

    konstrain = Konstrain(descriptorPath, ket, constraintsPath)

    logging.info(f'Running konstrain on {cFile}')
    return cFile if konstrain.runcmd().err != ExitCode.ERR else ExitCode.ERR


def _runJotai(cFile: Path) -> ExitCode | Path:
    # genBenchFile buffer, starting with headers
    # buffer <- includes, defines, typedefs and runtime info placeholder
    genBuffer = GenBenchTemplatePrefix

    # buffer += original benchmark function
    try: cFile_RO = open(cFile, 'r', encoding='utf-8')
    except Exception as e: return logret(e).err
    with cFile_RO: genBuffer += cFile_RO.read() + f'\n\n\n{sep}\n\n'

    cFileMetaDir    = cFile.with_suffix('.d')
    descriptorPath  = cFileMetaDir / 'descriptor'
    constraintsPath = cFileMetaDir / f'constraint_big-arr'  # big-arr only
    jotai           = Jotai(constraintsPath, descriptorPath)
    logging.info(f'Running jotai with {constraintsPath=}, {descriptorPath=}')
    mainFn, err     = jotai.runcmd()

    # If error: returns before creating the descriptor file
    if err == ExitCode.ERR: return logret(f'Jotai error: {mainFn=}').err
    else: genBuffer += mainFn

    # Creates the genBench file and writes the buffer to it
    genBenchPath = cFileMetaDir / cFile.name  # big-arr only
    try: genBenchFile = open(genBenchPath, 'w')
    except Exception as e: return logret(e).err
    with genBenchFile:
        try: print(genBuffer, file=genBenchFile)
        except Exception as e: return logret(e).err

    return cFile


def _compileGenBench(cFile: Path) -> ExitCode | Path:
    cFileMetaDir = cFile.with_suffix('.d')
    optFlag      = 'O0'
    genBenchPath = cFileMetaDir / cFile.name
    genBinPath   = cFileMetaDir / f'{cFile.stem}_{optFlag}'

    # Compiles the genBench into a binary
    clang = Clang(optFlag=optFlag, ofile=genBinPath, ifile=genBenchPath)
    return cFile if clang.runcmd().err != ExitCode.ERR else ExitCode.ERR


def _runCFGgrind(cFile: Path, fnName: str) -> ExitCode:
    cFileMetaDir     = cFile.with_suffix('.d')
    optFlag: OptFlag = 'O0'
    genBinPath       = cFileMetaDir / f'{cFile.stem}_{optFlag}'

    # Compiles the genBench into a binary
    cfgg = CFGgrind(genBinPath, fnName)
    return cfgg.runcmd().err


def _start(self: Application, ) -> SysExitCode:

    # For each directory passed with -i/--inputdir, do:
    for benchDir in self.inputBenchmarks:

        ## TODO: Finish this optimization
        ## Get all .c files in that directory and exclude the ones that were
        ## already used to generate a descriptor in a previous run
        #dFiles  = list(benchDir.glob('*.d/descriptor'))
        #cFiles  =  [cf for cf
        #            in benchDir.glob('*.c')
        #            if cf.with_suffix('.d') / Path('descriptor') not in dFiles]
        #kcfiles =  {kf.parent.with_suffix('.c') for kf
        #            in benchDir.glob('*.d/constraint*')}
        #cFiles  =  [cf for cf in cFiles if cf not in kcfiles]

        cFiles = list(benchDir.glob('*.c'))

        if self.args.clean:
            with Pool(self.nproc) as pool:
                pool.map(_cleanFn, cFiles, self.chunksize)
                pool.close()
                pool.join()
            return ExitCode.OK

        with Pool(self.nproc) as pool:

            # benchDir/descriptor <- PrintDescriptors
            res = pool.map(_genDescriptor, cFiles, self.chunksize)

            cf_fn = [r for r in res if isinstance(r, FileWithFnName)
                                    and r.cf in cFiles]
            if not cf_fn:
                return 'No input for Konstrain'

            # benchDir/constraints <- Konstrain
            konsInput = [(r.cf, ty) for r in cf_fn for ty in self.ketList]
            resKons = pool.starmap(_runKonstrain, konsInput, self.chunksize)
            if all(ret == ExitCode.ERR for ret in resKons):
                return 'No input for Jotai'

            # benchDir/genBench.c <- Jotai
            jotaiInput = [cf for cf in resKons if isinstance(cf, Path)]
            resJotai = pool.map(_runJotai, jotaiInput, self.chunksize)
            if all(ret == ExitCode.ERR for ret in resJotai):
                return 'No input for clang'

            # benchDir/genBench <- clang
            clangInput = [cf for cf in resJotai if isinstance(cf, Path)]
            resClang = pool.map(_compileGenBench, clangInput, self.chunksize)
            if all(ret == ExitCode.ERR for ret in resClang):
                return 'No input for CFGgrind'

            cfgGrindInput = {cf: fn for (cf,fn) in cf_fn if cf in resClang}
            pool.starmap(_runCFGgrind, cfgGrindInput.items(), self.chunksize)

            pool.close()
            pool.join()

    return ExitCode.OK


def main() -> SysExitCode:
    app = Application()
    return app.start()


# --------------------------------------------------------------------------- #


if __name__ == '__main__':
    import sys
    res = main()
    sys.exit(0 if res == ExitCode.OK else res)

# =========================================================================== #