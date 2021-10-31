
from kotai.logconf import sep, src_sep

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

// macros
// #define etc...

// typedefs
//typedef int bool;

// Usage menu
int usage() {
    fprintf(stderr, "Usage:\\n\\
    prog [OPTIONS] [ARGS]\\n\\
\\nARGS:\\n\\
    case_number         integer: 1 <= n <= 8\\n\\
\\nOPTIONS:\\n\\
    -t                  (NOT IMPLEMENTED YET) enable time measurement\\n\\n\\
");
    return 1;
}
''' f'''
{sep}
{runtimeInfoPlaceholder}\n\n
''')