#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import os
import sys
from distutils.version import LooseVersion

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

try:
    # typing only available builtin starting with Python3
    # cannot employ it during setup, but will be installed afterwards with backport
    from typing import TYPE_CHECKING  # noqa
    if TYPE_CHECKING:
        # pylint: disable=W0611,unused-import
        from typing import Iterable, Set, Tuple, Union  # noqa: F401
except ImportError:
    pass

COWBIRD_ROOT = os.path.abspath(os.path.dirname(__file__))
COWBIRD_MODULE_DIR = os.path.join(COWBIRD_ROOT, "cowbird")
sys.path.insert(0, COWBIRD_MODULE_DIR)
# do not use "from cowbird" to avoid import error on not yet installed packages
import __meta__  # isort:skip # noqa: E402

LOGGER = logging.getLogger("cowbird.setup")
if logging.StreamHandler not in LOGGER.handlers:
    LOGGER.addHandler(logging.StreamHandler(sys.stdout))  # type: ignore # noqa
LOGGER.setLevel(logging.INFO)
LOGGER.info("starting setup")


with open("README.rst") as readme_file:
    README = readme_file.read()

with open("CHANGES.rst") as changes_file:
    CHANGES = changes_file.read().replace(".. :changelog:", "")


def _split_requirement(requirement, version=False, python=False, merge=False):
    # type: (str, bool, bool, bool) -> Union[str, Tuple[str, str]]
    """
    Splits a requirement package definition into it's name and version specification.

    Returns the appropriate part(s) according to :paramref:`version`. If ``True``, returns the operator and version
    string. The returned version in this case would be either the package's or the environment python's version string
    according to the value of :paramref:`python`. Otherwise, only returns the 'other part' of the requirement, which
    will be the plain package name without version or the complete ``package+version`` without ``python_version`` part.

    Package requirement format::

        package [<|<=|==|>|>=|!= x.y.z][; python_version <|<=|==|>|>=|!= "x.y.z"]

    Returned values with provided arguments::

        default:                                "<package>"
        python=True                             n/a
        version=True:                           ([pkg-op], [pkg-ver])
        version=True,python=True:               ([py-op], [py-ver])
        version=True,merge=True:                "<package> [pkg-op] [pkg-ver]"
        version=True,python=True,merge=True:    "[python_version] [py-op] [py-ver]"

    :param requirement: full package string requirement.
    :param version:
        Retrieves the version operator and version number instead of only the package's name (without specifications).
    :param python:
        Retrieves the python operator and python version instead of the package's version.
        Must be combined with :paramref:`version`, otherwise doesn't do anything.
    :param merge:
        Nothing done if ``False`` (other arguments behave normally).
        If only :paramref:`version` is ``True``, merges the package name back with the version operator and number into
        a single string (if any version part), but without the python version part (if any).
        If both :paramref:`version` and :paramref:`python` are ``True`` combines back the part after ``;`` to form
        the python version specifier.
    :return: Extracted requirement part(s). Emtpy strings if parts cannot be found.
    """
    idx_pyv = -1 if python else 0
    if python and "python_version" not in requirement:
        return ("", "") if version and not merge else ""
    requirement = requirement.split("python_version")[idx_pyv].replace(";", "").replace("\"", "")
    op_str = ""
    pkg_name = requirement
    for operator in [">=", ">", "<=", "<", "!=", "==", "="]:
        if operator in requirement:
            op_str = operator
            pkg_name, requirement = requirement.split(operator, 1)
            break
    if not version:
        return pkg_name.strip()
    if op_str == "":
        pkg_name = requirement
        requirement = ""
    parts = (op_str, requirement.strip())
    if merge and python:
        return "python_version {} \"{}\"".format(parts[0], parts[1])
    if merge and version:
        return "{}{}{}".format(pkg_name, parts[0], parts[1])
    return parts


