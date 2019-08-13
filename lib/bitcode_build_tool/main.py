#!/usr/bin/env python
"""Inspect an IPA file with bitcode, and recompile it."""

import sys
import os
import argparse

import cmdtool
from macho import Macho, MachoType
from buildenv import env


def parse_args(args):
    """Get the command line arguments, and make sure they are correct."""

    parser = argparse.ArgumentParser(
        description="Recompile MachO from bitcode.", )

    parser.add_argument("input_macho_file", type=str,
                        help="The input MachO file contains bitcode section")

    parser.add_argument("-o", "--output", type=str, dest="output",
                        default="a.out", help="Output file")
    parser.add_argument("-L", "--library", action="append", dest="include",
                        default=[], help="Dylib search path")
    parser.add_argument("-t", "--tool", action="append", dest="tool_path",
                        default=[], help="Additional tool search path")
    parser.add_argument("--sdk", type=str, dest="sdk_path",
                        help="SDK path")
    parser.add_argument("--generate-dsym", type=str, dest="dsym_output",
                        help="Generate dSYM for the binary and output to path")
    parser.add_argument("--library-list", type=str, dest="library_list",
                        help="A list of dynamic libraries to link against")
    parser.add_argument("--symbol-map", type=str, dest="symbol_map",
                        help="bcsymbolmap file or directory")
    parser.add_argument("--strip-swift-symbols", action="store_true",
                        dest="strip_swift", help="Strip out Swift symbols")
    parser.add_argument("--translate-watchos", action="store_true",
                        dest="translate_watchos", help="translate armv7k watch app to arm64_32")
    parser.add_argument("--save-temps", action="store_true", dest="save_temp",
                        help="leave all the temp directories behind")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--verify", action="store_true",
                        help="Verify the bundle without compiling")
    parser.add_argument("-j", "--threads", metavar="N", type=int,
                        default=1, dest="j",
                        help="How many jobs to execute at once. (default=1)")
    parser.add_argument("--liblto", type=str, dest="liblto", default=None,
                        help="libLTO.dylib path to overwrite the default")
    parser.add_argument("--compile-swift-with-clang", action="store_true",
                        dest="compile_with_clang", help=argparse.SUPPRESS)

    args = parser.parse_args(args[1:])

    return args


def main(args=None):
    """Run the program, can override args for testing."""
    if args is None:
        args = sys.argv
    args = parse_args(args)

    try:
        env.initState(args)

        if not os.path.isfile(args.input_macho_file):
            env.error(
                u"Input macho file doesn't exist: {}".format(
                    args.input_macho_file))
        if args.symbol_map is not None and args.dsym_output is None:
            env.error("--symbol-map can only be used "
                      "together with --generate-dsym")
        if args.symbol_map is not None and not os.path.exists(args.symbol_map):
            env.error(u"path passed to --symbol-map doesn't exists: {}".format(
                    args.symbol_map))

        input_macho = Macho(args.input_macho_file)
        if input_macho == MachoType.Error:
            env.error(u"Input is not a macho file: {}".format(
                    args.input_macho_file))

        map(input_macho.buildBitcode, input_macho.getArchs())

        if (args.dsym_output is not None and
            not any([x.contain_symbols for x in input_macho.output_slices]) and
                args.symbol_map is None):
            env.warning(
                u"Cannot genarte useful dsym from input macho file: {}".format(
                    unicode(args.input_macho_file, 'utf-8')))

        if not args.verify:
            input_macho.installOutput(args.output)

            if args.dsym_output is not None:
                cmdtool.Dsymutil(args.output, args.dsym_output).run()
                input_macho.writeDsymUUIDMap(args.dsym_output)

            if args.symbol_map is not None:
                cmdtool.DsymMap(args.dsym_output, args.symbol_map).run()

            # always strip the output
            if input_macho.is_executable:
                cmdtool.StripSymbols(args.output).run()
            else:
                cmdtool.StripDebug(args.output, args.strip_swift).run()
    finally:
        env.cleanupTempDirectories()

if __name__ == "__main__":
    main()
