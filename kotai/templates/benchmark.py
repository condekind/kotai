
from kotai.logconf import sep, src_sep

indent = '    '

runtimeInfoPlaceholder = '// [JOTAI-RUNTIME-INFO] //'

GenBenchTemplatePrefix: str = (f'''{src_sep}\n'''
'''
// includes
#include "stdio.h"
#include "stdlib.h"
#include "time.h"
#include "string.h"
#include "limits.h"
#include "float.h"

''')

def usage(numCases:int):
    return ('''
// Usage menu
int usage() {
    fprintf(stderr, "Usage:\\n\\
    prog [OPTIONS] [ARGS]\\n\\
    \\nARGS:\\n\\
    case_number         integer: 0 <= n <= ''' f'''{numCases}''' ''' \\n\\
    \\nOPTIONS:\\n\\
    -t                  (NOT IMPLEMENTED YET) enable time measurement\\n\\n\\
    return);
}\n\n'''

f'''{sep}\n\n'''
)

GenBenchTemplateMainBegin: str = (
    'int main(int argc, char *argv[]) {\n\n'
)

GenBenchTemplateMainEnd: str = (
    f'\n{indent}return 0;\n'
    '}\n'
)

GenBenchSwitchBegin: str = (
    f'{indent}int opt = atoi(argv[1]);\n'
    f'{indent}switch(opt) ''{\n\n'
)
GenBenchSwitchEnd: str = (
    f'{indent}''}\n'
)

def genSwitch(idx: int, out: str, ketDesc: str = '') -> str:
    return (
        f"""{f'{indent}// {ketDesc}' if ketDesc else ''}\n"""
        f'{indent}case {idx}:\n'
        f'{indent}''{\n'
        f'{indent*2}{out}\n'
        f'{indent*2}break;\n'
        f'{indent}''}\n'
    )
