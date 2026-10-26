"""不联网的单元测试：版本目录名校验 + Forge 装完改名逻辑。"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import installer as inst  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("  [OK] " if cond else "  [!!] ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


print("== 版本目录名校验 ==")
check("空名字=自动", inst.check_version_name("") is None)
check("正常名字", inst.check_version_name("1.20.1-fabric") is None)
check("中文可以", inst.check_version_name("我的整合包") is None)
check("斜杠非法", inst.check_version_name("a/b") is not None)
check("冒号非法", inst.check_version_name("a:b") is not None)
check("问号非法", inst.check_version_name("a?b") is not None)
check(".. 非法", inst.check_version_name("..") is not None)
check("CON 保留", inst.check_version_name("con") is not None)
check("结尾点非法", inst.check_version_name("abc.") is not None)
check("首尾空格非法", inst.check_version_name(" abc") is not None)
check("超长非法", inst.check_version_name("x" * 80) is not None)

print("== Forge 装完改名 ==")
tmp = Path(tempfile.mkdtemp(prefix="mcdl-test-"))
gd = tmp / ".minecraft"
old = "1.20.1-forge-47.3.0"
vd = gd / "versions" / old
vd.mkdir(parents=True)
(vd / f"{old}.json").write_text(
    json.dumps({"id": old, "inheritsFrom": "1.20.1", "jar": "1.20.1"}), "utf-8")
(vd / f"{old}.jar").write_text("fake", "utf-8")
(vd / f"{old}-natives").mkdir()

ins = inst.Installer()
new_id = ins._rename_version(gd, old, "我的Forge端")
new_dir = gd / "versions" / new_id

check("返回新名字", new_id == "我的Forge端", new_id)
check("旧目录没了", not vd.exists())
check("新目录存在", new_dir.is_dir())
check("json 已改名", (new_dir / "我的Forge端.json").is_file())
data = json.loads((new_dir / "我的Forge端.json").read_text("utf-8"))
check("json 内 id 已同步", data.get("id") == "我的Forge端", str(data.get("id")))
check("inheritsFrom 保留", data.get("inheritsFrom") == "1.20.1")
check("jar 未改动", data.get("jar") == "1.20.1")
check("natives 目录跟着改名", (new_dir / "我的Forge端-natives").is_dir())
check("其余文件还在", (new_dir / "1.20.1-forge-47.3.0.jar").is_file())

# 目标已存在时要报错
(gd / "versions" / "占位").mkdir()
try:
    ins._rename_version(gd, "我的Forge端", "占位")
    check("目标重名报错", False)
except RuntimeError:
    check("目标重名报错", True)

import shutil  # noqa: E402
shutil.rmtree(tmp, ignore_errors=True)

print()
print("失败项:", fails if fails else "无")
sys.exit(1 if fails else 0)
