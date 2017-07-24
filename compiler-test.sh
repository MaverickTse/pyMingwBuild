#!/bin/sh
source ./MWTC/use32.sh
$CXX -std=c++14 compiler-test.cpp -o compiler-test32.exe
source ./MWTC/use64.sh
$CXX -std=c++14 compiler-test.cpp -o compiler-test64.exe
source ./MWTC/restore.sh
