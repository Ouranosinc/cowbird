#!/usr/bin/env python3
"""
Cowbird CLI helper to execute handler operations.
"""
import argparse
from typing import List

from cowbird.cli import LOGGER
from cowbird.cli.utils import (
    CommandPrefixes,
    HelperParser,
    ParsedArgs,
    ParserArgs,
    ParseResult,
    SharedParsers,
    get_config_parser,
    get_format_parser,
    print_format,
    set_log_level,
    subparser_help
)
from cowbird.handlers import get_handlers
from cowbird.typedefs import JSON
from cowbird.utils import CLI_MODE_CFG, get_app_config


def make_parser(shared_parsers: SharedParsers = None, prefixes: CommandPrefixes = None) -> argparse.ArgumentParser:
    cfg = get_config_parser()
    fmt = get_format_parser()
    parents = list(shared_parsers or []) + [cfg, fmt]
    prog = " ".join(prefix for prefix in list(prefixes or []) + ["handlers"] if prefix)
    parser = argparse.ArgumentParser(description="Handler commands.", prog=prog, parents=parents)
    parents += []
    cmd = parser.add_subparsers(title="Commands", dest="command", description="Command to run on handlers.")
    cmd.add_parser("list", parents=parents, **subparser_help("List known handlers.", parser))
    info = cmd.add_parser("info", parents=parents, **subparser_help("Obtains information about a handler.", parser))
    info.add_argument("name", help="Name of the handler to retrieve.")
    return parser


def main(args: ParserArgs = None, parser: HelperParser = None, namespace: ParsedArgs = None) -> ParseResult:
    if not parser:
        parser = make_parser()
    args = parser.parse_args(args=args, namespace=namespace)
    set_log_level(args)
    LOGGER.debug("Getting configuration")

    # Set the internal setting CLI_MODE_CFG to true which is used to prevent celery activation
    config = get_app_config({"cowbird.ini_file_path": args.config,
                             CLI_MODE_CFG: True})
    if args.command == "list":
        handlers = get_handlers(config)
        handler_json: List[JSON] = [handler.name for handler in handlers]
        print_format(handler_json, args.format, section="handlers")
    elif args.command == "info":
        handlers = get_handlers(config)
        handler_json: List[JSON] = [handler.json() for handler in handlers if handler.name == args.name]
        if not len(handler_json) == 1:
            LOGGER.error("Cannot find handler named: %s", args.name)
            return -1
        print_format(handler_json[0], args.format, section="handler")
    return 0


if __name__ == "__main__":
    main()
