# -*- mode: python ; coding: utf-8 -*-
# PyInstaller (modo "onedir", sem UPX): menos falsos positivos de antivírus que o "onefile" autoextraível.
import re
from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = ROOT / "kibitz"
ver = re.search(r'__version__\s*=\s*"([^"]+)"', (PKG / "__init__.py").read_text(encoding="utf-8")).group(1)
m = re.match(r"(\d+)\.(\d+)\.(\d+)(?:b(\d+))?", ver)
nums = tuple(int(x or 0) for x in m.groups())
pretty = f"{nums[0]}.{nums[1]}.{nums[2]}" + (f"-beta.{nums[3]}" if m.group(4) else "")

# recursos de versão do .exe (Propriedades > Detalhes): nome, empresa e licença claros em vez de "desconhecido"
vf = ROOT / "build" / "version_info.txt"
vf.parent.mkdir(exist_ok=True)
vf.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Lucas Rafael de Andrade'),
      StringStruct('FileDescription', 'Kibitz'),
      StringStruct('FileVersion', '{nums[0]}.{nums[1]}.{nums[2]}.{nums[3]}'),
      StringStruct('InternalName', 'Kibitz'),
      StringStruct('LegalCopyright', 'GPL-3.0-or-later. https://github.com/Andrade020/kibitz'),
      StringStruct('OriginalFilename', 'Kibitz.exe'),
      StringStruct('ProductName', 'Kibitz'),
      StringStruct('ProductVersion', '{pretty}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")

datas = [(str(PKG / d), f"kibitz/{d}") for d in ("static", "prompts", "assets", "examples")]

a = Analysis(
    [str(ROOT / "installer" / "desktop_entry.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["pystray._win32"],
    excludes=["tkinter", "unittest", "pydoc", "test", "distutils", "setuptools", "pip", "pytest", "playwright"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Kibitz",
    console=False,
    icon=str(ROOT / "installer" / "icon.ico"),
    version=str(vf),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Kibitz", upx=False)