def _parse_requirements(file_path, requirements, links):
    # type: (str, Set[str], Set[str]) -> None
    """
    Parses a requirements file to extra packages and links.

    If a python version specific is present, requirements are added only if they match the current environment.

    :param file_path: file path to the requirements file.
    :param requirements: pre-initialized set in which to store extracted package requirements.
    :param links: pre-initialized set in which to store extracted link reference requirements.
    :returns: None
    """
    with open(file_path, "r") as requirements_file:
        for line in requirements_file:
            # ignore empty line, comment line or reference to other requirements file (-r flag)
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "python_version" in line:
                operator, py_ver = _split_requirement(line, version=True, python=True)
                op_map = {
                    "==": LooseVersion(sys.version) == LooseVersion(py_ver),
                    ">=": LooseVersion(sys.version) >= LooseVersion(py_ver),
                    "<=": LooseVersion(sys.version) <= LooseVersion(py_ver),
                    "!=": LooseVersion(sys.version) != LooseVersion(py_ver),
                    ">": LooseVersion(sys.version) > LooseVersion(py_ver),
                    "<": LooseVersion(sys.version) < LooseVersion(py_ver),
                }
                # skip requirement if not fulfilling python version
                if not op_map[operator]:
                    continue
                # remove only python part if any present
                line = _split_requirement(line, version=True, merge=True)
            if "git+https" in line:
                pkg = line.split("#")[-1]
                links.add(line.strip())
                requirements.add(pkg.replace("egg=", "").rstrip())
            elif line.startswith("http"):
                links.add(line.strip())
            else:
                requirements.add(line.strip())


def _extra_requirements(base_requirements, other_requirements):
    # type: (Iterable[str], Iterable[str]) -> Set[str]
    """
    Extracts only the extra requirements not already defined within the base requirements.

    :param base_requirements: base package requirements.
    :param other_requirements: other set of requirements referring to additional dependencies.
    """
    raw_requirements = set()
    for req in base_requirements:
        raw_req = _split_requirement(req, version=True, merge=True)
        raw_requirements.add(raw_req)
    filtered_requirements = set()
    for req in other_requirements:
        raw_req = _split_requirement(req, version=True, merge=True)
        if raw_req and raw_req not in raw_requirements:
            filtered_requirements.add(req)
    return filtered_requirements


LOGGER.info("reading requirements")

# See https://github.com/pypa/pip/issues/3610
# use set to have unique packages by name
LINKS = set()
REQUIREMENTS = set()
DOCS_REQUIREMENTS = set()
TEST_REQUIREMENTS = set()
_parse_requirements("requirements.txt", REQUIREMENTS, LINKS)
_parse_requirements("requirements-doc.txt", DOCS_REQUIREMENTS, LINKS)
_parse_requirements("requirements-dev.txt", TEST_REQUIREMENTS, LINKS)
LINKS = list(LINKS)
REQUIREMENTS = list(REQUIREMENTS)
DOCS_REQUIREMENTS = list(_extra_requirements(REQUIREMENTS, DOCS_REQUIREMENTS))
TEST_REQUIREMENTS = list(_extra_requirements(REQUIREMENTS, TEST_REQUIREMENTS))

LOGGER.info("base requirements: %s", REQUIREMENTS)
LOGGER.info("docs requirements: %s", DOCS_REQUIREMENTS)
LOGGER.info("test requirements: %s", TEST_REQUIREMENTS)
LOGGER.info("link requirements: %s", LINKS)

setup(
    # -- meta information --------------------------------------------------
    name=__meta__.__package__,
    version=__meta__.__version__,
    description=__meta__.__description__,
    long_description=README + "\n\n" + CHANGES,
    author=__meta__.__author__,
    maintainer=__meta__.__maintainer__,
    maintainer_email=__meta__.__email__,
    contact=__meta__.__maintainer__,
    contact_email=__meta__.__email__,
    url=__meta__.__url__,
    platforms=__meta__.__platforms__,
    license=__meta__.__license__,
    keywords=", ".join(__meta__.__keywords__),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: {} License".format(__meta__.__license__),
        "Natural Language :: English",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
    ],
    python_requires=">=3.6, <4",

    # -- Package structure -------------------------------------------------
    packages=[__meta__.__package__],
    package_dir={__meta__.__package__: __meta__.__package__},
    include_package_data=True,
    install_requires=REQUIREMENTS,
    dependency_links=LINKS,
    extras_require={
        "docs": DOCS_REQUIREMENTS,
        "dev": TEST_REQUIREMENTS,
        "test": TEST_REQUIREMENTS,
    },
    zip_safe=False,

    # -- self - tests --------------------------------------------------------
    # test_suite="nose.collector",
    # test_suite="tests.test_runner",
    # test_loader="tests.test_runner:run_suite",
    test_suite="tests",
    tests_require=TEST_REQUIREMENTS,

    # -- script entry points -----------------------------------------------
    entry_points={
        "paste.app_factory": [
            "main = cowbird.app:main"
        ],
        "console_scripts": [
            "cowbird = cowbird.cli:main",
        ],
    }
)
LOGGER.info("setup complete")
