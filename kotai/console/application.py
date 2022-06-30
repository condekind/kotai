#!/usr/bin/env python3
# =========================================================================== #

import argparse
import logging
import csv
from pathlib import Path
from multiprocessing import Pool
from typing import Any
from pprint import pprint


from kotai.constraints.genkonstrain import Konstrain
from kotai.benchInfo.GetBenchInfo import GetBenchInfo
from kotai.plugin.PrintDescriptors import PrintDescriptors
from kotai.plugin.Jotai import Jotai
from kotai.plugin.Clang import Clang
from kotai.plugin.CFGgrind import CFGgrind
from kotai.templates.benchmark import GenBenchTemplatePrefix, randGenerator, GenBenchTemplateMainBegin, GenBenchTemplateMainEnd, genSwitch, GenBenchSwitchBegin, GenBenchSwitchEnd, usage
from kotai.kotypes import BenchInfo, CaseBenchInfo, Failure, ExitCode, LogThen, OptLevel, OptLevels, SysExitCode, KonstrainExecType, KonstrainExecTypes, setLog, success, failure, valid
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

    # maxtasksperchild (passed to mp.Pool ctor)
    mtpc: int = 16

    def __init__(self, ) -> None:

        # Attribute type annotation
        self.clean: bool
        self.inputdir: list[str]
        self.nproc: int
        self.chunksize: int
        self.optLevels: list[OptLevel] = []
        self.ketList: list[KonstrainExecType] = []
        self.logfile: str
        self.ubstats: str

        self.args = argparse.Namespace()
        cli = argparse.ArgumentParser(
            prog='python -m kotai',
            description='Jotai options'
        )

        cli.add_argument('-c', '--clean',     action='store_true', default=False)
        cli.add_argument('--no-log',          action='store_true', default=False)
        cli.add_argument('-i', '--inputdir',  type=str, nargs='+', required=True)
        cli.add_argument('-j', '--nproc',     type=int, default=8)
        cli.add_argument('-J', '--chunksize', type=int, default=-1)
        cli.add_argument('-K',         type=str, nargs='+', choices=KonstrainExecTypes, default='all')
        cli.add_argument('--optLevel', type=str, nargs='+', choices=OptLevels,          default='O0')
        cli.add_argument('-L', '--logfile', default='./output/jotai.log')
        cli.add_argument('-u', '--ubstats', default='./output/ubstats.txt')
        cli.parse_args(namespace=self.args)

        # [-i]
        self.inputBenchmarks = [P for p in self.args.inputdir
                                  if (P := Path(p)).exists()]

        # [-j]
        self.nproc      = (self.args.nproc if self.args.nproc > 1
                           else 1)

        # [-J]
        self.chunksize  = (self.args.chunksize if self.args.chunksize > 1
                           else 64)

        # [-K]
        if 'all' in self.args.K:
            self.ketList = KonstrainExecTypes
        else:
            self.ketList = (kets if (kets := [ket for ket in self.args.K if ket in KonstrainExecTypes])
                              else ['all'])

        # [--optLevel]
        if 'all' in self.args.optLevel:
            self.optLevels = list(OptLevels)
        else:
            self.optLevels = (opts if (opts := [opt for opt in self.args.optLevel if opt in OptLevels])
                              else ['O0'])

        self.ubstats = self.args.ubstats

        if self.args.no_log:
            # [--no-log] Disable logging
            logger = logging.getLogger()
            logger.propagate = False
            logger.disabled = True
            setLog(False)
        else:
            # [-L] Logging defaults
            setLog(True)
            logging.basicConfig(
                filename=self.args.logfile,
                filemode='w+',
                format=logFmt,
                level=logging.DEBUG
            )
            logging.debug(f'{self.args=}')


    def start(self, ) -> SysExitCode:
        return _start(self)  # Defined at the end of this file

# --------------------------------------------------------------------------- #


# Deletes the files generated by this program on a previous run
def _cleanFn(pArgs: BenchInfo) -> ExitCode:
    cFileMetaDir = pArgs.cFilePath.with_suffix('.d')
    genFiles     = cFileMetaDir.glob('*')

    # For each file inside the bench.d folder
    for file in genFiles:

        # Delete it
        try: file.unlink(missing_ok=True)
        except Exception as e:
            logging.error(f'{e}: {file}')
            continue

    # Finally, delete the .d folder
    try: cFileMetaDir.rmdir()
    except Exception as e:
        return LogThen.Err(f'{e}: {cFileMetaDir}')

    return LogThen.Ok(f'Deleted {cFileMetaDir}')


