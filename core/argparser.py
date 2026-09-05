"""
This module processes the command line arguments passed to the trappy scopes CLI.

Options: <script1> <script2> <script3> : Positional, run in sequence.
         <script1> <script1> <script1> : Positional, run three times.
         -itr 3 <script1>              : Itterate three times.
         
         --login <user>                : Login to the terminal
         --experiment <exp-name>       :  Load experiment
"""

import argparse
#from rich import print

from core.permaconfig.sharing import Share
import os
import sys

parser = argparse.ArgumentParser(description='Trappy-Scopes Control Layer', 
                                 prog="Trappy-Scopes scope-cli")


### --- script parsing ----------------
parser.add_argument('scriptlist_', metavar='<script>', type=str,
                    action="append", nargs='?', 
                    help='List of scripts to execute in sequence')

parser.add_argument('-itr', '--iterate', metavar=('N', '<script>'), dest='scriptlist_', 
                    action='append', nargs=2, 
                    help='Specify the number of iterations to perform for a given script.')
### ------------------------------------

### --- login --------------------------
parser.add_argument('-su', '--setuser', dest='user', default=["ghost"], action='store',
                    nargs=1, help='Login/Set user for the microscope.',  type=str,
                    metavar='<user-initials>') 
parser.add_argument('--login', dest='user', default=["ghost"], action='store', type=str,
                    nargs=1, help='Login/Set user for the microscope.',
                    metavar='<user-initials>')
### ------------------------------------

### --- experiment ---------------------
parser.add_argument('-exp', '--experiment', dest='expname', default=None, action='store',
                    nargs=1, help='Set the experiment.', metavar='<exp-name>')
### ------------------------------------

## ---- enter-experiment prompt --------
parser.add_argument('-noep', '--noep', dest='noep', default=False, action='store_true',
                    help='Skip prompt to select experiment')
### ------------------------------------

### --- supres-fluff -------------------
parser.add_argument('-noff', '--nofluff', dest='nofluff', default=False, action='store_true',
                    help='Supress all the fluff during startup.')

### ------------------------------------

### --- intro --------------------------
parser.add_argument('--intro', dest='intro', default=False, action='store_true',
                    help='Print the scope CLI introduction document.')
### ------------------------------------

### --- launcher menu ------------------
parser.add_argument('--launcher', dest='launcher', default=False, action='store_true',
                    help='Open the animated menu instead of booting straight through.')
### ------------------------------------


### --- MP4 converter ------------------
parser.add_argument('-mp4', '--mp4', metavar=('<exp-name>'), dest='tomp4_exp', 
                    action='store', nargs=1, type=str, 
                    help='Convert all the .h264 videos in the experiment folder to .mp4 videos.')

parser.add_argument('-fps', '--fps', metavar='<fps>', dest='fps', 
                    action='store', nargs=1, type=int, default=30, 
                    help='Specify the fps for conversion to mp4.')
### ------------------------------------


### --- Trappy-Scopes installation -----
parser.add_argument('-install', '--install', dest='install', 
                    action='store_true',
                    help='Do installation of all required python and Unix libraries required for trappyscopes.')
### ------------------------------------



### --- Count lines of code in the project -----
parser.add_argument('-loc', '--loc', dest='loc', 
                    action='store_true',
                    help='Count lines of code for this project.')
### -------------------------------------------



### --- Generate a unique identifier ----------
parser.add_argument('-uid', '--uid', dest='uid', 
                    action='store_true',
                    help='Generate a trappy-scopes (systems) unique identifier.')
### -------------------------------------------

### --- Create a registry entry for the uid and  ----------
parser.add_argument('-k', '--kind', dest='kind', 
                    action='store', type=str, default=None,
                    help='Additionally adds the uid to the registry. Also specify the --tag \
                    parameter to add comments.')

parser.add_argument('-t', '--tag', dest='tag', 
                    action='store',
                    help='Additional comment for the uid registry.')

parser.add_argument('-reg', '--registry', dest='registry', 
                    action='store_true',
                    help='Show the current Trappy-Scopes objects registry.')
### -------------------------------------------


### Parse !!!!!!!!!!!!!!!
print("Passed arguements:", sys.argv)
args = parser.parse_args()


### ---- Process Scriptlist -----------------
scriptlist = []
for script in args.scriptlist_:
    if not isinstance(script, list):
        scriptlist.append(script)
    else:
        scriptlist += [script[1]]*int(script[0])
if None in scriptlist:
    scriptlist.remove(None)
if len(scriptlist) > 0:
    print("Scripts that will be loaded: ")
    print(scriptlist)
####### --------------------------------------


## `core` must not import upwards into `expframework`, so the scriptlist is
## only recorded here. The experiment environment recipe picks it up and hands
## it to the ScriptEngine.
Share.argparse["scriptlist"] = scriptlist

Share.argparse["user"] = args.user[0]
Share.argparse["expname"] = args.expname
Share.argparse["noep"] = (args.noep or (len(scriptlist) > 0))
Share.argparse["nofluff"] = args.nofluff
Share.argparse["launcher"] = args.launcher

if args.intro:
    from utilities.fluff import intro
    intro()
    exit(0)

if args.tomp4_exp:
    from utilities.mp4box import MP4Box
    args.tomp4_exp = args.tomp4_exp[0]
    args.tomp4_exp = os.path.join(Share.expdir, args.tomp4_exp)
    if os.path.exists(args.tomp4_exp):
        args.fps = list([args.fps])[0]
        print(f"Appending all converted files to {args.tomp4_exp + '/processed'} .\nFPS set at: {args.fps}")
        MP4Box.convert_all(args.tomp4_exp, fps=args.fps, prompt=False)
    else:
        print(f"[red]Given experiment doesn't exist:[default] {args.tomp4_exp}")
    exit()

if args.install:
    from core.installer.installer import Installer
    Installer.do_all()
    exit(0)

if args.loc:
    os.system("git ls-files | xargs wc -l ")
    exit(0)

if args.uid:
    from core.uid import uid
    from rich import print
    uid_ = uid()
    print(f"Unique identifier: {uid_}")
    
    if args.kind:
        from core.bookkeeping.registry import Registry
        Registry(uid_, args.kind, tag=args.tag)
    exit()

if args.registry:
    from core.bookkeeping.registry import ShowRegistry
    ShowRegistry()
    exit(0)



