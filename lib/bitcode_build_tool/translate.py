"""Translates various options/names for build compatibility"""
import os


class ClangCC1Translator:
    ARG_MAP = {
        "apcs-vfp": "aapcs16"
    }

    TO_OPTIMIZED = {
        "-disable-llvm-optzns": "-O1",
        "-disable-llvm-passes": "-O1",
        "-O0": "-O1",
    }

    @staticmethod
    def upgrade(opts, arch):
        new_opts = [ClangCC1Translator.ARG_MAP[x]
                    if x in ClangCC1Translator.ARG_MAP else x
                    for x in opts]
        new_opts.extend(ClangCC1Translator.compatibility_flags(arch))
        return new_opts

    @staticmethod
    def compatibility_flags(arch):
        if arch.startswith("armv7"):
            return ["-mllvm", "-arm-bitcode-compatibility", "-mllvm", "-fast-isel=0"]
        else:
            return []

    @staticmethod
    def append_translate_args(opt):
        opt.extend(["-mllvm", "-aarch64-watch-bitcode-compatibility"])
        return opt

    @staticmethod
    def add_optimization(opts):
        opts_map = ClangCC1Translator.TO_OPTIMIZED
        return [opts_map[x] if x in opts_map else x for x in opts]

    @staticmethod
    def translate_triple(opts):
        new_opts = []
        for opt in opts:
            if opt == "aapcs16":
                new_opts.append("darwinpcs")
            elif opt.startswith("thumbv7k"):
                new_opts.append(opt.replace("thumbv7k", "arm64_32"))
            elif opt.startswith("armv7k"):
                new_opts.append(opt.replace("armv7k", "arm64_32"))
            else:
                new_opts.append(opt)
        return ClangCC1Translator.append_translate_args(new_opts)


class SwiftArgTranslator:

    TO_CLANG = {
        "-frontend": "-cc1",
        "-emit-object": "-emit-obj",
        "-target": "-triple",
        "-Xllvm": "-mllvm",
        "-Onone": "-O0",
        "-Oplayground" : "-O1",
        "-Osize" : "-Oz",
        "-Ounchecked" : "-Os",
        "-O": "-Os",
        # meaningless but just map to some clang cc1 option
        "-module-name": "-main-file-name",
        "-parse-stdlib": "-stdlib=libc++"
    }

    TO_OPTIMIZED = {
        "-disable-llvm-optzns": "-O",
        "-disable-llvm-passes": "-O",
        "-Onone": "-O",
    }

    @staticmethod
    def upgrade(opts, arch):
        opts.extend(SwiftArgTranslator.compatibility_flags(arch))
        return opts

    @staticmethod
    def translate_to_clang(opts):
        opts_map = SwiftArgTranslator.TO_CLANG
        return [opts_map[x] if x in opts_map else x for x in opts]

    @staticmethod
    def add_optimization(opts):
        opts_map = SwiftArgTranslator.TO_OPTIMIZED
        return [opts_map[x] if x in opts_map else x for x in opts]

    @staticmethod
    def compatibility_flags(arch):
        if arch.startswith("armv7"):
            return ["-Xllvm", "-arm-bitcode-compatibility", "-Xllvm", "-fast-isel=0"]
        else:
            return []

    @staticmethod
    def append_translate_args(opt):
        opt.extend(["-Xllvm", "-aarch64-watch-bitcode-compatibility"])
        return opt

    @staticmethod
    def translate_triple(opts):
        new_opts = []
        for opt in opts:
            if opt == "aapcs16":
                new_opts.append("darwinpcs")
            elif opt.startswith("thumbv7k"):
                new_opts.append(opt.replace("thumbv7k", "arm64_32"))
            elif opt.startswith("armv7k"):
                new_opts.append(opt.replace("armv7k", "arm64_32"))
            else:
                new_opts.append(opt)
        return SwiftArgTranslator.append_translate_args(new_opts)


class FrameworkUpgrader:

    """Handle system frameworks/dylibs upgrade"""
    LIBRARY_MAP = {
        "/usr/lib/libextension":
            "/System/Library/Frameworks/Foundation.framework/Foundation"
    }

    @staticmethod
    def translate(lib):
        libname = os.path.splitext(lib)[0]
        return FrameworkUpgrader.LIBRARY_MAP.get(libname, lib)