def getFnName(descriptor: str) -> str | Failure:
    '''
    Called by _genDescriptor to retrieve the fn name found in the benchmark.
    The name is important because we gather stats later with:
    $ cfggrind_info -f "benchBinPath::fnName" -s functions ...
    '''

    tokens = [t for t in descriptor.split() if t]

    if 'no-params' in tokens:        return failure
    if tokens.count('function') > 1: return failure

    # The fn name is the token after the 'function' keyword
    # The -1 excludes the last token, to avoid IndexError when we +1
    try: fn = '' + tokens[tokens.index('function', 0, -1) + 1]
    except Exception:                return failure
    else:                            return fn


# Worker function mapped in a multiprocessing.Pool to run PrintDescriptors
def _genDescriptor(pArgs: BenchInfo) -> BenchInfo:

    cFilePath = pArgs.cFilePath

    msg, err = PrintDescriptors(cFilePath).runcmd()

    # If the PrintDescriptors plugin fails, return before creating the file
    if err == failure:
        return pArgs.Err('descriptor', f'PrintDescriptors [{cFilePath}]:"{msg=}"')

    # If the fnName isn't found, return before creating the file
    if (fnName := getFnName(msg)) == failure:
        return pArgs.Err('descriptor', f'{fnName=}')

    # Creates the output dir for the current cFile
    cFileMetaDir = cFilePath.with_suffix('.d')
    try: cFileMetaDir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return pArgs.Err('descriptor', f'{e}: PrintDescriptors [{cFileMetaDir}]')

    # Creates the descriptor file
    descriptorPath = cFileMetaDir / 'descriptor'
    try:
        with open(descriptorPath, 'w', encoding='utf-8') as descFile:
            descFile.write(msg)
    except Exception as e:
        return pArgs.Err('descriptor', f'{e}: PrintDescriptors [{descriptorPath}]')

    return BenchInfo(pArgs.cFilePath,
                     fnName=fnName,
                     ketList=pArgs.ketList,
                     optLevelList=pArgs.optLevelList,
                     exitCodes={'descriptor': success},
                     descriptor = msg)


# Worker function mapped in a multiprocessing.Pool to run Konstrain
def _runKonstrain(pArgs: BenchInfo) -> BenchInfo:
    cFilePath              = pArgs.cFilePath
    ketList: list[KonstrainExecType] = pArgs.ketList
    cFileMetaDir           = cFilePath.with_suffix('.d')
    descriptorPath         = cFileMetaDir / 'descriptor'

    exitCodes: dict[Any, ExitCode] = {}

    for ket in ketList:
        if ket != 'linked':

            msg, err = Konstrain(descriptorPath, ket, cFileMetaDir / f'constraint_{ket}').runcmd()

            if err == failure:
                exitCodes[ket] = failure
                logging.error(f'Konstrain {ket} [{cFilePath}]:"{msg=}"')
            else:
                exitCodes[ket] = success

    pArgs.setExitCodes(exitCodes)
    return pArgs

