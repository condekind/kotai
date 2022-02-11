#!/usr/bin/env python
# coding: utf-8

# In[ ]:


# Standard libraries
import os
from pathlib import Path
from multiprocessing import Pool
from pprint import pprint

# External
import numpy as np
import scipy.stats as stats
import pandas as pd
import yaml
#from IPython.display import display

# Misc
lineSepThin  = ('# --------------------------------------------------------------------------- #')
lineSepThick = ('# =========================================================================== #')
#pd.options.display.float_format = '{:20,.2f}'.format

NDEBUG = False


# In[ ]:


# Path to the directory with the '.c' files and '.d' dirs
benchmarkDir = '../../seed_fns'

# Patterns to look for in desired files
patterns = {}

#case 0: int bounds
patterns['case0_O0'] = '*.d/*_O0_0.info'
patterns['case0_O1'] = '*.d/*_O1_0.info'
patterns['case0_Oz'] = '*.d/*_Oz_0.info'
patterns['case0_O2'] = '*.d/*_Oz_0.info'

#case 1: big arr
# patterns['case1_O0'] = '*.d/*_O0_1.info'
# patterns['case1_O1'] = '*.d/*_O1_1.info'
# patterns['case1_O2'] = '*.d/*_O2_1.info'
# patterns['case1_Oz'] = '*.d/*_Oz_1.info'

#case 2: big arr 10x
# patterns['case2_O0'] = '*.d/*_O0_2.info'
# patterns['case2_O1'] = '*.d/*_O1_2.info'
# patterns['case2_Oz'] = '*.d/*_Oz_2.info'

print(f'Globbing files from directory\n\n{benchmarkDir}\n\nwith group -> pattern:\n')
_ = [print(f'{group}    ->    {pat}') for group, pat in patterns.items()]


# In[ ]:


infoFilePaths = {group: list(Path(benchmarkDir).glob(pattern)) for group, pattern in patterns.items()}

for group, pattern in patterns.items():
    print(f'Group {group}:\t\tfound {len(infoFilePaths[group])} programs')


# In[ ]:


runInParallel = True  # Run in parallel?

# Number of cpu cores (remove the `// 2` to use all the cores)
nproc = len(os.sched_getaffinity(0)) // 2 if runInParallel else 1
print(f'Using {nproc} core(s)')

chunksize = 512
print(f'Each cpu core will work on chunks of {chunksize} tasks')


# In[ ]:


cnt = 0


# In[ ]:


def err(msg=None, val=None, *args):

    if NDEBUG:
        return val

    print(msg)
    for arg in args:
        print(arg)

    return val


# Loads .info files faster if you have parallel disk access
def parseInfo(infoFilePath):
    global cnt

    try:
        with open(infoFilePath, 'r') as infoFileHandle:
            try:
                info = yaml.safe_load(infoFileHandle)

            except Exception as e:
                return err(msg=f'Failed parsing {infoFilePath}: {e}')

            else:
                if not info:
                    cnt += 1
                    return err(f'Info evaluates to False: {infoFilePath}')
                
                return info[0]

    except Exception as e:
        return err(f'Failed parsing {infoFilePath}: {e}')


# Turns each key in the inner dicts ('static' and 'dynamic') into a key in
# the outer dict, e.g., accessing infoFile['static']['instructions'] becomes
# infoFile['static_instructions']. This also makes pandas happier.
def flattenCfgInfo(cfgInfo, desiredCols=None):
    
    try: fullName = cfgInfo['name']
    except Exception as e:
        return err(f'File without the field "name"! {e}\nContents:\n{cfgInfo}\n')

    try: res = {k: v for k, v in {
            'cfg': cfgInfo['cfg'],
            'invoked': cfgInfo['invoked'],
            'complete': cfgInfo['complete'],
            'blocks': cfgInfo['blocks'],
            'phantoms': cfgInfo['phantoms'],
            'exit': cfgInfo['exit'],
            'halt': cfgInfo['halt'],
            'edges': cfgInfo['edges'],
            'static_instructions': cfgInfo['static']['instructions'],
            'static_calls': cfgInfo['static']['calls'],
            'static_signals': cfgInfo['static']['signals'],
            'dynamic_instructions': cfgInfo['dynamic']['instructions'],
            'dynamic_calls': cfgInfo['dynamic']['calls'],
            'dynamic_signals': cfgInfo['dynamic']['signals'],
            'name': Path(Path(cfgInfo['name']).parent.name).with_suffix('.c'),
    }.items() if k in desiredCols}

    except Exception as e:
        return err(f'Function flattenCfgInfo(cfgInfo, desiredCols) failed for {fullName}: {e}')

    else:
        return res  # Success


# In[ ]:


desiredCols = ['name', 'static_instructions', 'dynamic_instructions']

print('The desired columns to be included in the dataframe are:')
pd.DataFrame([], columns=desiredCols).style.set_table_styles([dict(selector="th", props=[('font-size', '18px')])])


# In[ ]:


