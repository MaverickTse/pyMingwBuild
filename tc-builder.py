"""
Python(Anaconda) script for building Mingw-w64 cross-toolchain
Copyrighted 2017 Maverick Tse YM, Hong Kong
Twitter: @MaverickTse

This script attempts to build Mingw-w64 toolchain with reference
to Zeranoe's build script. This script only works under bash-like
shell and requires Anaconda with Python 3.6 or newer. DO NOT USE Python
from Ubuntu/Debian official/personal repo!

Besides Anaconda, you will also need:
build-essential, automake, texinfo, yasm
for standard build facilities

Unlike Zeranoe's build script, wget, git, subversion, etc. are not needed
since this script only utilize FTP and HTTP through Python's built-in
networking functions.

Download is parallelized with 2 threads by default.

The building is complicated with some steps of uncertain function.
Roughly speaking, the build order (corresponds to functions order):
binutils [i686 and x86_64, with host compiler]
mingw-w64 header [i686 and x86_64]
gmp [x86_64, host compiler]
mpfr/isl/cloog [x86_64, host compiler]
mpc [x86_64, host compiler]
GCC bootstrap compiler [i686 and x86_64, host compiler]
^ NEED to specify posix as threading lib, or will be win32 by default
^ This is where you set SJLJ or DW2 exceptions model (for win32)
Mingw-w64 CRT [i686 and x86_64, Mingw-w64 compiler]
winpthreads [i686 and x86_64, Mingw-w64 compiler]
^ MUST be built before libGCC or threading won't work properly
GCC [i686 and x86_64, host compiler]


The CRT build script is relatively dumb and need to set
CC variable to the the mingw compiler in order to work.
"""
import os
import stat
import re
import tarfile
import ftplib
import multiprocessing as mp
import subprocess
import argparse
import hashlib
import datetime
import time
import socket
from ftplib import FTP
from urllib import request, response
from urllib.parse import urljoin, urlparse
from operator import itemgetter

import sys
from bs4 import BeautifulSoup
from shutil import rmtree, move
from colorama import init, Fore, Back, Style, deinit

# Constants
WORK_FOLDER = "~/MWTC/"
CONFIG_GUESS = "https://raw.githubusercontent.com/gcc-mirror/gcc/master/config.guess"
GNU_SERVER = "ftp.yzu.edu.tw"  # All GNU FTP servers do not support MLST/D!
GCC_SERVER = "gcc.gnu.org"

GNU_MIRRORS = [
        "mirror.jre655.com",  # Japan
        "ftp.yzu.edu.tw",  # Taiwan
        "reflection.oss.ou.edu",  # US
        "mirrors.ocf.berkeley.edu",  # US
        "mirrorservice.org",  # UK
        "ftp.igh.cnrs.fr",  # France
        "mirror.checkdomain.de",  # Germany
        "ftp.unicamp.br",  # Brazil
        "gnu.mirror.iweb.com",  # Canada
        "mirror.tochlab.net",  # Russia
        "ftp.gnu.org"  # Official
    ]

GCC_MIRRORS = [
        "ftp.irisa.fr",  # France
        "ftp.fu-berlin.de",  # Germany
        "ftp.ntua.gr",  # Greece
        "ftp.nluug.nl",  # Netherlands
        "gcc.gnu.org"  # Official
    ]

FTP_DOWNLOADS = ["binutils", "gcc", "gmp", "mpfr", "mpc", "isl", "cloog"]

FTP_SERVERS = {
    "gcc": GCC_SERVER,
    "binutils": GNU_SERVER,
    "gmp": GCC_SERVER,
    "mpfr": GCC_SERVER,
    "mpc": GCC_SERVER,
    "isl": GCC_SERVER,
    "cloog": GCC_SERVER
}

PRIMARY_FTP_FOLDERS = {
    "gcc": "/pub/gcc/releases/",
    "binutils": "/pub/gnu/binutils/",
    "gmp": "/pub/gcc/infrastructure/",
    "mpfr": "/pub/gcc/infrastructure/",
    "mpc": "/pub/gcc/infrastructure/",
    "isl": "/pub/gcc/infrastructure/",
    "cloog": "/pub/gcc/infrastructure/"
}

HTML_DOWNLOADS = ["mingw64"]

HTML_URLS = {
    "mingw64": "https://github.com/mirror/mingw-w64/releases"
}

FILENAME_PATTERNS = {
    "gcc": r"^gcc-([0-9.]+).tar.gz$",
    "binutils": r"^binutils-([0-9.]+).tar.bz2$",
    "gmp": r"^gmp-([0-9.]+).tar.bz2$",
    "mpfr": r"^mpfr-([0-9.]+).tar.bz2$",
    "mpc": r"^mpc-([0-9.]+).tar.gz$",
    "isl": r"^isl-([0-9.]+).tar.bz2$",
    "cloog": r"^cloog-([0-9.]+).tar.gz$",
    "mingw64": r".+?([0-9.]+).tar.gz$"
}

FILENAME_VERSION_CAPTURE = {
    "gcc": 1,
    "binutils": 1,
    "gmp": 1,
    "mpfr": 1,
    "mpc": 1,
    "isl": 1,
    "cloog": 1,
    "mingw64": 1
}

FOLDER_PATTERNS = {
    "gcc": r"^gcc-([0-9.]+)$",
    "binutils": None,
    "gmp": None,
    "mpfr": None,
    "mpc": None,
    "isl": None,
    "cloog": None
}

FOLDER_VERSION_CAPTURE = {
    "gcc": 1,
    "binutils": 1,
    "gmp": 1,
    "mpfr": 1,
    "mpc": 1,
    "isl": 1,
    "cloog": 1
}

PREFERRED_FOLDER_VERSION = {  # ignored if pattern is None
    "gcc": "99",
    "binutils": "99",
    "gmp": "99",
    "mpfr": "99",
    "mpc": "99",
    "isl": "99",
    "cloog": "99"
}

PREFERRED_FILE_VERSION = {
    "gcc": "99",
    "binutils": "99",
    "gmp": "99",
    "mpfr": "99",
    "mpc": "99",
    "isl": "99",
    "cloog": "99",
    "mingw64": "99"
}

SAVE_PATH = {
    "gcc": "./dl/gcc.tar.gz",
    "binutils": "./dl/binutils.tar.bz2",
    "gmp": "./dl/gmp.tar.bz2",
    "mpfr": "./dl/mpfr.tar.bz2",
    "mpc": "./dl/mpc.tar.gz",
    "isl": "./dl/isl.tar.bz2",
    "cloog": "./dl/cloog.tar.gz",
    "mingw64": "./dl/mingw64.tar.gz"
}

LOCATIONS = {
    "pkg_dir": "./pkgs/",
    "mingw_w64_i686_prefix": "./mingw-w64-i686/",
    "mingw_w64_x86_64_prefix": "./mingw-w64-x86_64/",
    "mingw_w64_source_dir": "./source/",
    "mingw_w64_build_dir": "./build/"
}

TARGET = {
    "i686": "i686-w64-mingw32",
    "x86_64": "x86_64-w64-mingw32"
}

USE_SJLJ = False

PERFORMANCE_COUNTER = {}

HELP_TEXT = """\
{hl}Python(Anaconda) script for building Mingw-w64 cross-toolchain{chl}
Copyrighted 2017 Maverick Tse YM, Hong Kong
Twitter: @MaverickTse

This script attempts to build Mingw-w64 toolchain with reference
to Zeranoe's build script. This script only works under bash-like
shell and {hl}requires Anaconda with Python 3.6 or newer{chl}. DO NOT USE Python
from Ubuntu/Debian official/personal repo!

Besides Anaconda, you will also need:
{hl}build-essential, automake, texinfo, yasm{chl}
for standard build facilities.

Unlike Zeranoe's build script, wget, git, subversion, etc. are not needed
since this script only utilize FTP and HTTP through Python's built-in
networking functions. This script also cut down redundant build steps
in Zeranoe's script when looping.

Download is parallelized with 2 threads by default.

Currently, win32 and win64 toolchains will be built without multilib.

If unspecified, the sandbox will be ~/MWTC by default,
and latest release versions of each component will be used.

All errors will be logged into files in the component's build folder:
config_error.log
build_error.log
install_error.log
may be generated with all the details. Console output is kept minimal.

At the end of the build process, a readme file and 3 shell scripts
would be generated.
"""


