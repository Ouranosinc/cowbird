import argparse
import json
import logging
from typing import TYPE_CHECKING

import yaml

from cowbird.constants import get_constant

if TYPE_CHECKING:
    from typing import Callable, Dict, Iterable, Optional, Sequence

    CommandPrefixes = Optional[Iterable[str]]
    SharedParsers = Optional[Iterable[argparse.ArgumentParser]]
    ParsedArgs = Optional[argparse.Namespace]
    ParserArgs = Optional[Sequence[str]]
    HelperParser = Optional[argparse.ArgumentParser]
    ParseResult = int

    ParserMaker = Callable[[SharedParsers, CommandPrefixes], argparse.ArgumentParser]
    ParserRunner = Callable[[ParserArgs, HelperParser, ParsedArgs], ParseResult]


def subparser_help(description, parent_parser=None):
    # type: (str, Optional[argparse.ArgumentParser]) -> Dict[str, str]
    """
    Generates both fields with the same description as each parameter is used in different context.

    Field ``help`` is printed next to the subparser name when *parent parser* is called with ``--help``.
    Field ``description`` populates the help details under the usage command when calling *child parser* ``--help``.
    """
    desc = {"help": description, "description": description}
    if parent_parser:
        desc.update({"usage": parent_parser.usage})
    return desc


def get_config_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-c", "--config", help="INI configuration file to employ.",
                        default=get_constant("COWBIRD_INI_FILE_PATH", raise_missing=False, raise_not_set=False))
    return parser


def get_logger_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(add_help=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-q", "--quiet", action="store_true", help="Suppress informative logging.")
    group.add_argument("-d", "--debug", action="store_true", help="Set debug logging level.")
    group.add_argument("-l", "--level", choices=["debug", "info", "warn", "error"], default="info")
    return parser


def set_log_level(args, logger=None):
    # type: (argparse.Namespace, Optional[logging.Logger]) -> None
    from cowbird.cli import LOGGER
    logger = logger or LOGGER
    if args.quiet:
        logger.setLevel(logging.ERROR)
    elif args.debug:
        logger.setLevel(logging.DEBUG)
    elif args.level:
        logger.setLevel(args.level.upper())
    else:
        logger.setLevel(logging.INFO)


def get_format_parser():
    # type: () -> argparse.ArgumentParser
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-f", "--format", choices=["flat", "json", "table", "yaml"], default="json",
                        help="Output format of the command.")
    return parser


def print_format(data, fmt, section=None):
    if fmt == "yaml":
        if section:
            data = {section: data}
        print(yaml.safe_dump(data, allow_unicode=True, indent=2, sort_keys=False))
    elif fmt == "json":
        if section:
            data = {section: data}
        print(json.dumps(data, indent=4, ensure_ascii=False))
    elif fmt == "flat":
        if isinstance(data, dict):
            for field, value in data.items():
                print(f"{field}: {value}")
        else:
            for value in data:
                print(value)
    elif fmt == "table":
        if isinstance(data, dict):
            widths = [8, 8]
            for field, value in data.items():
                widths[0] = max(widths[0], len(field))
                widths[1] = max(widths[1], len(value))
            separator = "+" + "-" * (widths[0] + 2) + "+" + "-" * (widths[1] + 2) + "+"
            print(separator)
            print(f"| {'Fields'.ljust(widths[0])} | {'Values'.ljust(widths[1])} |")
            print(separator.replace("-", "="))
            for field, value in data.items():
                print(f"| {field.ljust(widths[0])} | {value.ljust(widths[1])} |")
            print(separator)
        else:
            width = max(8, len(section or ""))
            for item in data:
                width = max(width, len(item))
            separator = "+" + "-" * (width + 2) + "+"
            print(separator)
            if section:
                print(f"| {section.ljust(width)} |")
                print(separator.replace("-", "="))
            for item in data:
                print(f"| {item.ljust(width)} |")
            print(separator)
    else:
        raise ValueError(f"unknown format [{fmt}]")
