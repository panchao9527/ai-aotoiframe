"""允许使用 python -m autotest 运行命令，与 qa 命令完全等价。"""

from autotest.cli import main

raise SystemExit(main())