# Common functions


def print_ok():
    print("【" + Fore.GREEN + Style.BRIGHT + "OK" + Fore.RESET + Style.RESET_ALL + "】 ", end='')
    return None


def print_error():
    print("【" + Fore.RED + Back.LIGHTYELLOW_EX + Style.BRIGHT + "ERROR" + Fore.RESET + Style.RESET_ALL + "】 ", end='')
    return None


def ftp_get(server, folder, filename_re, file_version_capture_group, save_path=None,
            preferred_version="99", folder_re=None, folder_version_capture_group=1,
            preferred_folder_version="99"):
    """
    Download a file from FTP server with the preferred version or get the latest
    :param server: The ftp server name without sub-directory or protocol name
    :param folder: The first folder to move to after log in
    :param filename_re: A regex string that match the full intended filename, with version string in capture group
    :param file_version_capture_group: Specify which capture group holds the version string. Default=1
    :param save_path: Destination folder or filename for saving the downloaded file
    :param preferred_version: A file with this version string will be downloaded first. If no match, get the latest file
    :param folder_re: An optional regex for moving to a child folder a second time, basing on version string
    :param folder_version_capture_group: Specify which capture group in folder_re holds the version string
    :param preferred_folder_version: The preferred version string when moving to a child folder
    :return: None if failed. Return the saving path on success
    """
    if not server:
        return None
    if not folder:
        return None
    if not filename_re:
        return None
    if file_version_capture_group < 1:
        return None

    ftp = FTP()
    try:
        ftp.connect(server, timeout=30)
        ftp.login()
    except ftplib.all_errors as e:
        print('FTP Error: ', str(e))
        ftp.quit()
        return False
    ftp.cwd(folder)

    if folder_re:  # runs only when there is a regex for folder
        fre = re.compile(folder_re)
        available_version = {}  # id: version
        folder_data = {}  # id: folder name
        modify_data = {}  # id: last modified date
        keyid = 0
        try:
            listing = ftp.mlsd(facts=["type", "modify"])
            for name, fact in listing:
                if fact["type"] != "dir":
                    continue
                m = fre.fullmatch(name)
                if not m:
                    continue
                available_version[keyid] = m.group(folder_version_capture_group)
                folder_data[keyid] = name
                modify_data[keyid] = fact["modify"]
                keyid += 1
        except ftplib.all_errors as e:
            print("FTP Server does not support MLST/MLSD command! Falling back to NLST")
            print("Note: No file type or date info available")
            name_list = ftp.nlst()
            for name in name_list:
                m = fre.fullmatch(name)
                if not m:
                    continue
                available_version[keyid] = m.group(folder_version_capture_group)
                folder_data[keyid] = name
                modify_data[keyid] = keyid
                keyid += 1
        # Check for preferred folder version
        foundkey = None
        for key, ver in available_version.items():
            if ver == str(preferred_folder_version):
                foundkey = key
                break
        final_folder = folder
        if foundkey:
            final_folder = urljoin(final_folder, folder_data[foundkey])
        else:  # get latest, default action
            #latestid, stamp = sorted(modify_data.items(), key=itemgetter(1), reverse=False).pop()
            latestid, stamp = sorted(available_version.items(), key=itemgetter(1), reverse=False).pop()
            final_folder = urljoin(final_folder, folder_data[latestid])
        ftp.cwd(final_folder)  # change to our final target folder


    # We should now be inside the final target folder
    # Get file listing and match filename

    file_version = {}  # id: version
    file_names = {}  # id: filename
    file_date = {}  # id: modified date
    keyid = 0
    fnre = re.compile(filename_re)
    try:
        listing = ftp.mlsd(facts=["type", "modify"])
        for name, fact in listing:
            if fact["type"] != "file":
                continue
            fm = fnre.fullmatch(name)
            if not fm:
                continue
            file_version[keyid] = fm.group(file_version_capture_group)
            file_names[keyid] = name
            file_date[keyid] = fact["modify"]
            keyid += 1
    except ftplib.all_errors as e:
        print("No MLST/MLSD support again... falling back")
        name_list = ftp.nlst()
        for name in name_list:
            fm = fnre.fullmatch(name)
            if not fm:
                continue
            file_version[keyid] = fm.group(file_version_capture_group)
            file_names[keyid] = name
            file_date[keyid] = keyid
            keyid += 1
    # Check for preferred file version

    foundkey = None
    for key, ver in file_version.items():
        if ver == str(preferred_version):
            foundkey = key
            break
    final_archive = None
    if foundkey:
        final_archive = file_names[foundkey]
    else:
        #latestid, stamp = sorted(file_date.items(), key=itemgetter(1), reverse=False).pop()
        latestid, stamp = sorted(file_version.items(), key=itemgetter(1), reverse=False).pop()
        final_archive = file_names[latestid]
    # Download file
    # Before downloading, set the save path
    final_path = None
    if not save_path:  # when not specified, save in current folder, preserve name
        final_path = os.path.join(os.getcwd(), final_archive)
    else:
        dir_name = os.path.dirname(save_path)  # can be empty
        filename = os.path.basename(save_path)  # can be empty
        if dir_name:
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)
        if filename:
            final_path = save_path
        else:
            final_path = os.path.join(dir_name, final_archive)
        final_path = os.path.abspath(final_path)
    if os.path.exists(final_path):
        print(final_path, "already exists, skipping...")
        ftp.quit()
        return final_path
    # prepare the file
    retrieve_cmd = "RETR " + final_archive
    print("[FTP] Downloading ", final_archive, " to ", final_path, " ...")
    ftp.retrbinary(retrieve_cmd, open(final_path, "wb").write)
    print("[FTP] Download Finished")
    ftp.quit()
    return final_path


def select_mirror(server_list=[], priority=1, protocol="FTP", timeout=5.0):
    """
    Select a server mirror based on connection time
    :param server_list: A list of server names
    :param priority: 1 for the fastest server, 2 for the 2nd fast, etc.
    :param protocol: Decide PORT to use. Accepts HTTP, HTTPS, FTP, SFTP, SSH
    :param timeout: time-out threshold in second
    :return: a tuple of (server_name, latency)
    """
    benchmark = {} # to hold the server: connect time pairs
    # Set the ports to connect based on protocol
    port = 1
    if protocol == "HTTP":
        port = 80
    elif protocol == "HTTPS":
        port = 443
    elif protocol == "FTP":
        port = 21
    elif (protocol == "SFTP") or (protocol == "SSH"):
        port = 22
    else:
        port = 1
    # Test each server
    for server in server_list:
        # First need a default socket
        sock = socket.socket()
        sock.settimeout(timeout)
        start = time.time()
        try:
            sock.connect((server, port))
            end = time.time()
            benchmark[server] = end - start
            sock.close()
        except socket.herror as e:
            print("Hostname error for ", server)
            print(e)
            sock.close()
            continue
        except socket.gaierror as e:
            print("Address error for ", server)
            print(e)
            sock.close()
            continue
        except socket.timeout:
            print("Server ", server, " timed out")
            sock.close()
            continue

    # fix priority number
    valid_servers = len(benchmark)
    if valid_servers <= 0:
        print("[WARNING] No mirror available!")
        return None, None
    priority = min([valid_servers, priority]) - 1
    priority = max([0, priority])  # keep it >=0
    # Sort server list
    sorted_servers = sorted(benchmark.items(), key=itemgetter(1), reverse=False)
    return sorted_servers[priority]


def ftp_get_by_component(component):
    os.chdir(WORK_FOLDER)
    ftp_get(FTP_SERVERS[component], PRIMARY_FTP_FOLDERS[component], FILENAME_PATTERNS[component],
            FILENAME_VERSION_CAPTURE[component],
            SAVE_PATH[component], PREFERRED_FILE_VERSION[component], FOLDER_PATTERNS[component],
            FOLDER_VERSION_CAPTURE[component], PREFERRED_FOLDER_VERSION[component])
    untar(SAVE_PATH[component], LOCATIONS["pkg_dir"])


