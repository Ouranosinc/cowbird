#!/usr/bin/env python3
"""
Cowbird CLI helper to execute service operations.
"""
import argparse
from typing import TYPE_CHECKING

from cowbird.cli import LOGGER
from cowbird.cli.utils import get_config_parser, get_format_parser, print_format, set_log_level, subparser_help
from cowbird.services import get_services
from cowbird.utils import USE_CELERY_CFG, get_app_config

if TYPE_CHECKING:
    from cowbird.cli.utils import CommandPrefixes, HelperParser, ParsedArgs, ParserArgs, ParseResult, SharedParsers


def make_parser(shared_parsers=None, prefixes=None):
    # type: (SharedParsers, CommandPrefixes) -> argparse.ArgumentParser
    cfg = get_config_parser()
    fmt = get_format_parser()
    parents = list(shared_parsers or []) + [cfg, fmt]
    prog = " ".join(prefix for prefix in list(prefixes or []) + ["services"] if prefix)
    parser = argparse.ArgumentParser(description="Service commands.", prog=prog, parents=parents)
    parents += []
    cmd = parser.add_subparsers(title="Commands", dest="command", description="Command to run on services.")
    cmd.add_parser("list", parents=parents, **subparser_help("List known services.", parser))
    info = cmd.add_parser("info", parents=parents, **subparser_help("Obtains information about a service.", parser))
    info.add_argument("name", help="Name of the service to retrieve.")
    return parser


def main(args=None, parser=None, namespace=None):
    # type: (ParserArgs, HelperParser, ParsedArgs) -> ParseResult
    if not parser:
        parser = make_parser()
    args = parser.parse_args(args=args, namespace=namespace)
    set_log_level(args)
    LOGGER.debug("Getting configuration")
    config = get_app_config({"cowbird.ini_file_path": args.config,
                             USE_CELERY_CFG: False})
    if args.command == "list":
        services = get_services(config)
        svc_json = [svc.name for svc in services]
        print_format(svc_json, args.format, section="services")
    elif args.command == "info":
        services = get_services(config)
        svc_json = [svc.json() for svc in services if svc.name == args.name]
        if not len(svc_json) == 1:
            LOGGER.error("Cannot find service named: %s", args.name)
            return -1
        print_format(svc_json[0], args.format, section="service")
    return 0


if __name__ == "__main__":
    main()
