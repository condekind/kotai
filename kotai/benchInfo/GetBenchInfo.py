#!/usr/bin/env python3
# =========================================================================== #

import pandas as pd
import os

from pathlib import Path
from kotai.kotypes import OptLevel, KonstrainExecType
from multiprocessing import Pool

from functools import reduce
from pprint import pprint
import numpy as np
import scipy.stats as stats
import yaml
# Misc
lineSepThin  = ('# --------------------------------------------------------------------------- #')
lineSepThick = ('# =========================================================================== #')
pd.options.display.float_format = '{:20,.2f}'.format
NDEBUG = False

def remove_prefix(self: str, prefix: str, /) -> str:
    if self.startswith(prefix):
        return self[len(prefix):]
    else:
        return self[:]
# =========================================================================== #

class GetBenchInfo():

	# ---------------------------- Member attrs. ---------------------------- #

	__slots__ = (
		'inputDir',
		'optLevelList',
		'ketList',
	)

	# ----------------------------------------------------------------------- #
	def __init__(self, inputDir: str, optLevelList: list[OptLevel], ketList: list[KonstrainExecType]):
	    self.inputDir: str = inputDir
	    self.optLevelList: list[OptLevel] = optLevelList
	    self.ketList: list[KonstrainExecType] = ketList

	# ----------------------------------------------------------------------- #

	def err(self, msg=None, val=None, *args):

		if NDEBUG:
			return val

		print(msg)
		for arg in args:
			print(arg)

		return val


	# Loads .info files faster if you have parallel disk access
	def parseInfo(self, infoFilePath):

		try:
			with open(infoFilePath, 'r') as infoFileHandle:
				try:
					info = yaml.safe_load(infoFileHandle)

				except Exception as e:
					return self.err(msg=f'Failed parsing {infoFilePath}: {e}')

				else:
					if not info:
						return self.err(f'Info evaluates to False: {infoFilePath}')
					return info[0]

		except Exception as e:
			return self.err(f'Failed parsing {infoFilePath}: {e}')


	# Turns each key in the inner dicts ('static' and 'dynamic') into a key in
	# the outer dict, e.g., accessing infoFile['static']['instructions'] becomes
	# infoFile['static_instructions']. This also makes pandas happier.
	def flattenCfgInfo(self, cfgInfo, desiredCols=None, group=None):


		try: fullName = cfgInfo['name']
		except Exception as e:
			return self.err(f'File without the field "name"! {e}\nContents:\n{cfgInfo}\n')

		try: res = {k: v for k, v in {
				'cfg': cfgInfo['cfg'],
				'invoked': cfgInfo['invoked'],
				'complete': cfgInfo['complete'],
				'blocks': cfgInfo['blocks'],
				'phantoms': cfgInfo['phantoms'],
				'exit': cfgInfo['exit'],
				'halt': cfgInfo['halt'],
				'edges': cfgInfo['edges'],
				'static_instructions' + '_' + group : cfgInfo['static']['instructions'],
				'static_calls': cfgInfo['static']['calls'],
				'static_signals': cfgInfo['static']['signals'],
				'dynamic_instructions' + '_' + group : cfgInfo['dynamic']['instructions'],
				'dynamic_calls': cfgInfo['dynamic']['calls'],
				'dynamic_signals': cfgInfo['dynamic']['signals'],
				'name': Path(Path(cfgInfo['name']).parent.name).with_suffix('.c'),
		}.items() if k in desiredCols}

		except Exception as e:
			return self.err(f'Function flattenCfgInfo(cfgInfo, desiredCols) failed for {fullName}: {e}')
		else:
			return res  # Success

	def runcmd(self):

		# Make sure the path leading to the last prefix directory exists
		outputPrefix = '/home/cissakind/repos/kotai/util/output/'

		patterns = {}

		for o in self.optLevelList:
			for k in self.ketList:
				patterns['case_'+ k + '_' + o] = '*.d/*_' + o + '_' + k + '.info'

		print(f'Globbing files from directory\n\n{self.inputDir}\n\nwith group -> pattern:\n')
		_ = [print(f'{group}    ->    {pat}') for group, pat in patterns.items()]

		infoFilePaths = {group: list(Path(self.inputDir[0]).glob(pattern)) for group, pattern in patterns.items()}
		for group, pattern in patterns.items():
			print(f'Group {group}:\t\tfound {len(infoFilePaths[group])} programs')

		runInParallel = True  # Run in parallel?

		# Number of cpu cores (remove the `// 2` to use all the cores)
		nproc = len(os.sched_getaffinity(0)) // 2 if runInParallel else 1
		print(f'Using {nproc} core(s)')

		chunksize = 512
		print(f'Each cpu core will work on chunks of {chunksize} tasks')

		tmpdf = {}
		infoGroups = {}

		#with Pool(nproc) as pool:
		for group, files in infoFilePaths.items():

			desiredCols = ['name', 'static_instructions_' + group, 'dynamic_instructions_' + group]
			res = [self.parseInfo(f) for f in files]
			infoGroups[group] = [self.flattenCfgInfo(r, desiredCols, group) for r in res if r]

			print(infoGroups[group])
			print('\n\n')
			tmpdf[group] = pd.DataFrame(infoGroups[group], columns=desiredCols)

			print()
			print(lineSepThick)


			df = {}
			for group, infoFiles in infoGroups.items():
				df[group] = tmpdf[group].set_index(['name'], verify_integrity=True)
				if not len(df[group]): continue
				print(f'\n{" "*((80-len(group))//2)}{group}:')
				#display(df[group].head(5))
				print()
				print(df[group].dtypes)
				print()
				print(df[group].describe(include='all'))
				print()
				print(lineSepThin)

				# Warning: [ , . ; : ] are all allowed characters for linux filenames
				csvSeparator = ','
				for group in patterns.keys():
					try:
						df[group].to_csv(Path(outputPrefix + f'CFGInfo_{group}.csv'), sep=csvSeparator, encoding='utf-8')
					except Exception as e:
						print(f'{e}')

		caseStdoutFile = pd.read_csv('/home/cissakind/repos/kotai/output/caseStdout.csv', sep=',')
		caseStdoutFile = caseStdoutFile.rename(columns={'filename': 'name'})

		#remove / if input folder ends with /
		caseStdoutFile['name'] = caseStdoutFile['name'].map(lambda a: remove_prefix(a, self.inputDir[0]+ '/'))

		print(self.inputDir[0])
		for k in self.ketList:
			file = []
			caseStdoutCols = []
			
			for o in self.optLevelList:
				file = file + [pd.read_csv(outputPrefix + f'CFGInfo_case_{k}_{o}.csv', sep=',')]
				caseStdoutCols = caseStdoutCols + [k + o]
			
			all_stats_case = reduce(lambda left,right: pd.merge(left,right,on=['name'],how='inner'), file)
			all_stats_case.to_csv(outputPrefix + 'CFG_allOpt_' + str(k) + '.csv',index = False)

			print(all_stats_case)
			print(caseStdoutFile)
			stats_and_output = pd.merge(all_stats_case, caseStdoutFile[['name'] + caseStdoutCols], how='inner')
			stats_and_output.to_csv(outputPrefix + 'retVal_and_CFGstats' + str(k),index = False)

			print(k + " : " + str(len(stats_and_output)))
	# =========================================================================== #