def html_get_by_component(component):
    os.chdir(WORK_FOLDER)
    html_get(HTML_URLS[component], FILENAME_PATTERNS[component], FILENAME_VERSION_CAPTURE[component],
             SAVE_PATH[component])
    untar(SAVE_PATH[component], LOCATIONS["pkg_dir"])


def html_get(url, filename_re, file_version_capture_group=1, save_path=None, preferred_version="99"):
    """
    Scrape a HTML page for links, then download the preferred version or the latest
    :param url: The URL string for the HTML page
    :param filename_re: A regex string that will run against links to search for target files
    :param file_version_capture_group: Specify which group holds the version string. Default=1
    :param save_path: Folder, filename or full path for saving the downloaded file
    :param preferred_version: A string for your preferred version
    :return: None if failed. Saved path on success
    """
    if not url:
        return None
    if not filename_re:
        return None
    html = request.urlopen(url)
    soup = BeautifulSoup(html, "html.parser", from_encoding=html.info().get_param("charset"))
    file_regex = re.compile(filename_re)
    archive_info = {}  # id: url
    version_info = {}  # id: version
    keyid = 0

    for link in soup.find_all("a", href=True):
        m = file_regex.fullmatch(link["href"])
        if m:
            archive_info[keyid] = link["href"]
            version_info[keyid] = m.group(file_version_capture_group)
            keyid += 1

    file_id = None
    #  Search for preferred version
    for key, version in version_info.items():
        if version == preferred_version:
            file_id = key
            break
    # If not found, get the latest
    if not file_id:
        file_id, ver = sorted(version_info.items(), key=itemgetter(1), reverse=False).pop()

    final_url = archive_info[file_id]
    # make url absolute if not yet
    parsed_url = urlparse(final_url)
    if not parsed_url[1]:  # 1 as netloc
        final_url = urljoin(url, final_url)

    # Set save path
    final_archive = os.path.basename(parsed_url[2])  # 2 as path
    final_path = None
    if not save_path:  # when not specified, save in current folder, preserve name
        final_path = os.path.join(os.getcwd(), final_archive)
    else:
        dir_name = os.path.dirname(save_path)  # can be empty
        filename = os.path.basename(save_path)  # can be empty
        if dir_name:
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)
        if filename:
            final_path = save_path
        else:
            final_path = os.path.join(dir_name, final_archive)

        final_path = os.path.abspath(final_path)
    if os.path.exists(final_path):
        print(final_path, " already exists, skipping...")
        return final_path
    # Download
    print("[HTML] Downloading from ", final_url, " to ", final_path)
    saved_name, header = request.urlretrieve(final_url, final_path)
    if saved_name:
        print("[HTML] Download finished")
        return saved_name
    else:
        print("[HTML] Download Failed")
        return None


def hash_file_md5(filename):
    """
    Obtain a MD5 digest of a file
    :param filename: The file to be hashed
    :return: MD5 digest on success. None if file is not found.
    """
    if not os.path.exists(filename):
        print("[MD5 HASH]:", filename, " not found")
        return None
    md5 = hashlib.md5()
    with open(filename, "rb") as f:
        while True:
            data = f.read(128)
            if not data:
                break
            md5.update(data)
    return md5.hexdigest()


def untar(source_archive, destination_folder):
    """
    Decompress the source archive tarball into the destination foler
    :param source_archive: the path to tarball
    :param destination_folder: where to put the extracted files
    :return: None if failed. Destination path if success.
    """
    if not os.path.exists(source_archive):
        print("The tarball ", source_archive, " cannot be found")
        return None
    if not os.path.exists(destination_folder):
        os.makedirs(destination_folder)
    source_md5_file = source_archive + ".md5"
    new_md5 = hash_file_md5(source_archive)
    if os.path.exists(source_md5_file):
        old_md5 = None
        with open(source_md5_file,"r") as f:
            old_md5 = f.read()
        if new_md5 in old_md5:
            print("[TAR] Same archive found. Skipping")
            return destination_folder

    hFile = tarfile.open(source_archive)
    if hFile:
        print("[TAR] Extracting ", source_archive, " to ", destination_folder)
        extract_ok = False
        try:
            hFile.extractall(destination_folder)
            extract_ok = True
        except tarfile.ExtractError as e:
            print("Error extracting tarfile: skipping")
            print(str(e))
        except IOError as e:
            print("IO error: skipping")
            print(str(e))
        hFile.close()
        print("[TAR] Extraction finished")
        if extract_ok:
            with open(source_md5_file, "w") as f:
                f.write(new_md5)
        return destination_folder
    else:
        print("Cannot open tarball ", source_archive, " for extraction")
        return None


def guess_config():
    global WORK_FOLDER
    os.chdir(WORK_FOLDER)
    saved_name, header = request.urlretrieve(CONFIG_GUESS, os.path.join(WORK_FOLDER, "config.guess"))

    if not os.path.exists("./config.guess"):
        return None
    shell_type = os.getenv("SHELL")

    if not shell_type:
        print("Need to be running in a bash-like shell environment")
        return None
    if "sh" not in shell_type:
        print("guess.config need to be run in bash-like shell")
        return None
    system_string = subprocess.run(["sh", "config.guess"], stdout=subprocess.PIPE).stdout.decode("utf-8")

    return system_string


def run_nproc():
    """
    Get cpu count via nproc
    :return: number of cpu core
    """
    return_string = subprocess.run(["nproc"], stdout=subprocess.PIPE).stdout.decode("utf-8")
    cores = int(return_string)
    if cores > 2:
        return cores-1
    else:
        return cores


def set_env(x86_64=True):
    """
    Set environment variables for specific compiler usage
    :param x86_64: When True[default], set for 64bit usage, 32bit otherwise
    :return: a map with "old_path" and "old_cc"
    """
    origin = {
        "old_path": os.environ["PATH"],
        "old_cc": os.environ["CC"]
    }
    current_dir = os.getcwd()
    global WORK_FOLDER, LOCATIONS, TARGET
    os.chdir(WORK_FOLDER)
    prefix_x86 = os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"])
    prefix_x86 = os.path.join(prefix_x86, "bin")
    prefix_x86_64 = os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"])
    prefix_x86_64 = os.path.join(prefix_x86_64, "bin")
    old_path_var = os.environ["PATH"]
    x86_env_path = prefix_x86 + ":" + old_path_var
    x86_64_env_path = prefix_x86_64 + ":" + old_path_var
    if x86_64:
        os.environ["PATH"] = x86_64_env_path
    else:
        os.environ["PATH"] = x86_env_path
    os.environ["CC"] = "gcc"
    os.chdir(current_dir)
    return origin


def restore_env(old_env):
    """
    Restore environment variables as changed by set_env()
    :param old_env: the map returned by set_env()
    :return: None
    """
    old_cc = old_env["old_cc"]
    old_path = old_env["old_path"]

    if old_cc:
        os.environ["CC"] = old_cc
    if old_path:
        os.environ["PATH"] = old_path


