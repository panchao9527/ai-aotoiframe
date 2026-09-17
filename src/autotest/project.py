"""项目接入的离线预检；不登录、不探测业务接口，也不输出凭据值。"""

import argparse

from pydantic import ValidationError

from autotest.api.auth import load_profile, resolve_role
from autotest.config import load_settings
from autotest.redaction import redact_text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="检查项目 API 地址和角色鉴权配置（离线）")
    parser.add_argument("action", choices=["check"])
    parser.add_argument("--env", required=True)
    parser.add_argument("--config-dir", default="configs/environments")
    parser.add_argument("--role", action="append", help="只检查指定角色，可重复；默认全部角色")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.env, args.config_dir)
        if not settings.api_base_url and settings.env != "demo":
            raise ValueError("缺少 API_BASE_URL / api_base_url")
        if settings.api_auth_file:
            profile = load_profile(settings.api_auth_file)
            for name in args.role or sorted(profile.roles):
                resolve_role(profile, name)
                print(f"[OK] 角色 {name} 的配置和环境变量齐全")
        elif args.role:
            raise ValueError("指定角色前需要配置 api_auth_file / API_AUTH_FILE")
        else:
            print("[OK] 使用原有 api_client；未启用角色鉴权")
        print("[OK] API 配置预检通过；未验证网络连通性、账号有效性或业务权限")
        return 0
    except ValidationError:
        print("[失败] 环境配置字段或地址格式无效，请按配置示例检查")
        return 1
    except OSError:
        print("[失败] 无法读取环境或鉴权配置文件，请检查路径与权限")
        return 1
    except ValueError as exc:
        # 配置加载器不回显 YAML/凭据；保留缺失变量名称，便于直接修正接入配置。
        print("[失败] " + redact_text(str(exc)))
        return 1
