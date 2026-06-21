"""pre-commit hook 入口"""

import sys
from .cli import main

def main() -> int:
    """pre-commit 钩子主函数"""
    return sys.exit(main())

if __name__ == "__main__":
    main()
