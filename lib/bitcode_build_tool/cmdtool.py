import os
import subprocess
import datetime
import sys

from buildenv import env, BitcodeBuildFailure


class Cmd(object):

    """Runs from subprocess"""
    BOLD_START = u"\033[1m"
    BOLD_END = u"\033[0;0m"

    def __init__(self, cmd, working_dir):
        self.working_dir = working_dir
        self.cmd = cmd
        self.stdout = None
        self.returncode = 0

    def __repr__(self):
        if sys.stdout.isatty():
            info = u"{}{}{}: cd {}\n".format(self.BOLD_START, type(self).__name__,
                                             self.BOLD_END, self.working_dir)
        else:
            info = u"{}: cd {}\n".format(type(self).__name__, self.working_dir)
        cmd_string = u" ".join(u'"{}"'.format(c if isinstance(c, unicode) else unicode(c, 'utf-8')) for c in self.cmd)
        if self.stdout is None:
            return u"{}{}\n".format(info, cmd_string)
        else:
            return u"{}{}\n-= Output =-\n{}Exited with {}\n".format(info, cmd_string,
                                                                    unicode(self.stdout, 'utf-8'),
                                                                    self.returncode)

    def run(self):
        self.run_cmd(False)
        return self

    def run_cmd(self, xfail=False):
        """Run a command in a working directory."""
        start_time = datetime.datetime.now()
        try:
            if not os.environ.get('TESTING', False):
                out = subprocess.check_output(self.cmd,
                                              stderr=subprocess.STDOUT,
                                              cwd=self.working_dir)
            else:
                out = "Skipped for testing mode."
            end_time = datetime.datetime.now()
        except subprocess.CalledProcessError as e:
            self.returncode = e.returncode
            self.stdout = e.output
            if xfail:
                env.log(self)
            else:
                env.error(self)
        else:
            self.returncode = 0
            self.stdout = out
            env.log(self)
            env.debug("Command took {} seconds".format(
                (end_time - start_time).seconds))


class CompileCmd(Cmd):

    """Compile command that doesn't run under verify mode"""

    def run_cmd(self, xfail=False):
        if not env.verify_mode:
            super(CompileCmd, self).run_cmd(xfail)


class Clang(CompileCmd):

    """Run clang command"""

    def __init__(self, bitcode, output, working_dir=os.getcwd()):
        self._clang = env.getTool("clang")
        self.input = bitcode
        self.output = output
        self.input_type = "ir"
        super(Clang, self).__init__([self._clang, "-cc1"], working_dir)

    def addArgs(self, args):
        self.cmd.extend(args)

    def setInputType(self, ty):
        self.input_type = ty

    def run(self):
        self.cmd.extend(["-x", self.input_type])
        self.cmd.append(self.input)
        self.cmd.extend(["-o", self.output])
        self.run_cmd(False)
        return self


class Swift(CompileCmd):

    """Run swiftc command"""

    def __init__(self, bitcode, output, working_dir=os.getcwd()):
        self._swift = env.getTool("swiftc")
        self.input = bitcode
        self.output = output
        super(Swift, self).__init__([self._swift, "-frontend"], working_dir)

    def addArgs(self, args):
        self.cmd.extend(args)

    def run(self, dry_run=False):
        self.cmd.append(self.input)
        self.cmd.extend(["-o", self.output])
        self.run_cmd(False)
        return self


class Ld(CompileCmd):

    """Run Ld command"""

    def __init__(self, output="a.out", working_dir=os.getcwd()):
        self._ld = env.getTool("ld")
        self.output = output
        super(Ld, self).__init__([self._ld], working_dir)

    def addArgs(self, args):
        self.cmd.extend(args)

    def run(self, dry_run=False):
        self.cmd.extend(["-o", self.output])
        try:
            self.run_cmd(False)
        except BitcodeBuildFailure:
            if env.deobfuscator is not None:
                translated_msg = env.deobfuscator.tryDeobfuscate(self.stdout)
                if translated_msg is not None:
                    env.log("Translation of the obfuscated symbols "
                            "using the bitcode symbol map:\n\n" +
                            translated_msg)
            raise BitcodeBuildFailure
        else:
            return self


