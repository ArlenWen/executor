# Task executor entry point
import argparse
import datetime
import random
import sys

from src import config, parse, secret
from src.job import Job, JobExitError


def gen_job_id() -> str:
    """job id = current datetime + 4 random digits, e.g. 202609211234567890"""
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
        except JobExitError as e:
            failed += 1
            logger.error("job %s (id=%s) aborted: %s; subsequent jobs will not run",
                         job_def.name, job_id, e)
            break
        except Exception as e:
            failed += 1
            logger.error("job %s (id=%s) failed: %s", job_def.name, job_id, e)
    return 1 if failed else 0


def cmd_serve(args) -> int:
    print(f"serve is not implemented yet (host={args.host}, port={args.port})")
    return 0


def cmd_secret(args) -> int:
    if args.secret_cmd == "set":
        secret.set_secret(args.name, args.value)
        print(f"secret saved: {args.name}")
    elif args.secret_cmd == "get":
        print(secret.get_secret(args.name))
    elif args.secret_cmd == "list":
        for name in secret.list_secrets():
            print(name)
    elif args.secret_cmd == "delete":
        secret.delete_secret(args.name)
        print(f"secret deleted: {args.name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="executor", description="task executor")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run jobs")
    group = p_run.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--file", help="run a single job file")
    group.add_argument("-d", "--dir", help="run all jobs in a directory")
    p_run.set_defaults(func=cmd_run)

    p_serve = sub.add_parser("serve", help="run http server (not implemented yet)")
    p_serve.add_argument("-H", "--host", default="0.0.0.0")
    p_serve.add_argument("-p", "--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    p_secret = sub.add_parser("secret", help="manage secrets")
    sub_secret = p_secret.add_subparsers(dest="secret_cmd", required=True)
    p_set = sub_secret.add_parser("set", help="set a secret")
    p_set.add_argument("name")
    p_set.add_argument("value")
    p_get = sub_secret.add_parser("get", help="get a secret")
    p_get.add_argument("name")
    sub_secret.add_parser("list", help="list all secret names")
    p_del = sub_secret.add_parser("delete", help="delete a secret")
    p_del.add_argument("name")
    p_secret.set_defaults(func=cmd_secret)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