def _runLinkedList(pArgs: BenchInfo) -> BenchInfo:
    descriptor             = pArgs.descriptor
    cFilePath              = pArgs.cFilePath
    cFileMetaDir           = cFilePath.with_suffix('.d')

    exitCodes: dict[Any, ExitCode] = {}
    rec_structs = []
    func_rec_params = []
    func_params = []

    for line in descriptor.split('\n'):
        if 'function' in line and 'struct' in line:
            func_params = line.split('|')[1:]
            func_params = [x.strip() for x in func_params if 'struct' in x and '*' in x and '**' not in x]

        elif 'struct' in line:
            count_rec_struct_members = 0
            struct_params = line.split('|')
            struct_params = [x.strip() for x in struct_params]
            name = struct_params[0]
            for i in struct_params[1:]:
                if '*' in i and name in i and '**' not in i:
                    count_rec_struct_members+=1
            if(count_rec_struct_members):
                rec_structs += [(name,count_rec_struct_members)]

    for param in func_params:
        param_type = param.split(None, 1)[1]
        param_type = param_type.replace('*', "").strip()

        for rec_struct,count_rec_struct_members in rec_structs:
            if rec_struct == param_type:
                func_rec_params += [(param, count_rec_struct_members)]


    skel_list = [x for x in ['linked', 'dlinked', 'bintree'] if x in pArgs.ketList]
    if func_rec_params:
        for i in skel_list:
            
            const_string = {}
            const_string["linked"] = ""
            const_string["dlinked"] = ""
            const_string["bintree"] = ""

            for rec_param, count_rec_struct_members in func_rec_params:
                # print(count_rec_struct_members)
                if(i == "linked"):
                    const_string["linked"] += 'linked(' + rec_param.split(' ')[0] + ', 10000) , '
                elif(i == 'dlinked' and count_rec_struct_members == 2):
                    const_string["dlinked"] += 'dlinked(' + rec_param.split(' ')[0] + ', 10000) , '
                elif(i == 'bintree' and count_rec_struct_members == 2):
                    const_string["bintree"] += 'btree(' + rec_param.split(' ')[0] + ', 10) , '
            if const_string[i] != "":
                # print(const_string[i])
                const_string[i] = const_string[i][:-2]
            
                try:
                    with open(str(cFileMetaDir) + "/constraint_" + i, "w") as constraint_file:
                        try: 
                            constraint_file.write(const_string[i])
                            constraint_file.close()
                        except Exception as e:
                            return pArgs.Err(i, f'{e}')
                except Exception as e:
                    return pArgs.Err(i, f'{e}')

                exitCodes[i] = success
            else:
                exitCodes[i] = failure

    
    else:
        for i in skel_list:
            exitCodes[i] = failure

    pArgs.setExitCodes(exitCodes)
    return pArgs

# Worker function mapped in a multiprocessing.Pool to run Jotai
def _runJotai(pArgs: BenchInfo) -> BenchInfo:
    '''
    Creates genBenchFile: a main() entry point to the original benchmark.

    Individual sections of the result are added to a buffer, which is only
    stored to disk (genBenchFile) if every step was successful.

    The headers, defines and typedefs are added to the buffer, then Jotai is
    used to generate the mainFn body (as a string), which declares and
    initializes variables needed by the benchFn.
    '''

    cFilePath = pArgs.cFilePath

    # buffer <- includes, defines, typedefs and runtime info placeholder
    genBuffer = GenBenchTemplatePrefix
    genBuffer += randGenerator


    # buffer += original benchmark function
    try:
        with open(cFilePath, 'r', encoding='utf-8') as cFileHandle:
            pArgs.benchFunction = cFileHandle.read()
    except Exception as e:
        return pArgs.Err('Jotai', f'{e}')

    cFileMetaDir    = cFilePath.with_suffix('.d')
    descriptorPath  = cFileMetaDir / 'descriptor'

    jotaiSwitchCase = ''
    genSwitchList: list[tuple[int, KonstrainExecType, str, ExitCode, str]] = []
    usageCases: list[tuple[int, KonstrainExecType]] = []

    
    for idx, ket in enumerate(pArgs.ketList):
        if ket in pArgs.exitCodes and pArgs.exitCodes[ket] == failure:
            continue

        constraintsPath = cFileMetaDir / f'constraint_{ket}'

        # Jotai's result
        jotaiResult, err = Jotai(constraintsPath, descriptorPath).runcmd()
        print(cFilePath)
        # print(jotaiResult)
        print(err)
        print("\n\n\n")
        # If error: returns before creating the genbench file
        if err == failure:
            pArgs.setExitCodes({ket: failure})
            continue

        # If recursive, separate jotai results
        
        match jotaiResult.split('/*RV_DELIM*/'):
            case [recFunc, decl]:  
                recFunction = recFunc;
                jotaiSwitchCase = decl

            case [decl]:
                recFunction = ""
                jotaiSwitchCase = decl

        genSwitchList += [(idx, ket, jotaiSwitchCase, err, recFunction)]
        usageCases += [(idx, ket)]

    genBuffer += usage(usageCases)
    genBuffer += pArgs.benchFunction
    genBuffer += f'\n\n\n{sep}\n\n'


    if not genSwitchList:
        return pArgs.Err('Jotai', 'Jotai: Complete failure')

    switchCases = ""
    aux_functions = ""

    aux_function_set = set()
    for sw in genSwitchList:
        idx, ket, out, err, aux_func = sw
        if(aux_func not in aux_function_set):
            aux_function_set.add(aux_func)
            aux_functions += aux_func

        switchCases += genSwitch(idx, out, ket)
        if cFilePath in pArgs.benchCases:
            pArgs.benchCases[cFilePath][ket] = CaseBenchInfo(idx, out, aux_func)
        else:
            ket: KonstrainExecType
            cb = CaseBenchInfo(idx, out, aux_func)
            pArgs.benchCases |= {cFilePath: {ket: cb}}

    genBuffer += aux_functions
    genBuffer += GenBenchTemplateMainBegin
    genBuffer += GenBenchSwitchBegin
    genBuffer += switchCases

    genBuffer += GenBenchSwitchEnd
    genBuffer += GenBenchTemplateMainEnd

    # Creates the genBench file and writes the buffer to it
    genBenchPath = cFileMetaDir / f'{cFilePath.stem}.c'
    try:
        with open(genBenchPath, 'w', encoding='utf-8') as genBenchFile:
            try: 
                genBenchFile.write(genBuffer)
                genBenchFile.close()
            except Exception as e:
                return pArgs.Err('Jotai', f'{e}')
    except Exception as e:
        return pArgs.Err('Jotai', f'{e}')

    # pArgs.setExitCodes({'jotai': success})
    return pArgs