class Lipo(Cmd):

    """Run Lipo command"""

    def __init__(self, working_dir=os.getcwd()):
        self._lipo = env.getTool("lipo")
        super(Lipo, self).__init__([self._lipo], working_dir)

    def run(self):
        self.run_cmd(False)
        return self


class MachoInfo(Lipo):

    """Get Macho Type"""

    def __init__(self, input, working_dir=os.getcwd()):
        super(MachoInfo, self).__init__(working_dir)
        self.cmd = [self._lipo, "-info", input]

    def run(self):
        """check the input info, this command can fail"""
        self.run_cmd(True)
        return self


class VerifyArch(Lipo):

    """Verify MachO contains slice"""

    def __init__(self, arch, input, working_dir=os.getcwd()):
        super(VerifyArch, self).__init__(working_dir)
        self.cmd = [self._lipo, input, "-verify_arch", arch]


class ReplaceSlice(Lipo):

    """replace slice in MachO"""

    def __init__(self, input, arch, file, working_dir=os.getcwd()):
        super(ReplaceSlice, self).__init__(working_dir)
        self.cmd = [self._lipo, input, "-replace", arch,
                    file, "-output", input]


class AddSlice(Lipo):

    """Add a slice to MachO"""

    def __init__(self, input, file, working_dir=os.getcwd()):
        super(AddSlice, self).__init__(working_dir)
        self.cmd = [self._lipo, "-create", input, file, "-output", input]


class ExtractSlice(Lipo):

    """Extract slice"""

    def __init__(self, input, arch, output, working_dir=os.getcwd()):
        super(ExtractSlice, self).__init__(working_dir)
        self.cmd = [self._lipo, input, "-thin", arch, "-output", output]


class LipoCreate(Lipo):

    def __init__(self, inputs, output, working_dir=os.getcwd()):
        super(LipoCreate, self).__init__(working_dir)
        self.cmd.extend(["-create"] + inputs + ["-output", output])


class CopyFile(Cmd):

    """File Copy"""

    def __init__(self, src, dst, working_dir=os.getcwd()):
        super(CopyFile, self).__init__(
            ["/usr/bin/ditto", src, dst], working_dir)


class ExtractXAR(Cmd):

    def __init__(self, input, output, working_dir=os.getcwd()):
        super(ExtractXAR, self).__init__([env.getTool("segedit"), input,
                                          "-extract", "__LLVM",
                                          "__bundle", output], working_dir)

    def run(self):
        self.run_cmd(True)
        return self


class Dsymutil(Cmd):

    def __init__(self, input, output, working_dir=os.getcwd()):
        super(Dsymutil, self).__init__(
            [env.getTool("dsymutil"), input, "-o", output], working_dir)


class DsymMap(Cmd):

    def __init__(self, input, mapfile, working_dir=os.getcwd()):
        super(DsymMap, self).__init__(
            [env.getTool("dsymutil"), "--symbol-map", mapfile, input],
            working_dir)


class StripSymbols(Cmd):

    def __init__(self, input, working_dir=os.getcwd()):
        super(StripSymbols, self).__init__([env.getTool("strip"), input],
                                           working_dir)


class StripDebug(Cmd):

    def __init__(self, input, strip_swift, working_dir=os.getcwd()):
        if strip_swift:
            strip_flags = "-STx"
        else:
            strip_flags = "-Sx"
        super(StripDebug, self).__init__([env.getTool("strip"), strip_flags,
                                          input],
                                         working_dir)


class GetUUID(Cmd):

    def __init__(self, input, working_dir=os.getcwd()):
        super(GetUUID, self).__init__([env.getTool("dwarfdump"), "-u", input],
                                      working_dir)


class RewriteArch(Cmd):
    def __init__(self, input, output, deployment_target, working_dir=os.getcwd()):
        new_triple = "arm64_32-apple-watchos"
        if deployment_target is not None:
            new_triple += deployment_target
        super(RewriteArch, self).__init__([env.getTool("clang"), "-target", new_triple, "-c", "-Xclang",
                                           "-disable-llvm-passes", "-emit-llvm", "-x", "ir", input, "-o", output],
                                          working_dir)
