[![Codacy Badge](https://api.codacy.com/project/badge/Grade/c50c40979103401db073a3e0ef349596)](https://www.codacy.com/app/MaverickTse/pyMingwBuild?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=MaverickTse/pyMingwBuild&amp;utm_campaign=Badge_Grade)

# 【UNMAINTAINED】

# pyMingwBuild
Python(Anaconda) script to build Mingw-w64 cross-toolchain


## What it does
To build 32bit and 64bit non-multilib STATIC Mingw-w64 toolchain in a bash-like environment


## Features
- Automatically looks for latest component versions (Not Hard-Coded) if not specified
- Preferred version string, e.g. "7.1.0", for GCC, Binutils and Mingw-w64 can be set on commandline
- Choosable from SJLJ and DW2 exception handling for win32 build from commandline
- Working Folder(aka. Sandbox) can be set on commandline. Meaning this script can be placed anywhere
- Clean terminal output. ONLY in case of error, outputs are logged into files in components' build folder
- Only use FTP and HTTP downloads, no need of wget or git or svn
- multi-threaded download (2 by default)
- Skip decompression if downloaded tarball has the same MD5 checksum
- include pkgconf
- Automatic benchmark record
- Build-report generation (readme.txt)
- Helper script generation for PATH and CC manipulation (use32.sh, use64.sh, restore.sh)
- EASIER to comprehend and customize than a BASH Script


## Prerequisite
- Linux/ Win10 WSL
- [Anaconda Linux 64-bit with Python 3.6 or newer](https://www.continuum.io/downloads) or Python3.6+BeautifulSoup4
- [build-essential](https://packages.ubuntu.com/xenial/build-essential)
- [automake](https://packages.ubuntu.com/xenial/automake)
- [Texinfo](https://packages.ubuntu.com/xenial/texinfo)
- [yasm](https://packages.ubuntu.com/xenial/yasm)
- clang (optional. Tested with GCC 4.9+ and Clang 3.8)


## How to Use
Download this script to somewhere. The simplest use would be:

```bash
python3 tc-builder.py
```

This would download and build inside a new folder named ```~/MWTC```.

Downloaded TAR balls would be inside ```~/MWTC/dl```

(Delete the dl folder to force re-download)

Extracted archives would be inside ```~/MWTC/pkgs```

(If the archive's MD5 has not been changed, decompression is skipped)

Build trees inside ```~MWTC/build```

(Can be safely deleted. Automatically deleted on rebuild)

Actual toolchains inside ```~/MWTC/mingw-w64-i686``` and ```~/MWTC/mingw-w64-x86_64```

To change the sandbox to somewhere other than ```~/MWTC``` use:

```bash
python3 tc-builder.py --prefix="/your/sandbox"
```

To specify component versions, use:

```bash
python3 tc-builder.py --prefix="/your/sandbox" --gcc="6.4.0"
```

If the version string is not found on repo, the latest version would be used. (based on version string)

After the thing successfully built, you may:

```bash
cd ~/MWTC
source use64.sh
```

To start using the 64bit Mingw toolchain

Test compile with:

```bash
$CXX std=c++14 compiler-test.cpp -o /mnt/c/compiler-test64.exe
```

and run compiler-test64.exe from Windows. Check if multiple CPU cores have increased activity.

finally,

```bash
source restore.sh
```

to restore PATH when done

## Potential Issues
- Only tested on Ubuntu 16.04 and Win10 WSL(Creators Update)
- DO NOT USE Sandbox path with SPACE and CJK characters in it (not tested)
- Dirty Code (Yeah, refractoring welcome :blush: )
- gendef and widl are not being built in current version (anyone need these?)
- winpthreads is used as the default threading library (but C++ threading SHOULD works)
- slow on WSL (a problem of M$)


## Parameters
- ```--help``` print the help text
- ```--prefix="~/MWTC"``` set the sandbox folder
- ```--sjlj``` Force win32 to use sjlj exception handling
- ```--gcc="6.4.0"``` set the preferred GCC version. Use latest if not found
- ```--binutils="99"``` set the preferred Binutils version. Use latest if not found
- ```--mingw="99"``` set the preferred Mingw-w64 version. Use latest if not found

## Contribution Guideline
- Open up a new ISSUE prior MAJOR change!
- TEST your code, i.e. BUILD Mingw-w64, and only submit Pull Request when it works right
- Do not inculde python packages not bundled with Anaconda by default
- Syntax standard: Python 3.6
- Proper identation and newline. Avoid spaghetti code.
- Do not expect fame or return