tmpdf = {}
infoGroups = {}
#with Pool(nproc) as pool:
for group, files in infoFilePaths.items():
    #res = pool.imap_unordered(parseInfo, files, chunksize)
    res = [parseInfo(f) for f in files]
    infoGroups[group] = [flattenCfgInfo(r, desiredCols) for r in res if r]
    tmpdf[group] = pd.DataFrame(infoGroups[group], columns=desiredCols)
#pool.close()
#pool.join()


# In[ ]:


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


# In[ ]:


# Make sure the path leading to the last prefix directory exists
outputPrefix = 'output/cfgInfo'

# Warning: [ , . ; : ] are all allowed characters for linux filenames
csvSeparator = ';'

for group in patterns.keys():
    try:
        df[group].to_csv(Path(outputPrefix + f'_{group}.csv'), sep=csvSeparator, encoding='utf-8')
    except Exception as e:
        print(f'{e}')


# In[ ]:


print(cnt)

# MUDAR DE ACORDO COM O NUM DE CONSTRAINTS UTILIZADOS
# ### Merge case 0 - int bounds

# In[ ]:


info0_O0 = pd.read_csv('output/cfgInfo_case0_O0.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
info0_O0.columns = ['filename','staticO0','dynamicO0']

info0_O1 = pd.read_csv('output/cfgInfo_case0_O1.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
info0_O1.columns = ['filename','staticO1','dynamicO1']

info0_Oz = pd.read_csv('output/cfgInfo_case0_Oz.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
info0_Oz.columns = ['filename','staticOz','dynamicOz']

info0_O2 = pd.read_csv('output/cfgInfo_case0_O2.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
info0_O2.columns = ['filename','staticO2','dynamicO2']

data_merge_case_0 = pd.merge(info0_O0, info0_O1, how = 'inner')
data_merge_case_0 = pd.merge(data_merge_case_0, info0_Oz, how = 'inner')
data_merge_case_0 = pd.merge(data_merge_case_0, info0_O2, how = 'inner')
data_merge_case_0.to_csv('output/CFGInfoStats_bigarr', index = False)


# ### Merge case 1 - big-arr

# In[ ]:


# info1_O0 = pd.read_csv('output/cfgInfo_case1_O0.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
# info1_O0.columns = ['filename','staticO0','dynamicO0']

# info1_O1 = pd.read_csv('output/cfgInfo_case1_O1.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
# info1_O1.columns = ['filename','staticO1','dynamicO1']

# info1_Oz = pd.read_csv('output/cfgInfo_case1_Oz.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
# info1_Oz.columns = ['filename','staticOz','dynamicOz']

# info1_O2 = pd.read_csv('output/cfgInfo_case1_O2.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
# info1_O2.columns = ['filename','staticO2','dynamicO2']

# data_merge_case_1 = pd.merge(info1_O0, info1_O1, how = 'inner')
# data_merge_case_1 = pd.merge(data_merge_case_1, info1_Oz, how = 'inner')
# data_merge_case_1.to_csv('output/CFGInfoStats_case_1-bigarr', index = False)


# ### Merge case 2 - big-arr-10x

# In[ ]:


# info2_O0 = pd.read_csv('output/cfgInfo_case2_O0.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
# info2_O0.columns = ['filename','staticO0','dynamicO0']

# info2_O1 = pd.read_csv('output/cfgInfo_case2_O1.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
# info2_O1.columns = ['filename','staticO1','dynamicO1']

# info2_Oz = pd.read_csv('output/cfgInfo_case2_Oz.csv', delimiter=';', usecols = ['name', 'static_instructions', 'dynamic_instructions'])
# info2_Oz.columns = ['filename','staticOz','dynamicOz']

# data_merge_case_2 = pd.merge(info2_O0, info2_O1, how = 'inner')
# data_merge_case_2 = pd.merge(data_merge_case_2, info2_Oz, how = 'inner')
# data_merge_case_2.to_csv('output/CFGInfoStats_case_2-bigarr10x', index = False)


# In[ ]:


# ## Todo: quote the field 'name' inside flattenCfgInfo
# # Whether to properly quote the 'name' field. Useful for working on shells.
# # WARNING: as the docs state:
# # '''
# #     The shlex module is only designed for Unix shells.
# # '''
# shellQuoteFileName = True
# if shellQuoteFileName: import shlex


# # In[ ]:


# Path(Path(filestr).parent().name).with_suffix('.c')


# # In[ ]:


# ff = df.Pandas(row in for row in df['case0_Oz'] if row not in df['case0_O1'])


# # In[ ]:


# print(df['case0_Oz'].iloc[0]['name'])
# print(len(df['case0_Oz'].merge(df['case0_O1'],indicator = True, how='outer').loc[lambda x : x['_merge']!='both']))


# # In[ ]:


# Path(Path(df['case0_Oz'].iloc[0]['name']).parent.name).with_suffix('.c').name


# # In[ ]:


# df['case0_Oz'].iloc[0]


# # In[ ]:


# Path(Path(jow['name']).parent.name).with_suffix('.c').name


# # In[ ]:





# # In[ ]:




