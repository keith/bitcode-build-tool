import os
import sys
import subprocess
import logging
import tempfile
import shutil
from multiprocessing.pool import ThreadPool
from translate import FrameworkUpgrader


class BitcodeBuildFailure(Exception):

    """Error happens during the build"""
    pass


class LogFormatter(logging.Formatter):

    """Customized logging formatter"""
    if sys.stdout.isatty():
        error_fmt = u"\033[1merror:\033[0;0m %(message)s\n"
        warning_fmt = u"\033[1mwarning:\033[0;0m %(message)s\n"
    else:
        error_fmt = u"error: %(message)s\n"
        warning_fmt = u"warning: %(message)s\n"

    debug_fmt = u"Debug: %(message)s"
    info_fmt = u"%(message)s"

    def __init__(self):
        super(LogFormatter, self).__init__(LogFormatter.info_fmt)

    def format(self, record):
        if record.levelno == logging.DEBUG:
            self._fmt = LogFormatter.debug_fmt
        elif record.levelno == logging.INFO:
            self._fmt = LogFormatter.info_fmt
        elif record.levelno == logging.WARNING:
            self._fmt = LogFormatter.warning_fmt
        elif record.levelno == logging.ERROR:
            self._fmt = LogFormatter.error_fmt
        else:
            self._fmt = LogFormatter.info_fmt
        return super(LogFormatter, self).format(record)


class LogDeobfuscator(object):

    """Deobfuscator the error messages"""
    def __init__(self, bcsymbolmap):
        self.input = bcsymbolmap
        self.bcsymbolmap = bcsymbolmap

    def selectUUID(self, uuid):
        if os.path.isdir(self.input):
            # directory
            self.bcsymbolmap = os.path.join(self.input, uuid + ".bcsymbolmap")
        else:
            # file
            self.bcsymbolmap = self.input

    def tryDeobfuscate(self, msg):
        if msg.find("__hidden#") == -1:
            return None
        if not os.path.isfile(self.bcsymbolmap):
            return None
        with open(self.bcsymbolmap, 'r') as f:
            symbol_map = f.readlines()
        while msg.find("__hidden#") != -1:
            index = msg.find("__hidden#")
            start_index = index + 9
            end_index = msg.find('_', start_index)
            number = msg[start_index:end_index]
            try:
                i = int(number)
                sym = symbol_map[i + 1].encode("UTF-8")
                new_msg = msg.replace("__hidden#" + number + "_",
                                      sym.strip())
            except ValueError, IndexError:
                return None
            if new_msg == msg:
                return None  # Don't infinite loop
            else:
                msg = new_msg
        return msg


class BuildEnvironment(object):

    """sdk/path related informations"""
    BUILD_TOOL_LIB_PATH = os.path.dirname(os.path.realpath(__file__))
    TOOL_PATH = os.path.realpath(
        os.path.join(
            BUILD_TOOL_LIB_PATH,
            "..",
            "..",
            "bin"))
    DEVELOPER_DIR = os.path.realpath(os.path.join(BUILD_TOOL_LIB_PATH,
                                                  "..", ".."))

    PLATFORM = {"iPhoneOS": "iphoneos",
                "iOS" : "iphoneos",
                "MacOSX": "macosx",
                "macOS" : "macosx",
                "AppleTVOS": "appletvos",
                "tvOS" : "appletvos",
                "watchOS": "watchos"}

    XCRUN = ["/usr/bin/xcrun"]
    XCRUN_ENV = {"TOOLCHAINS": "default"}
    if os.path.basename(DEVELOPER_DIR) == "Developer":
        XCRUN_ENV["DEVELOPER_DIR"] = DEVELOPER_DIR

    SUPPORTED_VERSION = set(["1.0"])

    def __init__(self, args=None):
        if args is None:
            return
        self.initState(args)

    def initState(self, args):
        # create console handler and set level to debug
        self.logger = logging.getLogger("bitcode-build-tool")
        ch = logging.StreamHandler(sys.stdout)
        if args.verbose:
            ch.setLevel(logging.DEBUG)
        elif args.verify:
            ch.setLevel(logging.WARNING)
        else:
            ch.setLevel(logging.INFO)
        # create formatter
        formatter = LogFormatter()
        # add formatter to ch
        ch.setFormatter(formatter)
        # add ch to logger
        self.logger.addHandler(ch)
        self.logger.setLevel(logging.DEBUG)
        # init variables
        self.sdk = args.sdk_path
        self.version = "1.0"
        self.platform = None
        self.tool_path = args.tool_path + [self.TOOL_PATH]
        self.addLibraryList(args.library_list)
        self.dylib_search_path = args.include
        self.translate_watchos = args.translate_watchos
        self.save_temp = args.save_temp
        self._tool_cache = dict()
        self.thread_pool = None
        self.verify_mode = args.verify
        self.thread_pool = ThreadPool(args.j)
        self.liblto = args.liblto
        self.compile_with_clang = args.compile_with_clang
        if self.liblto is not None and not os.path.exists(self.liblto):
            env.error("libLTO path does not exists: {}".format(self.liblto))
        self._temp_directories = []
        if args.symbol_map is not None:
            self.deobfuscator = LogDeobfuscator(args.symbol_map)
        else:
            self.deobfuscator = None
        self.logger.debug("SDK path: {}".format(self.sdk))
        self.logger.debug("PATH: {}".format(self.tool_path))

    def error(self, msg, exception=BitcodeBuildFailure("Bitcode Build Failure")):
        self.logger.error(msg)
        raise exception

    def warning(self, msg):
        self.logger.warning(msg)

    def log(self, msg):
        self.logger.info(msg)

    def debug(self, msg):
        self.logger.debug(msg)

    def getSDK(self):
        return self.sdk

    def addToolPath(self, paths):
        self.tool_path = paths + self.tool_path

    def setSDKPath(self, sdk):
        self.sdk = sdk

    def setParallelJobs(self, number):
        self.thread_pool = ThreadPool(number)

    @property
    def map(self):
        if self.thread_pool is None:
            return map
        else:
            return self.thread_pool.map

    def createTempDirectory(self, prefix="temp"):
        tempDir = tempfile.mkdtemp(prefix=prefix)
        self._temp_directories.append(tempDir)
        return tempDir

    def cleanupTempDirectories(self):
        if not self.save_temp:
            for d in self._temp_directories:
                shutil.rmtree(d, ignore_errors=True)

    def setPlatform(self, platform):
        self.debug("Setting platform to: {}".format(platform))
        if platform == "Unknown" or platform is None:
            if self.platform is not None:
                return
            else:
                self.error("Platform unknown, abort")
        if platform not in self.PLATFORM:
            self.error("Platform {} is not supported".format(platform))
        if self.platform is not None and self.platform != platform:
            self.warning(
                    "Change platform from {} to {}".format(
                        self.platform,
                        platform))
            self._tool_cache = dict()
        self.platform = platform
        self.XCRUN = ["/usr/bin/xcrun", "--sdk", self.getPlatform()]
        if self.sdk is None:
            cmd = self.XCRUN + ["--show-sdk-path"]
            try:
                sdk = subprocess.check_output(cmd, env=self.XCRUN_ENV)
            except subprocess.CalledProcessError:
                env.error("Could not infer SDK path")
            self.sdk = sdk.split()[0]
            self.debug("SDK PATH: {}".format(self.sdk))

    def getPlatform(self):
        if self.platform is not None:
            return self.PLATFORM[self.platform]
        else:
            self.error("Platform unset")

    def setVersion(self, vers):
        if vers in self.SUPPORTED_VERSION:
            self.version = vers
            self.debug("Bitcode bundle version: {}".format(vers))
        else:
            self.error("Bitcode bundle version not supported: {}".format(vers))

    def getTool(self, name):
        """Get tool from build environment"""
        try:
            tool = self._tool_cache[name]
        except KeyError:
            for path in self.tool_path:
                tool = os.path.join(path, name)
                if os.path.isfile(tool):
                    self.debug("Using: {}".format(tool))
                    self._tool_cache[name] = tool
                    return tool
                else:
                    continue
            # fall back plan, always uses default toolchain
            self.debug("Inferring {} from xcrun".format(name))
            cmd = self.XCRUN + ["-f", name]
            try:
                out = subprocess.check_output(cmd, env=self.XCRUN_ENV)
            except subprocess.CalledProcessError:
                pass
            else:
                tool = out.split()[0]
                self.debug("Using: {}".format(tool))
                self._tool_cache[name] = tool
                return tool
            self.error("Cannot find {} in PATH".format(name))
        else:
            return tool

    def addDylibSearchPath(self, path):
        self.dylib_search_path.append(os.path.realpath(path))

    def addLibraryList(self, filename):
        if filename is None:
            self._dylib_list = dict()
            return
        if os.path.isfile(filename):
            with open(filename) as f:
                lib_list = [line.rstrip('\n') for line in f]
                self._dylib_list = dict(
                    zip([os.path.basename(x) for x in lib_list],
                        [os.path.realpath(x) for x in lib_list]))
            self.debug("Library Seach List:")
            self.debug(self._dylib_list)
        else:
            self.error("library list doesn't exist: %s".format(filename))

    def findLibraryInDir(self, directory, lib, framework_dir=False):
        """Search a directory to find the library"""
        lib_path = os.path.join(directory, lib)
        if os.path.isfile(lib_path):
            return lib_path
        # Remap the file type (stubs <-> tbd file)
        if lib_path.endswith(".dylib"):
            lib_path = lib_path[:-6] + ".tbd"
        elif lib_path.endswith(".tbd"):
            if os.path.basename(lib_path).startswith("lib"):
                lib_path = lib_path[:-4] + ".dylib"
            else:
                lib_path = lib_path[:-4]
        else:
            lib_path = lib_path + ".tbd"
        if os.path.isfile(lib_path):
            return lib_path
        # check the framework path if needed
        if framework_dir:
            return self.findLibraryInDir(
                    os.path.join(directory, os.path.splitext(lib)[0] +
                                 ".framework"),
                    lib, False)
        # return None if not found
        return None

    def resolveDylibs(self, arch, lib, allow_failure=False):
        # verify mode, always succeed
        if self.verify_mode:
            return lib
        # do all the path computation with raw encoding
        if isinstance(lib, unicode):
            lib = lib.encode('utf-8')
        # Search for system framework and dylibs
        if lib.startswith("{SDKPATH}"):
            # Check if framework upgrading is needed
            lib = FrameworkUpgrader.translate(lib[9:])
            # this is mapped to one of the real sdk
            lib_path = self.sdk + lib
            found = self.findLibraryInDir(os.path.dirname(lib_path),
                                          os.path.basename(lib_path))
            if found:
                self.debug("Found framework/dylib: {}".format(found))
                return found
        # assume this is from user (aka Payload)
        # strip the path if fall throught from system frameworks
        libname = os.path.basename(lib)
        # search the dylib list first
        if libname in self._dylib_list:
            return self._dylib_list[libname]
        # search files in the -L path then
        toolchain_dylib_path = []
        # add clang libaries for the platform to search path
        toolchain_dylib_path.append(os.path.dirname(self.getlibclang_rt(arch)))
        # add the swift libraries for the platform to search path
        toolchain_dylib_path.append(os.path.join(self.getToolchainDir(),
                                                 "usr", "lib", "swift",
                                                 self.getPlatform()))
        # search the SDK as well
        sdk_search_path = [os.path.join(env.getSDK(), "usr", "lib")]
        sdk_search_path.append(os.path.join(env.getSDK(), "System",
                                            "Library", "Frameworks"))
        dylib_search_path = (self.dylib_search_path + toolchain_dylib_path +
                             sdk_search_path)
        for search_path in dylib_search_path:
            check_path = self.findLibraryInDir(search_path, libname, True)
            if check_path:
                self.debug(u"Found framework/dylib: {}".format(unicode(check_path, "utf-8")))
                return check_path
        if allow_failure:
            self.warning(u"{} not found in dylib search path".format(unicode(libname, "utf-8")))
            return None
        else:
            unicode_search_path = u", ".join(u'"{}"'.format(unicode(c, 'utf-8')) for c in dylib_search_path)
            self.debug(u"Search Path: {}".format(unicode_search_path))
            self.error(u"{} not found in dylib search path".format(unicode(libname, "utf-8")))

    def getToolchainDir(self):
        """Find toolchain directory"""
        try:
            tool = self._tool_cache["toolchain_dir"]
        except KeyError:
            # lookup clang for toolchain_dir
            clang_path = self.getTool("clang")
            toolchain_path = os.path.realpath(
                os.path.join(
                    os.path.dirname(clang_path),
                    "..",
                    ".."))
            self._tool_cache["toolchain_dir"] = toolchain_path
            return toolchain_path
        else:
            return tool

    def getlibclang_rt(self, arch):
        """Use a trick to get the correct libclang_rt"""
        try:
            tool = self._tool_cache["libclang_rt"]
        except KeyError:
            clang = self.getTool("clang")
            out = subprocess.check_output(
                [clang, "-arch", arch, "/dev/null",
                    "-isysroot", self.getSDK(), "-###"],
                stderr=subprocess.STDOUT)
            clang_rt = out.split('\"')[-2]
            self._tool_cache["libclang_rt"] = clang_rt
            return clang_rt
        else:
            return tool

    def getlibSwiftPath(self, arch):
        try:
            # try to look for libswiftCore.dylib
            swiftcore = self.resolveDylibs(arch, "libswiftCore.dylib")
        except BitcodeBuildFailure:
            return None
        else:
            swiftlib_path = os.path.dirname(swiftcore)
            self.debug(u"Found swift dylib path: {}".format(unicode(swiftlib_path, "utf-8")))
            return swiftlib_path

    def satifiesLinkerVersion(self, version):
        try:
            version_tuple = self._tool_cache["ld_version"]
        except KeyError:
            linker_vers = subprocess.check_output([self.getTool('ld'), '-v'],
                                                  stderr=subprocess.STDOUT)
            version_string = linker_vers.split('\n')[0].split('-')[-1]
            try:
                version_tuple = tuple(map(int, version_string.split('.')))
            except ValueError:
                # fail to detect version number, return false
                return False
            else:
                self._tool_cache["ld_version"] = version_tuple
        check_tuple = tuple(map(int, version.split('.')))
        return version_tuple >= check_tuple

    def setUUID(self, uuid):
        if self.deobfuscator is not None:
            self.deobfuscator.selectUUID(uuid)

env = BuildEnvironment()