def _compileGenBenchFsanitize(pArgs: BenchInfo) -> BenchInfo:
    cFilePath    = pArgs.cFilePath
    optLevelList = pArgs.optLevelList
    cFileMetaDir = cFilePath.with_suffix('.d')
    genBenchPath = cFileMetaDir / f'{cFilePath.stem}.c'
    
    optResList: list[tuple[OptLevel, ExitCode]] = []
    for opt in optLevelList:
        genBinPath   = cFileMetaDir / f'{cFilePath.stem}_fsanitize_{opt}'
        # Compiles the genBench into a binary
        _, err = Clang(opt, ofile=genBinPath, ifile=genBenchPath).runcmdFsanitize()

        if err == failure:
            print(cFilePath)
            print("compile error")
            # print(err)
            print("\n\n")
            pArgs.setExitCodes({opt: failure})
            continue
        optResList += [(opt, err), ]

    if not optResList:
        return pArgs.Err('Clang', 'Clang: Fsanitize Complete failure')
    return pArgs

def _runWithFsanitize(pArgs: BenchInfo) -> BenchInfo:
    cFilePath              = pArgs.cFilePath
    ketList                = pArgs.ketList
    optLevelList           = pArgs.optLevelList
    cFileMetaDir           = cFilePath.with_suffix('.d')

    ''' Runs binary compiled with Fsanitize'''
    runResList: list[tuple[str, OptLevel, KonstrainExecType, ExitCode]] = []
    for opt in optLevelList:
        if opt in pArgs.exitCodes and pArgs.exitCodes[opt] == failure:
            continue

        #if opt in pArgs.exitCodes:
        genBinPath = cFileMetaDir / f'{cFilePath.stem}_fsanitize_{opt}'
        for ket in ketList:
            
            if ket in pArgs.exitCodes and pArgs.exitCodes[ket] == failure:
                continue
            result, err = CFGgrind(genBinPath, pArgs.fnName).runcmdFsanitize(str(pArgs.benchCases[cFilePath][ket].switchNum))
        
            if err == failure:
                print(ket, err)
                print("run error")
                print("\n\n")
                pArgs.setExitCodes({ket: failure})
                continue

            runResList += [(pArgs.fnName, opt, ket, err)]

    if not runResList:
        return pArgs.Err('Run', 'Run: Fsanitize Complete failure')
    return pArgs

def _compileGenBench(pArgs: BenchInfo) -> BenchInfo:
    cFilePath    = pArgs.cFilePath
    optLevelList = pArgs.optLevelList
    cFileMetaDir = cFilePath.with_suffix('.d')
    genBenchPath = cFileMetaDir / f'{cFilePath.stem}.c'
    
    optResList: list[tuple[OptLevel, ExitCode]] = []
    for opt in optLevelList:
        genBinPath   = cFileMetaDir / f'{cFilePath.stem}_{opt}'
        # Compiles the genBench into a binary
        _, err = Clang(opt, ofile=genBinPath, ifile=genBenchPath).runcmd()

        if err == failure:
            pArgs.setExitCodes({opt: failure})
            continue
        optResList += [(opt, err), ]

    if not optResList:
        return pArgs.Err('Clang', 'Clang: Complete failure')
    return pArgs


