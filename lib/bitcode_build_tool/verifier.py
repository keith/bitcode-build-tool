"""This module verify the options in the bitcode are valid"""
import argparse


# The exception for verificaion failed
class VerifyError(Exception):
    pass


class FlagMatcher:
    def match(self, option):
        return option


class OptionVerifier(argparse.ArgumentParser):

    """Overwrite the ArgumentParser to verify options from command"""

    def __init__(self, **kwargs):
        super(OptionVerifier, self).__init__(**kwargs)
        # A hack to make python argparse behaves more like OptParser in
        # clang/ld/swift so options like -mllvm/-Xllvm can take an option
        # begins with '-'
        self._negative_number_matcher = FlagMatcher()

    def error(self, message):
        """Overwrite the error method so SystemExit is not raised"""
        self._error_msg = message
        raise VerifyError("Verification Failed")

    def verify(self, options):
        """Return whether the list of options are legal"""
        try:
            self.parse_args(options)
        except VerifyError:
            return False
        else:
            # Clear the error message
            self._error_msg = ''
            return True

    @property
    def error_msg(self):
        """Return the error message if there is one"""
        return getattr(self, '_error_msg', '')


class ClangOptVerifier(OptionVerifier):

    """clang option verifier"""

    def __init__(self):
        # clang option parser
        super(ClangOptVerifier, self).__init__(prog='clang', add_help=False)
        # Output options
        self.add_argument('-emit-obj', action='store_true', required=True)
        self.add_argument('-triple', type=str)
        # Optimizations
        self.add_argument('-O')
        self.add_argument('-disable-llvm-optzns', action='store_true')
        self.add_argument('-disable-llvm-passes', action='store_true')
        # Codegen/Asm options
        self.add_argument('-mdisable-tail-calls', action='store_true')
        # FP options
        self.add_argument('-mlimit-float-precision', action='store_true')
        self.add_argument('-menable-no-infs', action='store_true')
        self.add_argument('-menable-no-nans', action='store_true')
        self.add_argument('-fmath-errno', action='store_true')
        self.add_argument('-menable-unsafe-fp-math', action='store_true')
        self.add_argument('-fno-signed-zeros', action='store_true')
        self.add_argument('-freciprocal-math', action='store_true')
        self.add_argument('-ffp-contract')
        self.add_argument('-target-abi')
        self.add_argument('-mfloat-abi')
        self.add_argument('-mllvm')


class LinkerOptVerifier(OptionVerifier):

    """linker option verifier"""

    def __init__(self):
        super(LinkerOptVerifier, self).__init__(prog='ld', add_help=False)
        # Output kind
        self.add_argument('-execute', action='store_true')
        self.add_argument('-dylib', action='store_true')
        self.add_argument('-r', action='store_true')
        # Dylib options
        self.add_argument('-compatibility_version')
        self.add_argument('-current_version')
        self.add_argument('-install_name')
        # Platform versions
        self.add_argument('-ios_version_min')
        self.add_argument('-ios_simulator_version_min')
        self.add_argument('-watchos_version_min')
        self.add_argument('-watchos_simulator_version_min')
        self.add_argument('-macosx_version_min')
        self.add_argument('-tvos_version_min')
        self.add_argument('-tvos_simulator_version_min')
        # Other settings
        self.add_argument('-rpath', action='append')
        self.add_argument('-objc_abi_version')
        # -e will make argparse accept all args begin with -e
        # that is too general so it is handled elsewhere
        # self.add_argument('-e')
        self.add_argument('-executable_path')
        self.add_argument('-exported_symbols_list')
        self.add_argument('-unexported_symbols_list')
        self.add_argument('-order_file')
        self.add_argument('-source_version')
        self.add_argument('-no_implicit_dylibs', action='store_true')
        self.add_argument('-dead_strip', action='store_true')
        self.add_argument('-export_dynamic', action='store_true')
        self.add_argument('-application_extension', action='store_true')
        self.add_argument('-add_source_version', action='store_true')
        self.add_argument('-no_objc_category_merging', action='store_true')
        self.add_argument('-sectcreate', nargs=3)

    def verify(self, options):
        # delete -e and its argument
        try:
            entry_index = options.index('-e')
        except ValueError:
            pass
        else:
            options = options[:entry_index] + options[entry_index + 2:]
        return super(LinkerOptVerifier, self).verify(options)


class SwiftOptVerifier(OptionVerifier):

    """swift options verifier"""

    def __init__(self):
        super(SwiftOptVerifier, self).__init__(prog='swift', add_help=False)
        self.add_argument('-emit-object', action='store_true')
        self.add_argument('-target')
        self.add_argument('-target-cpu')
        self.add_argument('-Ounchecked', action='store_true')
        self.add_argument('-Onone', action='store_true')
        self.add_argument('-Osize', action='store_true')
        self.add_argument('-Oplayground', action='store_true')
        self.add_argument('-O', action='store_true')
        self.add_argument('-c', action='store_true')
        self.add_argument('-parse-stdlib', action='store_true')
        self.add_argument('-module-name')
        self.add_argument('-disable-llvm-optzns', action='store_true')
        # verify that the -Xllvm only takes -aarch64-use-tbi option added by
        # swift driver
        self.add_argument('-Xllvm', choices=['-aarch64-use-tbi'])

    def verify(self, options):
        return super(SwiftOptVerifier, self).verify(options)

# Initialized verifier
# For sequential uses
clang_option_verifier = ClangOptVerifier()
ld_option_verifier = LinkerOptVerifier()
swift_option_verifier = SwiftOptVerifier()
