# 从环境变量或 .env 读取配置。项目内所有 Python 入口都应先调用 load_project_env()。
import os
from pathlib import Path
from typing import Optional

_PROJECT_ROOT_CANDIDATES = (
    Path(__file__).resolve().parent.parent,              # src/../
    Path.cwd(),
)


def find_project_root() -> Path:
    for p in _PROJECT_ROOT_CANDIDATES:
        if (p / "manage-supervisor.sh").exists() or (p / "config.yaml").exists():
            return p
    return _PROJECT_ROOT_CANDIDATES[0]


def find_dotenv(project_root: Optional[Path] = None) -> Optional[Path]:
    root = project_root or find_project_root()
    env = root / ".env"
    return env if env.is_file() else None


def load_project_env(override: bool = False) -> Path:
    """加载项目根目录的 .env 文件。默认不覆盖当前进程已存在的环境变量。

    Args:
        override: 为 True 时 .env 中的值会覆盖同名环境变量（少用）。
    Returns:
        项目根目录 Path
    """
    root = find_project_root()
    env_file = find_dotenv(root)

    if env_file is not None:
        try:
            from dotenv import load_dotenv  # type: ignore
            load_dotenv(dotenv_path=env_file, override=override)
        except Exception:
            # python-dotenv 未安装时，退化实现 (兼容 install.sh 早期阶段 / 旧环境)
            with env_file.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if not k or (not override and k in os.environ):
                        continue
                    os.environ[k] = v

    return root