def _runCFGgrind(pArgs: BenchInfo) -> BenchInfo:
    cFilePath              = pArgs.cFilePath
    ketList                = pArgs.ketList
    optLevelList           = pArgs.optLevelList
    cFileMetaDir           = cFilePath.with_suffix('.d')

    caseStdout: dict[KonstrainExecType, str] = {}
    ''' Runs valgrind-memcheck, cfgg-asmmap, valgrind-cfgg and cfgg-info '''
    runResList: list[tuple[str, OptLevel, KonstrainExecType, ExitCode]] = []
    for opt in optLevelList:
        if opt in pArgs.exitCodes and pArgs.exitCodes[opt] == failure:
            continue

        #if opt in pArgs.exitCodes:
        genBinPath = cFileMetaDir / f'{cFilePath.stem}_{opt}'
        for ket in ketList:
            
            if ket in pArgs.exitCodes and pArgs.exitCodes[ket] == failure:
                continue

            result, err = CFGgrind(genBinPath, pArgs.fnName).runcmd(str(pArgs.benchCases[cFilePath][ket].switchNum), ket)
            if err == failure:
                print(result, err)
                pArgs.setExitCodes({ket: failure})
                #pArgs.setBenchCasesError(cFilePath, ket)
                continue

            result = result.rstrip()
            if ket not in caseStdout:
                # print only primitive types
                if result and '{{other_type}}' not in result:
                    caseStdout[ket+opt] = result
            

            runResList += [(pArgs.fnName, opt, ket, err)]

    if not runResList:
        return pArgs.Err('Run', 'Run: Complete failure')
    pArgs.setCaseStdout(caseStdout)
    return pArgs

def _createFinalBench(pArgs: BenchInfo) -> BenchInfo:


    cFilePath = pArgs.cFilePath
    cFileMetaDir    = cFilePath.with_suffix('.d')
    # decl vars
    #parse(self.descriptor())
    #newCaseNumber = 0
    switchBuffer = ""
    aux_function = ""
    usageCases: list[tuple[int, KonstrainExecType]] = []

    switch_count = 0
    aux_function_set = set()
    for ket in pArgs.ketList:
        if ket in pArgs.exitCodes and pArgs.exitCodes[ket] == failure:
            print (f'[error]: ({cFilePath.name=}) {ket=}\n')
            continue

        pArgs.benchCases[cFilePath][ket].switchNum = switch_count
        usageCases += [(switch_count , ket)]
        print (f'[success]: ({cFilePath.name=}) {ket=}\n')
        
        if(pArgs.benchCases[cFilePath][ket].auxFunction not in aux_function_set):
            aux_function_set.add(pArgs.benchCases[cFilePath][ket].auxFunction)
            aux_function += pArgs.benchCases[cFilePath][ket].auxFunction

        switchBuffer += genSwitch(pArgs.benchCases[cFilePath][ket].switchNum , pArgs.benchCases[cFilePath][ket].content, ket)
        switch_count += 1

    genBuffer = GenBenchTemplatePrefix
    genBuffer += randGenerator
    genBuffer += usage(usageCases)
    genBuffer += pArgs.benchFunction
    genBuffer += f'\n\n\n{sep}\n\n'
    genBuffer += aux_function
    genBuffer += f'\n\n\n{sep}\n\n'
    genBuffer += GenBenchTemplateMainBegin
    genBuffer += GenBenchSwitchBegin
    genBuffer += switchBuffer
    genBuffer += GenBenchSwitchEnd
    genBuffer += GenBenchTemplateMainEnd

    # Creates the genBench file and writes the buffer to it
    genBenchPath = cFileMetaDir / f'{cFilePath.stem}_Final.c'
    try:
        with open(genBenchPath, 'w', encoding='utf-8') as genBenchFile:
            try: genBenchFile.write(genBuffer)
            except Exception as e:
                return pArgs.Err('JotaiFinal', f'{e}')
    except Exception as e:
        return pArgs.Err('JotaiFinal', f'{e}')
    print("worked \n")
    return pArgs