def build_binutils(source_folder, build_folder, system_type):
    """
    Build both x86 and x86_64 versions of Binutils
    :param source_folder: The folder containing the source code for Binutils
    :param build_folder: A folder outside of source_folder for building
    :param system_type: a string as returned by guess_config function
    :return: None if failed
    """
    global WORK_FOLDER, LOCATIONS, TARGET
    os.chdir(WORK_FOLDER)
    i686_prefix = os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"])
    x86_64_prefix = os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"])
    full_source_path = os.path.abspath(source_folder)
    full_build_path = os.path.abspath(build_folder)
    full_build_path = os.path.join(full_build_path, "binutils")
    build_path_x86 = os.path.join(full_build_path, "x86")
    build_path_x86_64 = os.path.join(full_build_path, "x86_64")
    # print(i686_prefix)
    # print(x86_64_prefix)
    # print(full_source_path)
    # print(full_build_path)
    # print(build_path_x86)
    # print(build_path_x86_64)
    # purge old build file
    if os.path.exists(full_build_path):
        print("Deleting old Binutils build folders")
        rmtree(full_build_path)
    # recreate folders
    os.makedirs(build_path_x86)
    os.makedirs(build_path_x86_64)
    # create prefix paths if absent
    if not os.path.exists(i686_prefix):
        os.makedirs(i686_prefix)
    if not os.path.exists(x86_64_prefix):
        os.makedirs(x86_64_prefix)
    # build x86
    os.chdir(build_path_x86)
    os.environ["CC"] = "gcc"
    configure_script = os.path.join(full_source_path, "configure")
    arg_build = "--build=" + system_type
    arg_target = "--target=" + TARGET["i686"]
    arg_prefix = "--prefix=" + i686_prefix
    arg_sysroot = "--with-sysroot=" + i686_prefix
    arg_others = "--disable-multilib --disable-nls --disable-shared --enable-static"
    print("Configuring Binutils x86...")
    run_result = subprocess.run(["sh", configure_script, arg_build, arg_target, arg_prefix, arg_sysroot,
                                 "--disable-multilib", "--disable-nls", "--disable-shared", "--enable-static"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run_result.returncode:
        print("Error configuring Binutils x86!")
        output_message = run_result.stdout.decode("utf-8")
        error_message = run_result.stderr.decode("utf-8")
        with open("./configure_error.log", "w") as file_handle:
            file_handle.write(output_message)
            file_handle.write(error_message)
        return None
    print("Done configuring Binutils x86")
    cpu_count = str(run_nproc())
    print("Building Binutils x86")
    run_result = subprocess.run(["make", "-j", str(cpu_count)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run_result.returncode:
        print("Error building Binutils x86!")
        output_message = run_result.stdout.decode("utf-8")
        error_message = run_result.stderr.decode("utf-8")
        with open("./make_error.log", "w") as file_handle:
            file_handle.write(output_message)
            file_handle.write(error_message)
        return None
    print("Finished building Binutils x86")
    print("Installing Binutils x86")
    run_result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run_result.returncode:
        print("Error installing Binutils x86!")
        output_message = run_result.stdout.decode("utf-8")
        error_message = run_result.stderr.decode("utf-8")
        with open("./make_error.log", "w") as file_handle:
            file_handle.write(output_message)
            file_handle.write(error_message)
        return None
    # build x86_64
    os.chdir(build_path_x86_64)
    arg_target = "--target=" + TARGET["x86_64"]
    arg_prefix = "--prefix=" + x86_64_prefix
    arg_sysroot = "--with-sysroot=" + x86_64_prefix
    print("Configuring Binutils x86_64...")
    run_result = subprocess.run(["sh", configure_script, arg_build, arg_target, arg_prefix, arg_sysroot,
                                 "--disable-multilib", "--disable-nls", "--disable-shared", "--enable-static"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run_result.returncode:
        print("Error configuring Binutils x86_64!")
        output_message = run_result.stdout.decode("utf-8")
        error_message = run_result.stderr.decode("utf-8")
        with open("./configure_error.log", "w") as file_handle:
            file_handle.write(output_message)
            file_handle.write(error_message)
        return None
    print("Done configuring Binutils x86_64")
    print("Building Binutils x86_64")
    run_result = subprocess.run(["make", "-j", str(cpu_count)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run_result.returncode:
        print("Error building Binutils x86_64!")
        output_message = run_result.stdout.decode("utf-8")
        error_message = run_result.stderr.decode("utf-8")
        with open("./make_error.log", "w") as file_handle:
            file_handle.write(output_message)
            file_handle.write(error_message)
        return None
    print("Finished building Binutils x86_64")
    print("Installing Binutils x86_64")
    run_result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if run_result.returncode:
        print("Error installing Binutils x86!")
        output_message = run_result.stdout.decode("utf-8")
        error_message = run_result.stderr.decode("utf-8")
        with open("./make_error.log", "w") as file_handle:
            file_handle.write(output_message)
            file_handle.write(error_message)
        return None
    os.chdir(WORK_FOLDER)
    return True


def build_mingw_header(source_folder, build_folder, system_type):
    """
    Config and Install Mingw-w64 header files and make symlinks
    :param source_folder: Path to mingw-w64 source folder
    :param build_folder: Build location outside source folder
    :param system_type: string as returned by guess_config()
    :return: None if failed. True if success.
    """
    global WORK_FOLDER, LOCATIONS, TARGET
    os.chdir(WORK_FOLDER)
    config_source = os.path.join(os.path.abspath(source_folder), "mingw-w64-headers", "configure")
    prefix_x86 = os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"])
    prefix_x86_64 = os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"])
    build_common = os.path.join(os.path.abspath(build_folder), "header")
    build_x86 = os.path.join(os.path.abspath(build_folder), "header", "x86")
    build_x86_64 = os.path.join(os.path.abspath(build_folder), "header", "x86_64")
    arg_build = "--build=" + system_type
    arg_host = "--host=" + TARGET["i686"]
    arg_prefix = "--prefix=" + prefix_x86
    # purge old build file
    if os.path.exists(build_common):
        rmtree(build_common)
    # create working folders
    os.makedirs(build_x86)
    os.makedirs(build_x86_64)
    # set path, save old path for x86_64 use
    old_path_var = os.environ["PATH"]
    x86_env_path = prefix_x86 + ":" + old_path_var
    x86_64_env_path = prefix_x86_64 + ":" + old_path_var
    os.environ["PATH"] = x86_env_path
    # configure x86
    os.chdir(build_x86)
    print("Configuring Mingw-w64 x86 headers...")
    result = subprocess.run(["sh", config_source, "--enable-sdk-all", arg_build
                             , arg_host, arg_prefix], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        print("Failed to configure Mingw-w64 x86 headers!")
        log_file = os.path.join(build_x86, "config_error.log")
        with open(log_file, "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        return None
    print("Configured Mingw-w64 x86 headers")
    # Install headers
    print("Installing Mingw-w64 x86 headers...")
    result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        print("Failed to install Mingw-w64 x86 headers!")
        log_file = os.path.join(build_x86, "install_error.log")
        with open(log_file, "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        return None
    print("[OK] Mingw-w64 x86 headers installed")
    print("Making symlinks...")
    os.chdir(prefix_x86)
    target_folder = "./" + TARGET["i686"]
    include_folder = os.path.join(target_folder, "include")
    if not os.path.exists("./mingw"):
        os.symlink(target_folder, "./mingw")
    if not os.path.exists(include_folder):
        os.chdir(target_folder)
        os.symlink("../include", "./include")
        os.chdir(prefix_x86)
    print("[OK] symlinks done")
    # x86_64 part
    os.environ["PATH"] = x86_64_env_path
    arg_host = "--host=" + TARGET["x86_64"]
    arg_prefix = "--prefix=" + prefix_x86_64
    # configure x86_64
    os.chdir(build_x86_64)
    print("Configuring Mingw-w64 x86_64 headers...")
    result = subprocess.run(["sh", config_source, "--enable-sdk-all", arg_build
                                , arg_host, arg_prefix], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        print("Failed to configure Mingw-w64 x86 headers!")
        log_file = os.path.join(build_x86_64, "config_error.log")
        with open(log_file, "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        return None
    print("Configured Mingw-w64 x86_64 headers")
    # Install headers
    print("Installing Mingw-w64 x86_64 headers...")
    result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        print("Failed to install Mingw-w64 x86_64 headers!")
        log_file = os.path.join(build_x86_64, "install_error.log")
        with open(log_file, "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        return None
    print("[OK] Mingw-w64 x86_64 headers installed")
    print("Making symlinks...")
    os.chdir(prefix_x86_64)
    target_folder = "./" + TARGET["x86_64"]
    include_folder = os.path.join(target_folder, "include")
    if not os.path.exists("./mingw"):
        os.symlink(target_folder, "./mingw")
    if not os.path.exists(include_folder):
        os.chdir(target_folder)
        os.symlink("../include", "./include")
        os.chdir(prefix_x86_64)
    os.chdir(WORK_FOLDER)
    os.environ["PATH"] = old_path_var
    print("[OK] symlink done")
    return True


def build_gmp(source_folder, build_folder, system_type):
    """
    Build GMP library
    :param source_folder: Source folder of GMP
    :param build_folder: Folder for holding build
    :param system_type: string as returned by guess_config()
    :return: gmp_prefix string on success, None on Fail.
    """
    global WORK_FOLDER, LOCATIONS
    os.chdir(WORK_FOLDER)
    abs_source = os.path.abspath(source_folder)
    abs_build = os.path.abspath(build_folder)
    abs_pkg = os.path.abspath(LOCATIONS["pkg_dir"])
    build_common = os.path.join(abs_build, "gmp")
    config_path = os.path.join(abs_source, "configure")
    uname_info = os.uname()
    prefix = os.path.join(abs_pkg, "gmp", "gmp-"+uname_info.machine)
    # purge build folder
    if os.path.exists(build_common):
        rmtree(build_common)
    os.makedirs(build_common)
    os.chdir(build_common)
    arg_build = "--build=" + system_type
    arg_prefix = "--prefix=" + prefix
    old_env = None
    if "64" in uname_info.machine:
        old_env = set_env()
    else:
        old_env = set_env(False)
    print("Configuring GMP...")
    result = subprocess.run(["sh", config_path, arg_build, arg_prefix, "--enable-fat",
                             "--disable-shared", "--enable-static", "--enable-cxx",
                             "CPPFLAGS=-fexceptions"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error configuring GMP!")
        with open("config_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    cpu_cores = str(run_nproc())
    print("Building GMP...")
    result = subprocess.run(["make", "-j", cpu_cores], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error building GMP!")
        with open("build_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None
    print("Installing GMP...")
    result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error installing GMP!")
        with open("install_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    restore_env(old_env)
    os.chdir(WORK_FOLDER)
    return prefix


def build_mpfr(source_folder, build_folder, system_type, gmp_prefix):
    """
    Build MPFR library. Depends on GMP.
    :param source_folder: Source folder of MPFR
    :param build_folder: Build folder
    :param system_type: string as returned by guess_config()
    :param gmp_prefix: string as returned by build_gmp()
    :return: mpfr_prefix on success, None when failed
    """
    global WORK_FOLDER, LOCATIONS
    os.chdir(WORK_FOLDER)
    abs_source = os.path.abspath(source_folder)
    abs_build = os.path.abspath(build_folder)
    abs_pkg = os.path.abspath(LOCATIONS["pkg_dir"])
    build_common = os.path.join(abs_build, "mpfr")
    config_path = os.path.join(abs_source, "configure")
    uname_info = os.uname()
    prefix = os.path.join(abs_pkg, "mpfr", "mpfr-" + uname_info.machine)
    # purge build folder
    if os.path.exists(build_common):
        rmtree(build_common)
    os.makedirs(build_common)
    os.chdir(build_common)
    arg_build = "--build=" + system_type
    arg_prefix = "--prefix=" + prefix
    arg_gmp = '--with-gmp=' + gmp_prefix
    old_env = None
    if "64" in uname_info.machine:
        old_env = set_env()
    else:
        old_env = set_env(False)
    print("Configuring MPFR...")
    result = subprocess.run(["sh", config_path, arg_build, arg_prefix, arg_gmp,
                             "--disable-shared", "--enable-static"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error configuring MPFR!")
        with open("config_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    cpu_cores = str(run_nproc())
    print("Building MPFR...")
    result = subprocess.run(["make", "-j", cpu_cores], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error building MPFR!")
        with open("build_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None
    print("Installing MPFR...")
    result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error installing MPFR!")
        with open("install_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    restore_env(old_env)
    os.chdir(WORK_FOLDER)
    return prefix


def build_isl(source_folder, build_folder, system_type, gmp_prefix):
    """
    Build ISL library. Depends on GMP.
    :param source_folder: Source folder of ISL
    :param build_folder: Build folder
    :param system_type: string as returned by guess_config()
    :param gmp_prefix: string as returned by build_gmp()
    :return: isl_prefix on success, None when failed
    """
    global WORK_FOLDER, LOCATIONS
    os.chdir(WORK_FOLDER)
    abs_source = os.path.abspath(source_folder)
    abs_build = os.path.abspath(build_folder)
    abs_pkg = os.path.abspath(LOCATIONS["pkg_dir"])
    build_common = os.path.join(abs_build, "isl")
    config_path = os.path.join(abs_source, "configure")
    uname_info = os.uname()
    prefix = os.path.join(abs_pkg, "isl", "isl-" + uname_info.machine)
    # purge build folder
    if os.path.exists(build_common):
        rmtree(build_common)
    os.makedirs(build_common)
    os.chdir(build_common)
    arg_build = "--build=" + system_type
    arg_prefix = "--prefix=" + prefix
    arg_gmp = '--with-gmp-prefix=' + gmp_prefix
    old_env = None
    if "64" in uname_info.machine:
        old_env = set_env()
    else:
        old_env = set_env(False)
    print("Configuring ISL...")
    result = subprocess.run(["sh", config_path, arg_build, arg_prefix, arg_gmp,
                             "--disable-shared", "--enable-static", "--with-piplib=no", "--with-clang=no"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error configuring ISL!")
        with open("config_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    cpu_cores = str(run_nproc())
    print("Building ISL...")
    result = subprocess.run(["make", "-j", cpu_cores], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error building ISL!")
        with open("build_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None
    print("Installing ISL...")
    result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error installing ISL!")
        with open("install_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    restore_env(old_env)
    os.chdir(WORK_FOLDER)
    return prefix


def build_cloog(source_folder, build_folder, system_type, gmp_prefix):
    """
    Build CLoog library. Depends on GMP.
    :param source_folder: Source folder of cloog
    :param build_folder: Build folder
    :param system_type: string as returned by guess_config()
    :param gmp_prefix: string as returned by build_gmp()
    :return: cloog_prefix on success, None when failed
    """
    global WORK_FOLDER, LOCATIONS
    os.chdir(WORK_FOLDER)
    abs_source = os.path.abspath(source_folder)
    abs_build = os.path.abspath(build_folder)
    abs_pkg = os.path.abspath(LOCATIONS["pkg_dir"])
    build_common = os.path.join(abs_build, "cloog")
    config_path = os.path.join(abs_source, "configure")
    uname_info = os.uname()
    prefix = os.path.join(abs_pkg, "cloog", "cloog-" + uname_info.machine)
    # purge build folder
    if os.path.exists(build_common):
        rmtree(build_common)
    os.makedirs(build_common)
    os.chdir(build_common)
    arg_build = "--build=" + system_type
    arg_prefix = "--prefix=" + prefix
    arg_gmp = '--with-gmp-prefix=' + gmp_prefix
    old_env = None
    if "64" in uname_info.machine:
        old_env = set_env()
    else:
        old_env = set_env(False)
    print("Configuring CLoog...")
    result = subprocess.run(["sh", config_path, arg_build, arg_prefix, arg_gmp,
                             "--disable-shared", "--enable-static", "--with-bits=gmp", "--with-isl=bundled"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error configuring cloog!")
        with open("config_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    cpu_cores = str(run_nproc())
    print("Building CLoog...")
    result = subprocess.run(["make", "-j", cpu_cores], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error building cloog!")
        with open("build_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None
    print("Installing CLoog...")
    result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error installing cloog!")
        with open("install_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    restore_env(old_env)
    os.chdir(WORK_FOLDER)
    return prefix


def build_mpc(source_folder, build_folder, system_type, gmp_prefix, mpfr_prefix):
    """
    Build ISL library. Depends on GMP and MPFR.
    :param source_folder: Source folder of ISL
    :param build_folder: Build folder
    :param system_type: string as returned by guess_config()
    :param gmp_prefix: string as returned by build_gmp()
    :param mpfr_prefix: string as returned by build_mpfr()
    :return: mpc_prefix on success, None when failed
    """
    global WORK_FOLDER, LOCATIONS
    os.chdir(WORK_FOLDER)
    abs_source = os.path.abspath(source_folder)
    abs_build = os.path.abspath(build_folder)
    abs_pkg = os.path.abspath(LOCATIONS["pkg_dir"])
    build_common = os.path.join(abs_build, "mpc")
    config_path = os.path.join(abs_source, "configure")
    uname_info = os.uname()
    prefix = os.path.join(abs_pkg, "mpc", "mpc-" + uname_info.machine)
    # purge build folder
    if os.path.exists(build_common):
        rmtree(build_common)
    os.makedirs(build_common)
    os.chdir(build_common)
    arg_build = "--build=" + system_type
    arg_prefix = "--prefix=" + prefix
    arg_gmp = '--with-gmp=' + gmp_prefix
    arg_mpfr = '--with-mpfr=' + mpfr_prefix
    old_env = None
    if "64" in uname_info.machine:
        old_env = set_env()
    else:
        old_env = set_env(False)
    print("Configuring MPC...")
    result = subprocess.run(["sh", config_path, arg_build, arg_prefix, arg_gmp, arg_mpfr,
                             "--disable-shared", "--enable-static"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error configuring MPC!")
        with open("config_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    cpu_cores = str(run_nproc())
    print("Building MPC...")
    result = subprocess.run(["make", "-j", cpu_cores], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error building MPC!")
        with open("build_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None
    print("Installing MPC...")
    result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode:
        print("Error installing MPC!")
        with open("install_error.log", "w") as f:
            message = result.stdout.decode("utf-8")
            f.write(message)
            message = result.stderr.decode("utf-8")
            f.write(message)
        restore_env(old_env)
        return None

    restore_env(old_env)
    os.chdir(WORK_FOLDER)
    return prefix


def build_gcc1(source_folder, build_folder, system_type, gmp_prefix, mpfr_prefix,
               isl_prefix, mpc_prefix):
    """
    Build GCC step 1 of 2. Depends on GMP, MPFR, ISL and MPC
    :param source_folder: source folder of GCC
    :param build_folder: folder to hold building files
    :param system_type: string as returned by guess_config()
    :param gmp_prefix: string as returned by build_gmp()
    :param mpfr_prefix: string as returned by build_mpfr()
    :param isl_prefix: string as returned by build_isl()
    :param mpc_prefix: string as returned by build_mpc()
    :return: tuple of build_paths on success, (None,None) when failed
    """
    global WORK_FOLDER, LOCATIONS, TARGET, USE_SJLJ
    build_target = ["i686", "x86_64"]
    os.chdir(WORK_FOLDER)
    abs_source = os.path.abspath(source_folder)
    config_path = os.path.join(abs_source, "configure")
    abs_build_common = os.path.join(os.path.abspath(build_folder), "gcc")

    build_paths = {
        "i686": os.path.join(abs_build_common, "i686"),
        "x86_64": os.path.join(abs_build_common, "x86_64")
    }

    abs_prefix = {
        "i686": os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"]),
        "x86_64": os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"])
    }
    arg_mpc = '--with-mpc=' + mpc_prefix
    arg_mpfr = '--with-mpfr=' + mpfr_prefix
    arg_gmp = '--with-gmp=' + gmp_prefix
    arg_isl = '--with-isl=' + isl_prefix
    arg_build = "--build=" + system_type

    # purge old build files
    if os.path.exists(abs_build_common):
        rmtree(abs_build_common)
    os.makedirs(build_paths["i686"])
    os.makedirs(build_paths["x86_64"])

    for target in build_target:
        os.chdir(build_paths[target])
        print("Configuring GCC (1 of 2) ", target, "...")
        arg_target = "--target=" + TARGET[target]
        arg_prefix = '--prefix=' + abs_prefix[target]
        arg_sysroot = '--with-sysroot=' + abs_prefix[target]
        arg_sjlj = ""
        if USE_SJLJ and (target == "i686"):
            arg_sjlj += "--enable-sjlj-exceptions"
        else:
            arg_sjlj += "--disable-sjlj-exceptions"

        print("Configuring GCC ", target, "...")
        result = subprocess.run(["sh", config_path, arg_build, arg_target, arg_prefix, arg_sysroot,
                                  "--enable-static", "--disable-shared", "--disable-nls",
                                  "--disable-multilib", '--enable-languages=c,c++', "--enable-lto",
                                  "--enable-fully-dynamic-string", "--enable-threads=posix", arg_sjlj,
                                  arg_mpc, arg_mpfr, arg_isl, arg_mpc, arg_gmp],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Failed to configure GCC (1 of 2) ", TARGET[target])
            with open("config_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
            return None, None
        # actual build
        cpu_count = str(run_nproc())
        print("Building GCC (1 of 2) ", target, "...")
        result = subprocess.run(["make", "-j", cpu_count, "all-gcc"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Failed to build GCC (1 of 2) ", TARGET[target])
            with open("build_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
            return None, None
        # Install GCC
        print("Installing GCC (1 of 2) ", target, "...")
        result = subprocess.run(["make", "install-gcc"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Failed to install GCC (1 of 2) ", TARGET[target])
            with open("install_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
            return None, None

    os.chdir(WORK_FOLDER)
    return build_paths["i686"], build_paths["x86_64"]


def build_crt(source_folder, build_folder, system_type):
    """
    Build mingw-w64 CRT.
    :param source_folder: Source code folder for mingw-w64
    :param build_folder: folder to hold building files
    :param system_type: string as returned by guess_config()
    :return: True when success. None when failed.
    """
    global WORK_FOLDER, LOCATIONS, TARGET
    build_target = ["i686", "x86_64"]
    os.chdir(WORK_FOLDER)
    abs_source = os.path.abspath(source_folder)
    config_path = os.path.join(abs_source, "mingw-w64-crt", "configure")
    abs_build_common = os.path.join(os.path.abspath(build_folder), "crt")

    build_paths = {
        "i686": os.path.join(abs_build_common, "i686"),
        "x86_64": os.path.join(abs_build_common, "x86_64")
    }

    abs_prefix = {
        "i686": os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"]),
        "x86_64": os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"])
    }

    path_var ={
        "i686": os.path.join(os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"]), "bin")+":"+os.environ["PATH"],
        "x86_64": os.path.join(os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"]), "bin")+":"+os.environ["PATH"],
        "original": os.environ["PATH"]
    }

    cc_var ={
        "i686": "i686-w64-mingw32-gcc",
        "x86_64": "x86_64-w64-mingw32-gcc",
        "original": os.environ["CC"]
    }

    arg_build = "--build=" + system_type

    # purge old build files
    if os.path.exists(abs_build_common):
        rmtree(abs_build_common)
    os.makedirs(build_paths["i686"])
    os.makedirs(build_paths["x86_64"])

    for t in build_target:
        os.chdir(build_paths[t])
        arg_host = "--host=" + TARGET[t]
        arg_prefix = '--prefix=' + abs_prefix[t]
        arg_sysroot = '--with-sysroot=' + abs_prefix[t]
        # I cannot find where zeranoe set the PATH in his script, but this should be essential for CRT building
        print("Setting PATH and CC...")
        os.environ["PATH"] = path_var[t]
        os.environ["CC"] = cc_var[t]

        print("Configuring Mingw-w64 CRT ", t, "...")
        result = subprocess.run(["sh", config_path, arg_build, arg_host, arg_prefix, arg_sysroot],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Error configuring Mingw-w64 CRT", t)
            with open("config_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                return None
        # actual build
        cpu_count = str(run_nproc())
        print("Building Mingw-w64 CRT", t, "...")
        result = subprocess.run(["make", "-j", cpu_count], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Error building Mingw-w64 CRT", t)
            with open("build_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                return None
        # install
        print("Installing Mingw-w64 CRT", t, "...")
        result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Error installing Mingw-w64 CRT", t)
            with open("install_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                return None
        # a mysterious rename operation
        # is this necessary?
        print("Performing folder rename for unknown purpose... :-/")
        os.chdir(abs_prefix[t])
        from_folder = os.path.join("./", TARGET[t], "lib")
        to_folder = os.path.join("./", "lib")
        move(from_folder, to_folder)
        #rmtree(from_folder) # if moved sucessfully, the original is gone...
        #actually why not just make symlink in the top folder???
        os.chdir(os.path.join("./", TARGET[t]))
        if not os.path.exists("./lib"):
            os.symlink("../lib", "./lib")
        os.chdir(WORK_FOLDER)
        # restore PATH
        os.environ["PATH"] = path_var["original"]
        os.environ["CC"] = cc_var["original"]
    return True


def build_gcc2(build_folder):
    """
    A continuation of build_gcc1(). Just run make and make-install.
    :param build_folder: Use the returned tuple from build_gcc1()
    :return: True on success. None on failure.
    """
    global WORK_FOLDER
    os.chdir(WORK_FOLDER)
    cpu_cores = str(run_nproc())
    for folder in build_folder:
        os.chdir(folder)
        print("Building libGCC in ", folder, "...")
        result = subprocess.run(["make", "-j", cpu_cores, "all-target-libgcc"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode:
            print_error()
            print("Error building libGCC!")
            with open("build_error_libgcc.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
            return None

        print("Installing libGCC...")
        result = subprocess.run(["make", "install-target-libgcc"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode:
            print_error()
            print("Error installing libGCC!")
            with open("install_error_libgcc.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
            return None

        print("Building GCC in ", folder, "...")
        result = subprocess.run(["make", "-j", cpu_cores], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

        if result.returncode:
            print_error()
            print("Error building GCC!")
            with open("build_error_gcc.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
                if os.environ["CI"]:
                    print(message)
            return None

        print("Installing GCC...")
        result = subprocess.run(["make", "install-strip"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if result.returncode:
            print_error()
            print("Error installing GCC!")
            with open("install_error_gcc.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
            return None

        os.chdir(WORK_FOLDER)
    return True


def build_winpthreads(source_folder, build_folder, system_type):
    """
    Build mingw-w64 default threading library
    :param source_folder: Mingw-w64 source folder
    :param build_folder: Build location outside source folder
    :param system_type: string as returned by guess_config()
    :return: True on success. None on failure.
    """
    global WORK_FOLDER, LOCATIONS, TARGET
    os.chdir(WORK_FOLDER)
    config_source = os.path.join(os.path.abspath(source_folder), "mingw-w64-libraries/winpthreads/configure")
    build_common = os.path.join(os.path.abspath(build_folder), "winpthreads")
    abs_prefix ={
        "i686": os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"]),
        "x86_64": os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"])
    }
    path_var = {
        "i686": os.path.join(os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"]), "bin") + ":" + os.environ["PATH"],
        "x86_64": os.path.join(os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"]), "bin") + ":" + os.environ["PATH"],
        "original": os.environ["PATH"]
    }

    cc_var = {
        "i686": "i686-w64-mingw32-gcc",
        "x86_64": "x86_64-w64-mingw32-gcc",
        "original": os.environ["CC"]
    }
    # Reset the build folder
    if os.path.exists(build_common):
        rmtree(build_common)
    os.makedirs(build_common)
    # Architectures to loop through
    archs = ["i686", "x86_64"]
    # Loop and build
    for arch in archs:
        arch_build_folder = os.path.join(build_common, arch)
        os.makedirs(arch_build_folder)
        os.chdir(arch_build_folder)
        if not os.path.exists(config_source):
            print_error()
            print("winpthreads' configure script is not found!")
            return None
        arg_build = "--build=" + system_type
        arg_host = "--host=" + TARGET[arch]
        arg_prefix = "--prefix=" + abs_prefix[arch]
        # Set PATH and CC
        print("Setting PATH and CC...")
        os.environ["PATH"] = path_var[arch]
        os.environ["CC"] = cc_var[arch]

        # Run configure
        print("Configuring winpthreads ", arch, "...")
        result = subprocess.run(["sh", config_source, arg_build, arg_host, arg_prefix,
                                 "--enable-static", "--disable-shared"],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Failed to configure winpthreads ", arch)
            with open("config_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
            return None

        # Run Make
        print("Building winpthreads ", arch, "...")
        result = subprocess.run(["make"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Failed to build winpthreads ", arch)
            with open("build_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
            return None

        # Install
        print("Installing winpthreads ", arch, "...")
        result = subprocess.run(["make", "install"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode:
            print_error()
            print("Failed to install winpthreads ", arch)
            with open("install_error.log", "w") as f:
                message = result.stdout.decode("utf-8")
                f.write(message)
                message = result.stderr.decode("utf-8")
                f.write(message)
            return None

        os.environ["PATH"] = path_var["original"]
        os.environ["CC"] = cc_var["original"]
        os.chdir(WORK_FOLDER)
    return True


def generate_documentation():
    """
    Generate readme and helper scripts
    :return: None
    """
    global WORK_FOLDER, LOCATIONS, PERFORMANCE_COUNTER
    os.chdir(WORK_FOLDER)
    current_time = datetime.datetime.utcnow().isoformat()
    i686_prefix = os.path.abspath(LOCATIONS["mingw_w64_i686_prefix"])
    x86_64_prefix = os.path.abspath(LOCATIONS["mingw_w64_x86_64_prefix"])
    i686_bin = os.path.join(i686_prefix, "bin")
    x86_64_bin = os.path.join(x86_64_prefix, "bin")
    original_path = os.environ["PATH"]
    i686_new_path = i686_bin + ":" + original_path
    x86_64_new_path = x86_64_bin + ":" + original_path
    # Generate README
    readme_content = """\
    Mingw-w64 Toolchain built on {date}
    ===================================================================
    To use the 32-bit toolchain, add the following to the start of PATH
    {path32}
    RUN "source use32.sh" to automate 
    To use the 64-bit toolchain, add the following to the start of PATH
    {path64}
    RUN "source use64.sh" to do this for you
    The original PATH:
    {oldpath}
    RUN "source restore.sh" to get back original PATH
    
    Time consumed for building each component (in minutes)
    ===================================================================
    Downloading: {t_dl}
    Binutils: {t_binutils}
    Mingw-w64 Headers: {t_header}
    GMP: {t_gmp}
    MPFR: {t_mpfr}
    ISL: {t_isl}
    CLoog: {t_cloog}
    MPC: {t_mpc}
    GCC Bootstrap compiler: {t_gcc1}
    Mingw-w64 CRT: {t_crt}
    GCC: {t_gcc2}
    winpthreads: {t_winpthreads}
    
    """.format(date=current_time, path32=i686_bin, path64=x86_64_bin, oldpath=original_path,
               t_dl=PERFORMANCE_COUNTER["Download"].seconds/60,
               t_binutils=PERFORMANCE_COUNTER["Binutils"].seconds/60,
               t_header=PERFORMANCE_COUNTER["Header"].seconds/60,
               t_gmp=PERFORMANCE_COUNTER["GMP"].seconds/60,
               t_mpfr=PERFORMANCE_COUNTER["MPFR"].seconds/60,
               t_isl=PERFORMANCE_COUNTER["ISL"].seconds/60,
               t_cloog=PERFORMANCE_COUNTER["cloog"].seconds/60,
               t_mpc=PERFORMANCE_COUNTER["MPC"].seconds/60,
               t_gcc1=PERFORMANCE_COUNTER["GCC1"].seconds/60,
               t_crt=PERFORMANCE_COUNTER["CRT"].seconds/60,
               t_gcc2=PERFORMANCE_COUNTER["GCC2"].seconds/60,
               t_winpthreads=PERFORMANCE_COUNTER["winpthreads"].seconds/60)
    print("Generating readme.txt")
    with open("readme.txt", "w") as file:
        file.write(readme_content)
    # Generate helper scripts
    print("Generating helper scripts")
    use_script_template = """\
    #!/bin/sh
    export PATH="{new_path}"
    {arch}-w64-mingw32-gcc -v
    """

    restore_script_template = """\
    #!/bin/sh
    export PATH="{new_path}"
    printf "Original PATH restored\\n"
    """

    with open("use32.sh", "w") as file:
        file.write(use_script_template.format(new_path=i686_new_path, arch="i686"))
    st = os.stat("use32.sh")
    os.chmod("use32.sh", st.st_mode|stat.S_IXUSR|stat.S_IXGRP|stat.S_IXOTH)
    print("Use use32.sh to setup for 32bit toolchain\n")

    with open("use64.sh", "w") as file:
        file.write(use_script_template.format(new_path=x86_64_new_path, arch="x86_64"))
    st = os.stat("use64.sh")
    os.chmod("use64.sh", st.st_mode|stat.S_IXUSR|stat.S_IXGRP|stat.S_IXOTH)
    print("Use use64.sh to setup for 64bit toolchain\n")

    with open("restore.sh", "w") as file:
        file.write(restore_script_template.format(new_path=original_path))
    st = os.stat("restore.sh")
    os.chmod("restore.sh", st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("Use restore.sh to restore the PATH variable\n")
    print("Done!")
    return None


def main():

    global WORK_FOLDER, LOCATIONS, PERFORMANCE_COUNTER

    WORK_FOLDER = os.path.expandvars(WORK_FOLDER)
    WORK_FOLDER = os.path.expanduser(WORK_FOLDER)
    WORK_FOLDER = os.path.abspath(WORK_FOLDER)
    if os.path.exists(WORK_FOLDER):
        os.chdir(WORK_FOLDER)
    else:
        print("Creating work folder: ", WORK_FOLDER)
        os.makedirs(WORK_FOLDER)
        os.chdir(WORK_FOLDER)

    for item, path in LOCATIONS.items():
        ex_path = os.path.expandvars(path)
        ex_path = os.path.expanduser(ex_path)
        ex_path = os.path.abspath(ex_path)
        if not os.path.exists(ex_path):
            print("Creating: ", ex_path)
            os.makedirs(ex_path)
    SYSTEM_TYPE = guess_config()
    timer1 = datetime.datetime.utcnow()
    if __name__ == "__main__":
        thread_pool = mp.Pool(processes=2)
        thread_pool.map(ftp_get_by_component, FTP_DOWNLOADS)

        print("Downloaded from FTP")

        thread_pool.map(html_get_by_component, HTML_DOWNLOADS)
        thread_pool.close()
        thread_pool.join()
        print("Downloaded from HTTP")

    # Retrieve extracted folder path
    source_folders = {}
    all_components = ["binutils", "gcc", "gmp", "mpfr", "mpc", "isl", "cloog", "mingw-w64"]
    with os.scandir(LOCATIONS["pkg_dir"]) as it:
        for entry in it:
            if not entry.is_dir():
                continue
            for component in all_components:
                if component in entry.name:
                    source_folders[component] = entry.path
    print(source_folders)
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["Download"] = timer2 - timer1

    # build binutils
    timer1 = datetime.datetime.utcnow()
    state = build_binutils(source_folders["binutils"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE)
    if not state:
        print_error()
        print("Failed to build Binutils. Build process terminated.")
        return False
    else:
        print_ok()
        print("Built Binutils")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["Binutils"] = timer2 - timer1

    # build mingw headers
    timer1 = datetime.datetime.utcnow()
    state = build_mingw_header(source_folders["mingw-w64"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE)
    if not state:
        print_error()
        print("Failed to build mingw-w64 headers. Build process terminated.")
        return False
    else:
        print_ok()
        print("Built mingw-w64 headers")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["Header"] = timer2 - timer1

    # build gmp
    timer1 = datetime.datetime.utcnow()
    gmp_prefix = build_gmp(source_folders["gmp"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE)
    if not gmp_prefix:
        print_error()
        print("Failed to build GMP. Build process terminated.")
        return False
    else:
        print_ok()
        print("Built GMP")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["GMP"] = timer2 - timer1

    # build mpfr
    timer1 = datetime.datetime.utcnow()
    mpfr_prefix = build_mpfr(source_folders["mpfr"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE, gmp_prefix)
    if not mpfr_prefix:
        print_error()
        print("Failed to build MPFR. Build process terminated.")
        return False
    else:
        print_ok()
        print("Built MPFR")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["MPFR"] = timer2 - timer1

    # build isl
    timer1 = datetime.datetime.utcnow()
    isl_prefix = build_isl(source_folders["isl"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE, gmp_prefix)
    if not isl_prefix:
        print_error()
        print("Failed to build ISL. Build process terminated.")
        return False
    else:
        print_ok()
        print("Built ISL")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["ISL"] = timer2 -timer1

    # build cloog
    timer1 = datetime.datetime.utcnow()
    cloog_prefix = build_cloog(source_folders["cloog"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE, gmp_prefix)
    if not cloog_prefix:
        print_error()
        print("Failed to build cloog. Build process terminated.")
        return False
    else:
        print_ok()
        print("Built cloog")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["cloog"] = timer2 - timer1

    # build mpc
    timer1 = datetime.datetime.utcnow()
    mpc_prefix = build_mpc(source_folders["mpc"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE,
                           gmp_prefix, mpfr_prefix)
    if not mpc_prefix:
        print_error()
        print("Failed to build mpc. Build process terminated.")
        return False
    else:
        print_ok()
        print("Built mpc")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["MPC"] = timer2 - timer1

    # build gcc1
    timer1 = datetime.datetime.utcnow()
    path32, path64 = build_gcc1(source_folders["gcc"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE,
                                gmp_prefix, mpfr_prefix, isl_prefix, mpc_prefix)
    if not path32:
        print_error()
        print("Failed to build GCC 1 of 2. Build terminated.")
        return False
    else:
        print_ok()
        print("GCC 1 of 2")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["GCC1"] = timer2 - timer1

    # build crt
    timer1 = datetime.datetime.utcnow()
    state = build_crt(source_folders["mingw-w64"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE)
    if not state:
        print_error()
        print("Failed to build CRT. Build terminated.")
        return False
    else:
        print_ok()
        print("Built CRT")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["CRT"] = timer2 - timer1

    # build winpthreads
    timer1 = datetime.datetime.utcnow()
    state = build_winpthreads(source_folders["mingw-w64"], LOCATIONS["mingw_w64_build_dir"], SYSTEM_TYPE)
    if not state:
        print_error()
        print("Failed to build winpthreads. Build terminated.")
        return False
    else:
        print_ok()
        print("Built winpthreads")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["winpthreads"] = timer2 - timer1

    # build GCC 2 of 2
    timer1 = datetime.datetime.utcnow()
    state = build_gcc2([path32, path64])
    if not state:
        print_error()
        print("Failed to build GCC 2 of 2. Build terminated.")
        return False
    else:
        print_ok()
        print("GCC 2 of 2")
    timer2 = datetime.datetime.utcnow()
    PERFORMANCE_COUNTER["GCC2"] = timer2 - timer1

    # Generate readme and helper scripts
    generate_documentation()
    return True

# Run Main
init()
parser = argparse.ArgumentParser(description=HELP_TEXT.format(hl=Style.BRIGHT, chl=Style.RESET_ALL),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--prefix", "-p", default="~/MWTC/", help="Path to the sandbox folder[~/MWTC]")
parser.add_argument("--gcc", "-g", default="99", help="Version string for preferred GCC[99]")
parser.add_argument("--binutils", "-b", default="99", help="Version string for preferred Binutils[99]")
parser.add_argument("--mingw", "-m", default="99", help="Version string for preferred Mingw-w64[99]")
parser.add_argument("--sjlj", action='store_true', help="Use sjlj exception handling for win32. Default is dw2")
raw_args = parser.parse_args()
args = vars(raw_args)
WORK_FOLDER = args["prefix"]
PREFERRED_FOLDER_VERSION["gcc"] = args["gcc"]
PREFERRED_FILE_VERSION["gcc"] = args["gcc"]
PREFERRED_FOLDER_VERSION["binutils"] = args["binutils"]
PREFERRED_FILE_VERSION["binutils"] = args["binutils"]
PREFERRED_FILE_VERSION["mingw64"] = args["mingw"]
if args["sjlj"]:
    USE_SJLJ = True
else:
    USE_SJLJ = False

print("Testing GNU Server Mirrors...")
mirror, latency = select_mirror(GNU_MIRRORS, 1)
if mirror:
    GNU_SERVER = mirror
    print("Selecting mirror ", mirror, " with latency ", latency, "s")
else:
    print("Using default ", GNU_SERVER, 1)

print("Testing GCC Server Mirrors...")
mirror, latency = select_mirror(GCC_MIRRORS)
if mirror:
    GCC_SERVER = mirror
    print("Selecting mirror ", mirror, " with latency ", latency, "s")
else:
    print("Using default ", GCC_SERVER)


print("The sandbox would be: ", WORK_FOLDER)

ret = main()
if ret:
    print_ok()
    print("Everything built OK! Please read the readme file prior using the toolchain.")
else:
    print_error()
    print("Something goes wrong. Please check error logs.")
    sys.exit(1)
deinit()
