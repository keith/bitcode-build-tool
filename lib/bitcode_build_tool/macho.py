import os
import cmdtool
import shutil

from bundle import BitcodeBundle
from buildenv import env


class MachoType(object):

    """Enum of all macho types"""

    Error = 0
    Thin = 1
    Fat = 2

    @staticmethod
    def getType(path):
        with open(path, "r") as f:
            magic = f.read(4)
            if (magic == "cafebabe".decode("hex") or
                    magic == "bebafeca".decode("hex")):
                return MachoType.Fat
            elif (magic == "feedface".decode("hex") or
                    magic == "feedfacf".decode("hex") or
                    magic == "cefaedfe".decode("hex") or
                    magic == "cffaedfe".decode("hex")):
                return MachoType.Thin
            else:
                return MachoType.Error

    @staticmethod
    def getArch(path):
        macho_info = cmdtool.MachoInfo(path).run()
        if macho_info.returncode != 0:
            env.error(u"{} is not valid macho file".format(path))
        elif macho_info.stdout.startswith("Non-fat"):
            arch = macho_info.stdout.split()[-1]  # Last phrase is arch
            return [arch]
        else:
            message = macho_info.stdout.split()
            try:
                begin = message.index("are:") + 1
            except ValueError:
                env.error("Cound not detect architecture of the MachO file")
            else:
                return message[begin:]

    @staticmethod
    def getUUID(path):
        uuid_info = cmdtool.GetUUID(path).run()
        uuid_map = dict()
        for line in uuid_info.stdout.split("\n"):
            if len(line) > 0:
                arch = line.split()[2].lstrip("(").rstrip(")")
                uuid = line.split()[1]
                uuid_map[arch] = uuid
        return uuid_map


class Macho(object):

    """Class represent a macho input"""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self._slice_cache = dict()
        self._bitcode_cache = dict()
        self._temp_dir = env.createTempDirectory(prefix=self.name)
        self.type = MachoType.getType(path)
        self.archs = MachoType.getArch(path)
        self.uuid = MachoType.getUUID(path)
        self.output_uuid = None
        self.output_slices = []

    def getArchs(self):
        return self.archs

    def getSlice(self, arch):
        if arch not in self.archs:
            env.error(
                u"Requested arch {} doesn't exist in {}".format(
                                                        arch, self.path))
        if self.type == MachoType.Thin:
            return self.path
        elif self.type == MachoType.Fat:
            try:
                file = self._slice_cache[arch]
            except KeyError:
                extract_path = os.path.join(self._temp_dir,
                                            self.name + "." + arch)
                extract_job = cmdtool.ExtractSlice(self.path, arch,
                                                   extract_path).run()
                if extract_job.returncode != 0:
                    env.error(u"Cannot extract arch {} from {}".format(
                                                            arch, self.path))
                self._slice_cache[arch] = extract_path
                return extract_path
            else:
                return file

    def getXAR(self, arch):
        try:
            file = self._bitcode_cache[arch]
        except KeyError:
            macho_thin = self.getSlice(arch)
            extract_path = os.path.join(
                self._temp_dir,
                self.name + "." + arch + ".xar")
            extract_xar = cmdtool.ExtractXAR(macho_thin, extract_path).run()
            if extract_xar.returncode != 0:
                env.error(
                    u"Cannot extract bundle from {} ({})".format(
                        self.path, arch))
            if os.stat(extract_path).st_size <= 1:
                env.error(
                    u"Bundle only contains bitcode-marker {} ({})".format(
                        self.path, arch))
            self._bitcode_cache[arch] = extract_path
            return extract_path
        else:
            return file

    def buildBitcode(self, arch):
        output_path = os.path.join(self._temp_dir,
                                   self.name + "." + arch + ".out")
        bundle = self.getXAR(arch)
        env.setUUID(self.uuid[arch])
        bitcode_bundle = BitcodeBundle(arch, bundle, output_path).run()
        self.output_slices.append(bitcode_bundle)
        return bitcode_bundle

    def installOutput(self, path):
        if len(self.output_slices) == 0:
            env.error("Install failed: no bitcode build yet")
        elif len(self.output_slices) == 1:
            try:
                shutil.move(self.output_slices[0].output, path)
            except IOError:
                env.error(u"Install failed: can't create {}".format(path))
        else:
            cmdtool.LipoCreate([x.output for x in self.output_slices],
                               path).run()
        self.output_uuid = MachoType.getUUID(path)

    @property
    def is_executable(self):
        return all([isinstance(x, BitcodeBundle) and x.is_executable
                    for x in self.output_slices])

    def writeDsymUUIDMap(self, bundle_path):
        resource_dir = os.path.join(bundle_path, "Contents", "Resources")
        plist_template = u"""<?xml version="1.0" encoding="UTF-8"?>""" \
                         """<!DOCTYPE plist PUBLIC""" \
                         """ "-//Apple//DTD PLIST 1.0//EN" """ \
                         """"http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
   <key>DBGOriginalUUID</key>
   <string>{UUID}</string>
</dict>
</plist>"""
        if not os.access(resource_dir, os.W_OK):
            env.error(u"Dsym bunlde not writeable: {}".format(bundle_path))
        for arch in self.archs:
            try:
                old_uuid = self.uuid[arch]
                if env.translate_watchos and arch == "armv7k":
                    new_uuid = self.output_uuid["arm64_32"]
                else:
                    new_uuid = self.output_uuid[arch]
            except KeyError:
                env.error("Cannot generate uuid map in dsym bundle")
            with open(os.path.join(resource_dir, new_uuid + ".plist"),
                      "w") as f:
                f.write(plist_template.format(UUID=old_uuid))
