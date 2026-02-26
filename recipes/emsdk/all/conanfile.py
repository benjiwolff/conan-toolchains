import os
from pathlib import Path

from conan import ConanFile
from conan.tools.env import VirtualBuildEnv
from conan.tools.files import chdir, copy, get, replace_in_file
from conan.tools.layout import basic_layout

required_conan_version = ">=2.1"


class EmSDKConan(ConanFile):
    name = "emsdk"
    description = "Emscripten SDK. Emscripten is an Open Source LLVM to JavaScript compiler"
    url = "https://github.com/conan-io/conan-center-index"
    homepage = "https://github.com/kripken/emscripten"
    topics = ("emsdk", "emscripten", "sdk", "emcc", "em++", "nodejs")
    license = "MIT"
    package_type = "application"
    settings = "os", "arch"

    def layout(self):
        basic_layout(self, src_folder="src")

    def source(self):
        get(self, **self.conan_data["sources"][self.version], destination=self.source_folder, strip_root=True)

    @property
    def _emscripten(self):
        return os.path.join(self.package_folder, "bin", "upstream", "emscripten")

    @property
    def _node_path(self):
        subfolders = [path for path in (Path(self.package_folder) / "bin" / "node").iterdir() if path.is_dir()]
        if len(subfolders) != 1:
            return None
        return os.path.join("bin", "node", subfolders[0].name, "bin")

    def generate(self):
        # To avoid issues when cross-compiling or with not common arch in profiles we need to set EMSDK_ARCH
        # This is important for the emsdk install command
        env = VirtualBuildEnv(self)
        # Special consideration for armv8 as emsdk expects "arm64"
        arch = "arm64" if str(self.settings.arch) == "armv8" else str(self.settings.arch)
        env.environment().define("EMSDK_ARCH", arch)
        env.generate()

    def build(self):
        emdawnwebgpupy = os.path.join(self.source_folder, "upstream/emscripten/tools/ports/emdawnwebgpu.py")
        with chdir(self, self.source_folder):
            emsdk = "emsdk.bat" if self.settings_build.os == "Windows" else "./emsdk"
            self.run(f"{emsdk} install latest")
            replace_in_file(
                    self,
                    file_path=emdawnwebgpupy,
                    search="_VERSION = 'v20251002.162335'",
                    replace="_VERSION = 'v20260219.200501'")
            replace_in_file(
                    self,
                    file_path=emdawnwebgpupy,
                    search="SHA512 = 'ed15672c2c495a77c764929e6979f4e155bf8b9c46dee5b0f234f3208a708bc2b846d89eef345b725d03454b56d549531f48fc84ff2afe7627d14115893b0fb0'",
                    replace="SHA512 = '67f64ae3263e2111ca5d71b0ea69f0fbf42a0a7cd40ada66c3975e031f9af07411e1390a8b52fec08d563a99612ca6a3b3f75115191253d41fca18b8f3494f9c'")
            self.run(f"{emsdk} activate latest")

    def package(self):
        copy(self, "LICENSE", src=self.source_folder, dst=os.path.join(self.package_folder, "licenses"))
        copy(self, "*", src=self.source_folder, dst=os.path.join(self.package_folder, "bin"))
        replace_in_file(
            self,
            os.path.join(self.package_folder, "bin/upstream/emscripten/emrun.py"),
            "if MACOS and ('safari' in browser_exe.lower() or browser_exe == 'open'):",
            "if MACOS and 'safari' in browser_exe.lower():",
        )

    def finalize(self):
        copy(self, "*", src=self.immutable_package_folder, dst=self.package_folder)
        embuilder = os.path.join(
            self._emscripten, "embuilder" if self.info.settings.os != "Windows" else "embuilder.bat"
        )
        self.run(f"{embuilder} build MINIMAL")

    def _define_tool_var(self, value):
        suffix = ".bat" if self.settings.os == "Windows" else ""
        path = os.path.join(self._emscripten, f"{value}{suffix}")
        return path

    def package_info(self):
        self.cpp_info.bindirs = ["bin", os.path.join("bin", "upstream", "emscripten"), self._node_path]
        self.cpp_info.includedirs = []
        self.cpp_info.libdirs = []
        self.cpp_info.resdirs = []

        # If we are not building for Emscripten, probably we don't want to inject following environment variables,
        #   but it might be legit use cases... until we find them, let's be conservative.
        if not hasattr(self, "settings_target") or self.settings_target is None:
            return

        if self.settings_target.os != "Emscripten":
            self.output.warning(
                f"You've added {self.name}/{self.version} as a build requirement, while os={self.settings_target.os} != Emscripten"
            )
            return

        toolchain = os.path.join(
            self.package_folder, "bin", "upstream", "emscripten", "cmake", "Modules", "Platform", "Emscripten.cmake"
        )
        self.conf_info.prepend("tools.cmake.cmaketoolchain:user_toolchain", toolchain)

        self.buildenv_info.define_path("EMSDK", os.path.join(self.package_folder, "bin"))
        self.buildenv_info.define_path("EMSCRIPTEN", self._emscripten)
        self.buildenv_info.define_path("EM_CONFIG", os.path.join(self.package_folder, "bin", ".emscripten"))
        self.buildenv_info.define_path("EM_CACHE", os.path.join(self.package_folder, "bin", ".emscripten_cache"))

        compiler_executables = {
            "c": self._define_tool_var("emcc"),
            "cpp": self._define_tool_var("em++"),
        }
        self.conf_info.update("tools.build:compiler_executables", compiler_executables)
        self.buildenv_info.define_path("CC", compiler_executables["c"])
        self.buildenv_info.define_path("CXX", compiler_executables["cpp"])
        self.buildenv_info.define_path("AR", self._define_tool_var("emar"))
        self.buildenv_info.define_path("NM", self._define_tool_var("emnm"))
        self.buildenv_info.define_path("RANLIB", self._define_tool_var("emranlib"))
        self.buildenv_info.define_path("STRIP", self._define_tool_var("emstrip"))
