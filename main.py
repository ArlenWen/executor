# 任务执行器入口
import argparse
import datetime
import random
import sys

from src import config, parse, secret
from src.job import Job


def gen_job_id() -> str:
    """job id = 当前日期时间 + 4位随机数，例如 202609211234567890"""
    return datetime.datetime.now().strftime("%Y%m%d%H%M%S") + f"{random.randint(0, 9999):04d}"


def cmd_run(args) -> int:
    if args.file:
        jobs = parse.load_job(args.file)
    else:
        jobs = parse.load_dir(args.dir)
    failed = 0
    for job_def in jobs:
        job_id = gen_job_id()
        logger = config.setup_logging(job_id)
        try:
            Job(job_def, job_id).run()
        except Exception as e:
            failed += 1
            logger.error("job %s (id=%s) 执行失败: %s", job_def.name, job_id, e)
    return 1 if failed else 0


def cmd_serve(args) -> int:
    print(f"serve 功能暂未实现 (host={args.host}, port={args.port})")
    return 0


def cmd_secret(args) -> int:
    if args.secret_cmd == "set":
        secret.set_secret(args.name, args.value)
        print(f"secret 已保存: {args.name}")
    elif args.secret_cmd == "get":
        print(secret.get_secret(args.name))
    elif args.secret_cmd == "list":
        for name in secret.list_secrets():
            print(name)
    elif args.secret_cmd == "delete":
        secret.delete_secret(args.name)
        print(f"secret 已删除: {args.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="executor", description="任务执行器")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="执行 job")
    group = p_run.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--file", help="执行单个 job 文件")
    group.add_argument("-d", "--dir", help="执行目录下的所有 job")
    p_run.set_defaults(func=cmd_run)

    p_serve = sub.add_parser("serve", help="运行 http server（暂未实现）")
    p_serve.add_argument("-H", "--host", default="0.0.0.0")
    p_serve.add_argument("-p", "--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    p_secret = sub.add_parser("secret", help="管理敏感数据")
    sub_secret = p_secret.add_subparsers(dest="secret_cmd", required=True)
    p_set = sub_secret.add_parser("set", help="设置 secret")
    p_set.add_argument("name")
    p_set.add_argument("value")
    p_get = sub_secret.add_parser("get", help="查看 secret")
    p_get.add_argument("name")
    sub_secret.add_parser("list", help="列出所有 secret 名称")
    p_del = sub_secret.add_parser("delete", help="删除 secret")
    p_del.add_argument("name")
    p_secret.set_defaults(func=cmd_secret)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