def _start(self: Application, ) -> SysExitCode:

    #For each directory passed with -i/--inputdir, do:
    for benchDir in self.inputBenchmarks:

        #self.optLevelList
        pArgs = [BenchInfo(cf, ketList=self.ketList, optLevelList=self.optLevels) for cf in benchDir.glob('*.c')]

        # [-c] Deletes 
        if self.args.clean:
            with Pool(self.nproc) as pool:
                pool.imap_unordered(_cleanFn, pArgs, len(pArgs) // self.nproc // 2 + 1)
                pool.close()
                pool.join()
            return success


        with Pool(self.nproc, maxtasksperchild=self.mtpc) as pool:

            # benchDir/descriptor <- PrintDescriptors
            resGenDesc = [r for r in pool.imap_unordered(_genDescriptor, pArgs, self.chunksize) if valid(r)]
            if not resGenDesc:
                return '[PrintDescriptors] No descriptors were generated'

            # benchDir/constraints <- Konstrain
            resKons = [r for r in pool.imap_unordered(_runKonstrain, resGenDesc, self.chunksize) if valid(r)]
            if not resKons:
                return '[Konstrain] No constraints were generated'

            if('linked' in self.ketList or 'dlinked' in self.ketList or 'bintree' in self.ketList):
                resLinked = [r for r in pool.imap_unordered(_runLinkedList, resKons, self.chunksize) if valid(r)]
            else:
                resLinked = resKons

            # benchDir/genBench.c <- Jotai          
            resJotai = [r for r in pool.imap_unordered(_runJotai, resLinked, self.chunksize) if valid(r)]
            #print(resJotai)
            if not resJotai:
                print( '[Jotai] No benchmarks with entry points were generated')

            clangInput = resJotai

            # # # benchDir/genBench <- clang

            resClangFsanitize = [r for r in pool.imap_unordered(_compileGenBenchFsanitize, clangInput, self.chunksize) if valid(r)]
            if not resClangFsanitize:
                return '[Clang] No benchmarks with entry points compiled successfully with Fsanitize' 

            resFsanitize = [r for r in pool.imap_unordered(_runWithFsanitize, resClangFsanitize, self.chunksize) if valid(r)]
            if not resFsanitize:
                print('fsanitize')
                return '[runFsanitize] No binary executed successfully'

            resClang = [r for r in pool.imap_unordered(_compileGenBench, resFsanitize, self.chunksize) if valid(r)]

            if not resClang:
                return '[Clang] No benchmarks with entry points compiled successfully'

            resValgrind = [r for r in pool.imap_unordered(_runCFGgrind, resClang, self.chunksize) if valid(r)]
            if not resValgrind:
                print('valgrind')
                return '[Valgrind/CFGgrind] No binary executed successfully'

            #printable return val to file
            with open('output/caseStdout.csv', 'w', encoding='utf-8') as caseStdoutFile:
                nameAndCases = ['filename'] + [ket+opt for ket in self.ketList for opt in self.optLevels]
                caseWriter = csv.DictWriter(caseStdoutFile, fieldnames=nameAndCases)
                records = []
                for r in resValgrind:
                    records += [{
                        'filename': str(r.cFilePath)
                    } | {
                        ket+opt:
                        r.caseStdout[ket+opt] if ket+opt in r.caseStdout else 'NA'
                        for ket in self.ketList for opt in self.optLevels
                    }]

                caseWriter.writeheader()
                caseWriter.writerows(records)

            print(sep)
            print('resValgrind:')
            pprint(resValgrind)
            print(sep)
            
            resFinal = [r for r in pool.imap_unordered(_createFinalBench, resValgrind, self.chunksize) if valid(r)]
            caseNumbers = []

            with open('output/switchCases.csv', 'w', encoding='utf-8') as switchCaseFile:
                sCases = ['filename'] + [ket for ket in self.ketList]
                sCaseWriter = csv.DictWriter(switchCaseFile, fieldnames=sCases)
                for r in resFinal:
                    caseNumbers += [{
                    'filename' : str(r.cFilePath)
                        } | { ket: r.benchCases[r.cFilePath][ket].switchNum if r.exitCodes[ket] != failure else 'NA'
                        for ket in self.ketList
                    }]
                sCaseWriter.writeheader()
                sCaseWriter.writerows(caseNumbers)


            if not resFinal:
                return '[Final benchmark] No file created'

            print(len(resFinal))

            pool.close()
            pool.join()


    GetBenchInfo(self.args.inputdir, self.optLevels, self.ketList).runcmd()
    return success


def main() -> SysExitCode:
    return Application().start()



# =========================================================================== #
