define BROWSER_PYSCRIPT
import os, webbrowser, sys
try:
	from urllib import pathname2url
except:
	from urllib.request import pathname2url

webbrowser.open("file://" + pathname2url(os.path.abspath(sys.argv[1])))
endef
export BROWSER_PYSCRIPT
BROWSER := python -c "$$BROWSER_PYSCRIPT"

# Included custom configs change the value of MAKEFILE_LIST
# Extract the required reference beforehand so we can use it for help target
MAKEFILE_NAME := $(word $(words $(MAKEFILE_LIST)),$(MAKEFILE_LIST))
# Include custom config if it is available
-include Makefile.config

# Application
APP_ROOT    := $(abspath $(lastword $(MAKEFILE_NAME))/..)
APP_NAME    := cowbird
APP_VERSION ?= 1.0.0
APP_INI     ?= $(APP_ROOT)/config/$(APP_NAME).ini
APP_PORT    ?= 7000

# guess OS (Linux, Darwin,...)
OS_NAME := $(shell uname -s 2>/dev/null || echo "unknown")
CPU_ARCH := $(shell uname -m 2>/dev/null || uname -p 2>/dev/null || echo "unknown")

# conda
CONDA_ENV_NAME ?= $(APP_NAME)
CONDA_HOME     ?= $(HOME)/.conda
CONDA_ENVS_DIR ?= $(CONDA_HOME)/envs
CONDA_ENV_PATH := $(CONDA_ENVS_DIR)/$(CONDA_ENV_NAME)
# allow pre-installed conda in Windows bash-like shell
ifeq ($(findstring MINGW,$(OS_NAME)),MINGW)
  CONDA_BIN_DIR ?= $(CONDA_HOME)/Scripts
else
  CONDA_BIN_DIR ?= $(CONDA_HOME)/bin
endif
CONDA_BIN := $(CONDA_BIN_DIR)/conda
CONDA_ENV_REAL_TARGET_PATH := $(realpath $(CONDA_ENV_PATH))
CONDA_ENV_REAL_ACTIVE_PATH := $(realpath ${CONDA_PREFIX})

# environment already active - use it directly
ifneq ("$(CONDA_ENV_REAL_ACTIVE_PATH)", "")
  CONDA_ENV_MODE := [using active environment]
  CONDA_ENV_NAME := $(notdir $(CONDA_ENV_REAL_ACTIVE_PATH))
  CONDA_CMD :=
endif
# environment not active but it exists - activate and use it
ifneq ($(CONDA_ENV_REAL_TARGET_PATH), "")
  CONDA_ENV_NAME := $(notdir $(CONDA_ENV_REAL_TARGET_PATH))
endif
# environment not active and not found - create, activate and use it
ifeq ("$(CONDA_ENV_NAME)", "")
  CONDA_ENV_NAME := $(APP_NAME)
endif
# update paths for environment activation
ifeq ("$(CONDA_ENV_REAL_ACTIVE_PATH)", "")
  CONDA_ENV_MODE := [will activate environment]
  CONDA_CMD := source "$(CONDA_BIN_DIR)/activate" "$(CONDA_ENV_NAME)";
endif
# override conda command as desired
CONDA_COMMAND ?= undefined
CONDA_SETUP := 1
ifneq ("$(CONDA_COMMAND)","undefined")
  CONDA_SETUP := 0
  CONDA_ENV_MODE := [using overridden command]
  CONDA_CMD := $(CONDA_COMMAND)
endif

DOWNLOAD_CACHE ?= $(APP_ROOT)/downloads
REPORTS_DIR ?= $(APP_ROOT)/reports
PYTHON_VERSION ?= `python -c 'import platform; print(platform.python_version())'`
PIP_XARGS ?=
PIP_USE_FEATURE := `python -c '\
	import pip; \
	from distutils.version import LooseVersion; \
	print(LooseVersion(pip.__version__) < LooseVersion("21.0"))'`
ifeq ($(findstring "--use-feature=2020-resolver",$(PIP_XARGS)),)
  # feature not specified, but needed
  ifeq ("$(PIP_USE_FEATURE)", "True")
    PIP_XARGS := --use-feature=2020-resolver $(PIP_XARGS)
  else
    # use faster legacy resolver
    ifeq ($(subst "--use-deprecated=legacy-resolver",,$(PIP_XARGS)),)
      PIP_XARGS := --use-deprecated=legacy-resolver $(PIP_XARGS)
    endif
    ifeq ($(findstring "--use-feature=fast-deps",$(PIP_XARGS)),)
      PIP_XARGS := --use-feature=fast-deps $(PIP_XARGS)
    endif
  endif
else
  # feature was specified, but should not (not required anymore, default behavior)
  ifeq ("$(PIP_USE_FEATURE)", "True")
    PIP_XARGS := $(subst "--use-feature=2020-resolver",,"$(PIP_XARGS)")
  else
    # use faster legacy resolver
    ifeq $(subst "--use-deprecated=legacy-resolver",,$(PIP_XARGS))
      PIP_XARGS := --use-deprecated=legacy-resolver $(PIP_XARGS)
    endif
  	ifeq ($(findstring "--use-feature=fast-deps",$(PIP_XARGS)),)
      PIP_XARGS := --use-feature=fast-deps $(PIP_XARGS)
    endif
  endif
endif

# choose conda installer depending on your OS
CONDA_URL = https://repo.continuum.io/miniconda
ifeq ("$(OS_NAME)", "Linux")
  FN := Miniconda3-latest-Linux-x86_64.sh
else ifeq ("$(OS_NAME)", "Darwin")
  FN := Miniconda3-latest-MacOSX-x86_64.sh
else
  FN := unknown
endif

# docker
DOCKER_REPO := pavics/cowbird
BASE_TAG := $(APP_NAME):base
LATEST_TAG := $(APP_NAME):latest
VERSION_TAG := $(APP_NAME):$(APP_VERSION)
REPO_LATEST_TAG := $(DOCKER_REPO):latest
REPO_VERSION_TAG := $(DOCKER_REPO):$(APP_VERSION)
WEBSVC_SUFFIX := -webservice
WORKER_SUFFIX := -worker

# docker-compose
ifneq ("$(wildcard ./docker/.env)","")
    DOCKER_COMPOSE_ENV_FILE := $(APP_ROOT)/docker/.env
else
    DOCKER_COMPOSE_ENV_FILE := $(APP_ROOT)/docker/.env.example
endif

.DEFAULT_GOAL := help

## --- Informative targets --- ##

.PHONY: all
all: help

# Auto documented help targets & sections from comments
#	- detects lines marked by double octothorpe (#), then applies the corresponding target/section markup
#   - target comments must be defined after their dependencies (if any)
#	- section comments must have at least a double dash (-)
#
# 	Original Reference:
#		https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
# 	Formats:
#		https://misc.flogisoft.com/bash/tip_colors_and_formatting
_SECTION := \033[34m
_TARGET  := \033[36m
_NORMAL  := \033[0m
.PHONY: help
# note: use "\#\#" to escape results that would self-match in this target's search definition
help:	## print this help message (default)
	@echo "$(_SECTION)=== $(APP_NAME) help ===$(_NORMAL)"
	@echo "Please use 'make <target>' where <target> is one of:"
#	@grep -E '^[a-zA-Z_-]+:.*?\#\# .*$$' $(MAKEFILE_LIST) \
#		| awk 'BEGIN {FS = ":.*?\#\# "}; {printf "    $(_TARGET)%-24s$(_NORMAL) %s\n", $$1, $$2}'
	@grep -E '\#\#.*$$' "$(APP_ROOT)/$(MAKEFILE_NAME)" \
		| awk ' BEGIN {FS = "(:|\-\-\-)+.*?\#\# "}; \
			/\--/ {printf "$(_SECTION)%s$(_NORMAL)\n", $$1;} \
			/:/   {printf "    $(_TARGET)%-24s$(_NORMAL) %s\n", $$1, $$2} \
		'

.PHONY: version
version:	## display current version
	@-echo "$(APP_NAME) version: $(APP_VERSION)"

.PHONY: info
info:		## display make information
	@echo "Information about your make execution:"
	@echo "  OS Name                $(OS_NAME)"
	@echo "  CPU Architecture       $(CPU_ARCH)"
	@echo "  Conda Home             $(CONDA_HOME)"
	@echo "  Conda Prefix           $(CONDA_ENV_PATH)"
	@echo "  Conda Env Name         $(CONDA_ENV_NAME)"
	@echo "  Conda Env Path         $(CONDA_ENV_REAL_ACTIVE_PATH)"
	@echo "  Conda Binary           $(CONDA_BIN)"
	@echo "  Conda Activation       $(CONDA_ENV_MODE)"
	@echo "  Conda Command          $(CONDA_CMD)"
	@echo "  Application Root       $(APP_ROOT)"
	@echo "  Application Name       $(APP_NAME)"
	@echo "  Application Version    $(APP_VERSION)"
	@echo "  Download Cache         $(DOWNLOAD_CACHE)"
	@echo "  Test Reports           $(REPORTS_DIR)"
	@echo "  Base Docker Tag        $(REPO_VERSION_TAG)"
	@echo "  Webservice Docker Tag  $(REPO_VERSION_TAG)$(WEBSVC_SUFFIX)"
	@echo "  Worker Docker Tag      $(REPO_VERSION_TAG)$(WORKER_SUFFIX)"

## --- Cleanup targets --- ##

.PHONY: clean
clean: clean-all	## alias for 'clean-all' target

.PHONY: clean-all
clean-all: clean-build clean-pyc clean-test clean-docs	## remove all artifacts

.PHONY: clean-build
clean-build:	## remove build artifacts
	@echo "Cleaning build artifacts..."
	@-rm -fr build/
	@-rm -fr dist/
	@-rm -fr downloads/
	@-rm -fr .eggs/
	@find . -type d -name '*.egg-info' -exec rm -fr {} +
	@find . -type f -name '*.egg' -exec rm -f {} +

# rm without quotes important below to allow regex
.PHONY: clean-docs
clean-docs:		## remove doc artifacts
	@echo "Cleaning doc artifacts..."
	@-find "$(APP_ROOT)/docs/" -type f -name "$(APP_NAME)*.rst" -delete
	@-rm -f "$(APP_ROOT)/docs/modules.rst"
	@-rm -f "$(APP_ROOT)/docs/api.json"
	@-rm -rf "$(APP_ROOT)/docs/autoapi"
	@-rm -rf "$(APP_ROOT)/docs/_build"

.PHONY: clean-pyc
clean-pyc:		## remove Python file artifacts
	@echo "Cleaning Python artifacts..."
	@find . -type f -name '*.pyc' -exec rm -f {} +
	@find . -type f -name '*.pyo' -exec rm -f {} +
	@find . -type f -name '*~' -exec rm -f {} +
	@find . -type f -name '__pycache__' -exec rm -fr {} +

.PHONY: clean-test
clean-test:		## remove test and coverage artifacts
	@echo "Cleaning tests artifacts..."
	@-rm -fr .tox/
	@-rm -fr .pytest_cache/
	@-rm -f .coverage*
	@-rm -f coverage.*
	@-rm -fr "$(APP_ROOT)/coverage/"
	@-rm -fr "$(REPORTS_DIR)"

.PHONY: clean-docker
clean-docker: docker-clean	## alias for 'docker-clean' target

## --- Documentation targets --- ##

DOC_LOCATION := $(APP_ROOT)/docs/_build/html/index.html
$(DOC_LOCATION):
	@echo "Building docs..."
	@bash -c '$(CONDA_CMD) \
		sphinx-apidoc -o "$(APP_ROOT)/docs/" "$(APP_ROOT)/$(APP_NAME)"; \
		"$(MAKE)" -C "$(APP_ROOT)/docs" BUILDDIR=_build PACKAGE="$(APP_NAME)" html;'
	@-echo "Documentation available: file://$(DOC_LOCATION)"

# NOTE: we need almost all base dependencies because package needs to be parsed to generate OpenAPI
.PHONY: docs
docs: install-docs install-pkg clean-docs $(DOC_LOCATION)	## generate Sphinx HTML documentation, including API docs

.PHONY: docs-show
docs-show: $(DOC_LOCATION)	## display HTML webpage of generated documentation (build docs if missing)
	@-test -f "$(DOC_LOCATION)" || $(MAKE) -C "$(APP_ROOT)" docs
	$(BROWSER) "$(DOC_LOCATION)"

## --- Versioning targets --- ##

# Bumpversion 'dry' config
# if 'dry' is specified as target, any bumpversion call using 'BUMP_XARGS' will not apply changes
BUMP_XARGS ?= --verbose --allow-dirty
ifeq ($(filter dry, $(MAKECMDGOALS)), dry)
	BUMP_XARGS := $(BUMP_XARGS) --dry-run
endif

.PHONY: dry
dry: setup.cfg	## run 'bump' target without applying changes (dry-run)
ifeq ($(findstring bump, $(MAKECMDGOALS)),)
	$(error Target 'dry' must be combined with a 'bump' target)
endif

.PHONY: bump
bump:	## bump version using VERSION specified as user input
	@-echo "Updating package version ..."
	@[ "${VERSION}" ] || ( echo ">> 'VERSION' is not set"; exit 1 )
	@-bash -c '$(CONDA_CMD) test -f "$(CONDA_ENV_PATH)/bin/bump2version" || pip install $(PIP_XARGS) bump2version'
	@-bash -c '$(CONDA_CMD) bump2version $(BUMP_XARGS) --new-version "${VERSION}" patch;'

## --- Installation targets --- ##

.PHONY: dist
dist: clean conda-env	## package for distribution
	@echo "Creating distribution..."
	@bash -c '$(CONDA_CMD) python setup.py sdist'
	@bash -c '$(CONDA_CMD) python setup.py bdist_wheel'
	ls -l dist

.PHONY: install
install: install-all	## alias for 'install-all' target

.PHONY: install-all
install-all: install-sys install-pkg install-dev install-docs	## install every dependency and package definition

.PHONY: install-xargs
install-xargs:
	@echo "Using PIP_XARGS: $(PIP_XARGS)"

# note: don't use PIP_XARGS for install system package as it could be upgrade of pip that doesn't yet have those options
.PHONY: install-sys
install-sys: clean conda-env install-xargs	## install system dependencies and required installers/runners
	@echo "Installing system dependencies..."
	@bash -c '$(CONDA_CMD) pip install --upgrade -r "$(APP_ROOT)/requirements-sys.txt"'
	@bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) gunicorn'

.PHONY: install-pkg
install-pkg: install-sys	## install the package to the active Python's site-packages
	@echo "Installing $(APP_NAME)..."
	@bash -c '$(CONDA_CMD) python setup.py install_egg_info'
	@bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) --upgrade -e "$(APP_ROOT)" --no-cache'

.PHONY: install-req
install-req: conda-env install-xargs	 ## install package base requirements without installing main package
	@bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) -r "$(APP_ROOT)/requirements.txt"'
	@echo "Successfully installed base requirements."

.PHONY: install-docs
install-docs: conda-env install-xargs  ## install package requirements for documentation generation
	@bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) -r "$(APP_ROOT)/requirements-doc.txt"'
	@echo "Successfully installed docs requirements."

.PHONY: install-dev
install-dev: conda-env install-xargs	## install package requirements for development and testing
	@bash -c '$(CONDA_CMD) pip install $(PIP_XARGS) -r "$(APP_ROOT)/requirements-dev.txt"'
	@echo "Successfully installed dev requirements."

# install locally to ensure they can be found by config extending them
.PHONY: install-npm
install-npm:    		## install npm package manager if it cannot be found
	@[ -f "$(shell which npm)" ] || ( \
		echo "Binary package manager npm not found. Attempting to install it."; \
		apt-get install npm \
	)
	@[ `npm ls 2>/dev/null | grep stylelint-config-standard | wc -l` = 1 ] || ( \
		echo "Install required libraries for style checks." && \
		npm install stylelint stylelint-config-standard --save-dev \
	)

## --- Launchers targets --- ##

.PHONY: cron
cron:
	@echo "Starting Cron service..."
	cron

.PHONY: start
start: install	## start application instance(s) with gunicorn
	@echo "Starting $(APP_NAME)..."
	@bash -c '$(CONDA_CMD) exec gunicorn -b 0.0.0.0:$(APP_PORT) --paste "$(APP_INI)" --preload &'

.PHONY: stop
stop: 		## kill application instance(s) started with gunicorn
	@(lsof -t -i :$(APP_PORT) | xargs kill) 2>/dev/null || echo "No $(APP_NAME) process to stop"

.PHONY: stat
stat: 		## display processes with PID(s) of gunicorn instance(s) running the application
	@lsof -i :$(APP_PORT) || echo "No instance running"

## --- Docker targets --- ##

.PHONY: docker-info
docker-info:		## obtain docker image information
	@echo "Docker images will be built as: "
	@echo "  $(VERSION_TAG)"
	@echo "  $(VERSION_TAG)$(WEBSVC_SUFFIX)"
	@echo "  $(VERSION_TAG)$(WORKER_SUFFIX)"
	@echo "Docker images will be pushed as:"
	@echo "  $(REPO_VERSION_TAG)"
	@echo "  $(REPO_VERSION_TAG)$(WEBSVC_SUFFIX)"
	@echo "  $(REPO_VERSION_TAG)$(WORKER_SUFFIX)"

.PHONY: docker-build-base
docker-build-base:							## build the base docker image
	docker build "$(APP_ROOT)" -f "$(APP_ROOT)/docker/Dockerfile-base" -t "$(BASE_TAG)"
	docker tag "$(BASE_TAG)" "$(VERSION_TAG)"
	docker tag "$(BASE_TAG)" "$(LATEST_TAG)"
	docker tag "$(BASE_TAG)" "$(REPO_LATEST_TAG)"
	docker tag "$(BASE_TAG)" "$(REPO_VERSION_TAG)"

.PHONY: docker-build-webservice
docker-build-webservice: docker-build-base		## build the web service docker image
	docker build "$(APP_ROOT)" -f "$(APP_ROOT)/docker/Dockerfile$(WEBSVC_SUFFIX)" -t "$(VERSION_TAG)$(WEBSVC_SUFFIX)"
	docker tag "$(VERSION_TAG)$(WEBSVC_SUFFIX)" "$(LATEST_TAG)$(WEBSVC_SUFFIX)"
	docker tag "$(VERSION_TAG)$(WEBSVC_SUFFIX)" "$(REPO_LATEST_TAG)$(WEBSVC_SUFFIX)"
	docker tag "$(VERSION_TAG)$(WEBSVC_SUFFIX)" "$(REPO_VERSION_TAG)$(WEBSVC_SUFFIX)"

.PHONY: docker-build-worker
docker-build-worker: docker-build-base		## build the worker docker image
	docker build "$(APP_ROOT)" -f "$(APP_ROOT)/docker/Dockerfile$(WORKER_SUFFIX)" -t "$(VERSION_TAG)$(WORKER_SUFFIX)"
	docker tag "$(VERSION_TAG)$(WORKER_SUFFIX)" "$(LATEST_TAG)$(WORKER_SUFFIX)"
	docker tag "$(VERSION_TAG)$(WORKER_SUFFIX)" "$(REPO_LATEST_TAG)$(WORKER_SUFFIX)"
	docker tag "$(VERSION_TAG)$(WORKER_SUFFIX)" "$(REPO_VERSION_TAG)$(WORKER_SUFFIX)"

.PHONY: docker-build
docker-build: docker-build-base docker-build-webservice docker-build-worker		## build all docker images

.PHONY: docker-push-base
docker-push-base: docker-build-base			## push the base docker image
	docker push "$(REPO_VERSION_TAG)"
	docker push "$(REPO_LATEST_TAG)"

.PHONY: docker-push-webservice
docker-push-webservice: docker-build-webservice	## push the webservice docker image
	docker push "$(REPO_VERSION_TAG)$(WEBSVC_SUFFIX)"
	docker push "$(REPO_LATEST_TAG)$(WEBSVC_SUFFIX)"

.PHONY: docker-push-worker
docker-push-worker: docker-build-worker		## push the worker docker image
	docker push "$(REPO_VERSION_TAG)$(WORKER_SUFFIX)"
	docker push "$(REPO_LATEST_TAG)$(WORKER_SUFFIX)"

.PHONY: docker-push
docker-push: docker-push-base docker-push-webservice docker-push-worker  ## push all docker images

.PHONY: docker-config
docker-config:  ## update docker specific config from examples files
	# Create a celeryconfig.py specifically for the docker-compose network
	sed 's/mongodb:\/\/.*:/mongodb:\/\/mongodb:/g' config/celeryconfig.py > config/celeryconfig.docker.py
	sed 's/mongodb:\/\/.*:/mongodb:\/\/mongodb:/g' config/cowbird.example.ini > config/cowbird.docker.ini

DOCKER_COMPOSE_WITH_ENV := docker-compose --env-file $(DOCKER_COMPOSE_ENV_FILE)
DOCKER_TEST_COMPOSES := -f "$(APP_ROOT)/tests/ci/docker-compose.smoke-test.yml"
.PHONY: docker-test
docker-test: docker-build	## execute a smoke test of the built Docker image (validate that it boots)
	@echo "Smoke test of built application docker image"
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_TEST_COMPOSES) up -d
	sleep 5
	curl localhost:$(APP_PORT)/version | python -m json.tool | grep "version"
	curl localhost:$(APP_PORT) | python -m json.tool | grep $(APP_NAME)
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_TEST_COMPOSES) logs
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_TEST_COMPOSES) stop

.PHONY: docker-stat
docker-stat:  ## query docker-compose images status (from 'docker-test')
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_TEST_COMPOSES) ps

DOCKER_COMPOSES := -f "$(APP_ROOT)/docker/docker-compose.example.yml" -f "$(APP_ROOT)/docker/docker-compose.override.example.yml"
.PHONY: docker-up
docker-up: docker-build docker-config   ## run all containers using compose
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_COMPOSES) up

DOCKER_DEV_COMPOSES := -f "$(APP_ROOT)/docker/docker-compose.example.yml" -f "$(APP_ROOT)/docker/docker-compose.dev.example.yml"
.PHONY: docker-up-dev
docker-up-dev: docker-build   ## run all dependencies containers using compose ready to be used by a local cowbird
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_DEV_COMPOSES) up

# used for testing on github's ci
.PHONY: docker-up-dev-detached
docker-up-dev-detached:   ## run all dependencies containers using compose ready to be used by a local cowbird, in detached mode
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_DEV_COMPOSES) up -d

.PHONY: docker-down
docker-down:  ## stop running containers and remove them
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_TEST_COMPOSES) down || true
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_DEV_COMPOSES) down || true
	$(DOCKER_COMPOSE_WITH_ENV) $(DOCKER_COMPOSES) down --remove-orphans || true

.PHONY: docker-clean
docker-clean: docker-down  ## remove all built docker images (only matching current/latest versions)
	docker rmi -f "$(REPO_VERSION_TAG)$(WEBSVC_SUFFIX)" || true
	docker rmi -f "$(REPO_LATEST_TAG)$(WEBSVC_SUFFIX)" || true
	docker rmi -f "$(VERSION_TAG)$(WEBSVC_SUFFIX)" || true
	docker rmi -f "$(LATEST_TAG)$(WEBSVC_SUFFIX)" || true
	docker rmi -f "$(REPO_VERSION_TAG)$(WORKER_SUFFIX)" || true
	docker rmi -f "$(REPO_LATEST_TAG)$(WORKER_SUFFIX)" || true
	docker rmi -f "$(VERSION_TAG)$(WORKER_SUFFIX)" || true
	docker rmi -f "$(LATEST_TAG)$(WORKER_SUFFIX)" || true
	docker rmi -f "$(REPO_VERSION_TAG)" || true
	docker rmi -f "$(REPO_LATEST_TAG)" || true
	docker rmi -f "$(VERSION_TAG)" || true
	docker rmi -f "$(LATEST_TAG)" || true
	docker rmi -f "$(BASE_TAG)" || true

## --- Static code check targets ---

.PHONY: mkdir-reports
mkdir-reports:
	@mkdir -p "$(REPORTS_DIR)"

CHECKS := pep8 lint security doc8 links imports css
CHECKS := $(addprefix check-, $(CHECKS))

.PHONY: check
check: check-all	## alias for 'check-all' target

.PHONY: check-all
check-all: $(CHECKS)	## run every code style checks

.PHONY: check-pep8
check-pep8: mkdir-reports install-dev		## run PEP8 code style checks
	@echo "Running PEP8 code style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-pep8.txt"
	@bash -c '$(CONDA_CMD) \
		flake8 --config="$(APP_ROOT)/setup.cfg" --output-file="$(REPORTS_DIR)/check-pep8.txt" --tee'

.PHONY: check-lint
check-lint: mkdir-reports install-dev		## run linting code style checks
	@echo "Running linting code style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-lint.txt"
	@bash -c '$(CONDA_CMD) \
		pylint \
			--load-plugins pylint_quotes \
			--rcfile="$(APP_ROOT)/.pylintrc" \
			--reports y \
			"$(APP_ROOT)/$(APP_NAME)" "$(APP_ROOT)/docs" "$(APP_ROOT)/tests" \
		1> >(tee "$(REPORTS_DIR)/check-lint.txt")'

.PHONY: check-security
check-security: mkdir-reports install-dev	## run security code checks
	@echo "Running security code checks..."
	@-rm -fr "$(REPORTS_DIR)/check-security.txt"
	@bash -c '$(CONDA_CMD) \
		bandit -v --ini "$(APP_ROOT)/setup.cfg" -r \
		1> >(tee "$(REPORTS_DIR)/check-security.txt")'

.PHONY: check-docs
check-docs: check-doc8 check-docf	## run every code documentation checks

.PHONY: check-doc8
check-doc8:	mkdir-reports install-dev		## run PEP8 documentation style checks
	@echo "Running PEP8 doc style checks..."
	@-rm -fr "$(REPORTS_DIR)/check-doc8.txt"
	@bash -c '$(CONDA_CMD) \
		doc8 --config "$(APP_ROOT)/setup.cfg" "$(APP_ROOT)/docs" \
		1> >(tee "$(REPORTS_DIR)/check-doc8.txt")'

# FIXME: move parameters to setup.cfg when implemented (https://github.com/myint/docformatter/issues/10)
# NOTE: docformatter only reports files with errors on stderr, redirect trace stderr & stdout to file with tee
# NOTE:
#	Don't employ '--wrap-descriptions 120' since they *enforce* that length and rearranges format if any word can fit
#	within remaining space, which often cause big diffs of ugly formatting for no important reason. Instead only check
#	general formatting operations, and let other linter capture docstrings going over 120 (what we really care about).
.PHONY: check-docf
check-docf: mkdir-reports install-dev	## run PEP8 code documentation format checks
	@echo "Checking PEP8 doc formatting problems..."
	@-rm -fr "$(REPORTS_DIR)/check-docf.txt"
	@bash -c '$(CONDA_CMD) \
		docformatter \
			--pre-summary-newline \
			--wrap-descriptions 0 \
			--wrap-summaries 120 \
			--make-summary-multi-line \
			--check \
			--recursive \
			"$(APP_ROOT)" \
		1>&2 2> >(tee "$(REPORTS_DIR)/check-docf.txt")'

.PHONY: check-links
check-links: install-dev	## check all external links in documentation for integrity
	@echo "Running link checks on docs..."
	@bash -c '$(CONDA_CMD) $(MAKE) -C "$(APP_ROOT)/docs" linkcheck'

.PHONY: check-imports
check-imports: mkdir-reports install-dev	## run imports code checks
	@echo "Running import checks..."
	@-rm -fr "$(REPORTS_DIR)/check-imports.txt"
	@bash -c '$(CONDA_CMD) \
	 	isort --check-only --diff $(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/check-imports.txt")'

.PHONY: check-css
check-css: mkdir-reports install-npm
	@echo "Running CSS style checks..."
	@npx stylelint \
		--config "$(APP_ROOT)/.stylelintrc.json" \
		--output-file "$(REPORTS_DIR)/fixed-css.txt" \
		"$(APP_ROOT)/**/*.css"

FIXES := imports lint docf fstring css
FIXES := $(addprefix fix-, $(FIXES))

.PHONY: fix
fix: fix-all	## alias for 'fix-all' target

.PHONY: fix-all
fix-all: $(FIXES)	## fix all applicable code check corrections automatically

.PHONY: fix-imports
fix-imports: install-dev	## fix import code checks corrections automatically
	@echo "Fixing flagged import checks..."
	@-rm -fr "$(REPORTS_DIR)/fixed-imports.txt"
	@bash -c '$(CONDA_CMD) \
		isort $(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/fixed-imports.txt")'

.PHONY: fix-lint
fix-lint: install-dev	## fix some PEP8 code style problems automatically
	@echo "Fixing PEP8 code style problems..."
	@-rm -fr "$(REPORTS_DIR)/fixed-lint.txt"
	@bash -c '$(CONDA_CMD) \
		autopep8 -v -j 0 -i -r $(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/fixed-lint.txt")'

# FIXME: move parameters to setup.cfg when implemented (https://github.com/myint/docformatter/issues/10)
.PHONY: fix-docf
fix-docf: install-dev	## fix some PEP8 code documentation style problems automatically
	@echo "Fixing PEP8 code documentation problems..."
	@-rm -fr "$(REPORTS_DIR)/fixed-docf.txt"
	@bash -c '$(CONDA_CMD) \
		docformatter \
			--pre-summary-newline \
			--wrap-descriptions 0 \
			--wrap-summaries 120 \
			--make-summary-multi-line \
			--in-place \
			--recursive \
			$(APP_ROOT) \
		1> >(tee "$(REPORTS_DIR)/fixed-docf.txt")'

.PHONY: fix-fstring
fix-fstring: mkdir-reports install-dev    ## fix code string formats substitutions to f-string definitions automatically
	@echo "Fixing code string formats substitutions to f-string definitions..."
	@-rm -f "$(REPORTS_DIR)/fixed-fstring.txt"
	@bash -c '$(CONDA_CMD) \
		flynt $(FLYNT_FLAGS) "$(APP_ROOT)" \
		1> >(tee "$(REPORTS_DIR)/fixed-fstring.txt")'

.PHONY: fix-css
fix-css: mkdir-reports install-npm		## fix CSS styles problems automatically
	@echo "Fixing CSS style problems..."
	@npx stylelint \
		--fix \
		--config "$(APP_ROOT)/.stylelintrc.json" \
		--output-file "$(REPORTS_DIR)/fixed-css.txt" \
		"$(APP_ROOT)/**/*.css"

## --- Test targets --- ##

.PHONY: test
test: test-all	## alias for 'test-all' target

.PHONY: test-all
test-all: install-dev install test-only  ## run all tests combinations

.PHONY: test-all
test-all: install-dev install test-only  ## run all tests combinations

.PHONY: test-only
test-only:  ## run all tests, but without prior dependency check and installation
	@echo "Running tests..."
	@bash -c '$(CONDA_CMD) pytest tests -vv --junitxml "$(APP_ROOT)/tests/results.xml"'

.PHONY: test-api
test-api: install-dev install		## run only API tests with the environment Python
	@echo "Running local tests..."
	@bash -c '$(CONDA_CMD) pytest tests -vv -m "api" --junitxml "$(APP_ROOT)/tests/results.xml"'


.PHONY: test-cli
test-cli: install-dev install		## run only CLI tests with the environment Python
	@echo "Running local tests..."
	@bash -c '$(CONDA_CMD) pytest tests -vv -m "cli" --junitxml "$(APP_ROOT)/tests/results.xml"'

.PHONY: test-geoserver 
test-geoserver: install-dev install		## run Geoserver requests tests against a configured Geoserver instance. Most of these tests are "online" tests
	@echo "Running local tests..."
	@bash -c '$(CONDA_CMD) pytest tests -vv -m "geoserver" --junitxml "$(APP_ROOT)/tests/results.xml"'

.PHONY: test-magpie
test-magpie: install-dev install		## run Magpie requests tests against a configured Magpie instance. Most of these tests are "online" tests
	@echo "Running local tests..."
	@bash -c '$(CONDA_CMD) pytest tests -vv -m "magpie" --junitxml "$(APP_ROOT)/tests/results.xml"'

# test target used by github's ci
.PHONY: test-github
test-github:  ## runs all tests except online tests, without prior dependency check and installation
	@echo "Running tests..."
	@bash -c '$(CONDA_CMD) pytest tests -vv -m "not online" --junitxml "$(APP_ROOT)/tests/results.xml"'

.PHONY: test-custom
test-custom: install-dev install	## run custom marker tests using SPEC="<marker-specification>"
	@echo "Running custom tests..."
	@[ "${SPEC}" ] || ( echo ">> 'TESTS' is not set"; exit 1 )
	@bash -c '$(CONDA_CMD) pytest tests -vv -m "${SPEC}" --junitxml "$(APP_ROOT)/tests/results.xml"'

.PHONY: test-docker
test-docker: docker-test			## alias for 'docker-test' target [WARNING: could build image if missing]

# coverage file location cannot be changed
COVERAGE_FILE     := $(APP_ROOT)/.coverage
COVERAGE_HTML_DIR := $(REPORTS_DIR)/coverage
COVERAGE_HTML_IDX := $(COVERAGE_HTML_DIR)/index.html
$(COVERAGE_FILE): install-dev
	@echo "Running coverage analysis..."
	@bash -c '$(CONDA_CMD) coverage run --source "$(APP_ROOT)/$(APP_NAME)" \
		`which pytest` tests -m "not remote" || true'
	@bash -c '$(CONDA_CMD) coverage xml -i -o "$(REPORTS_DIR)/coverage.xml"'
	@bash -c '$(CONDA_CMD) coverage report -m'
	@bash -c '$(CONDA_CMD) coverage html -d "$(COVERAGE_HTML_DIR)"'
	@-echo "Coverage report available: file://$(COVERAGE_HTML_IDX)"

.PHONY: coverage
coverage: install-dev install $(COVERAGE_FILE)	## check code coverage and generate an analysis report

.PHONY: coverage-show
coverage-show: $(COVERAGE_HTML_IDX)		## display HTML webpage of generated coverage report (run coverage if missing)
	@-test -f "$(COVERAGE_HTML_IDX)" || $(MAKE) -C "$(APP_ROOT)" coverage
	$(BROWSER) "$(COVERAGE_HTML_IDX)"

## --- Conda setup targets --- ##

.PHONY: conda-base
conda-base:	 ## obtain a base distribution of conda if missing and required
	@[ $(CONDA_SETUP) -eq 0 ] && echo "Conda setup disabled." || ( ( \
		test -f "$(CONDA_HOME)/bin/conda" || test -d "$(DOWNLOAD_CACHE)" || ( \
			echo "Creating download directory: $(DOWNLOAD_CACHE)" && \
			mkdir -p "$(DOWNLOAD_CACHE)") ) ; ( \
		test -f "$(CONDA_HOME)/bin/conda" || \
		test -f "$(DOWNLOAD_CACHE)/$(FN)" || ( \
			echo "Fetching conda distribution from: $(CONDA_URL)/$(FN)" && \
		 	curl "$(CONDA_URL)/$(FN)" --insecure --location --output "$(DOWNLOAD_CACHE)/$(FN)") ) ; ( \
		test -f "$(CONDA_HOME)/bin/conda" || ( \
		  	bash "$(DOWNLOAD_CACHE)/$(FN)" -b -u -p "$(CONDA_HOME)" && \
		 	echo "Make sure to add '$(CONDA_HOME)/bin' to your PATH variable in '~/.bashrc'.") ) \
	)

.PHONY: conda-cfg
conda_config: conda-base	## update conda package configuration
	@echo "Updating conda configuration..."
	@"$(CONDA_HOME)/bin/conda" config --set ssl_verify true
	@"$(CONDA_HOME)/bin/conda" config --set use_pip true
	@"$(CONDA_HOME)/bin/conda" config --set channel_priority true
	@"$(CONDA_HOME)/bin/conda" config --set auto_update_conda false
	@"$(CONDA_HOME)/bin/conda" config --add channels defaults

# the conda-env target's dependency on conda-cfg above was removed, will add back later if needed

.PHONY: conda-env
conda-env: conda-base	## create conda environment if missing and required
	@[ $(CONDA_SETUP) -eq 0 ] || ( \
		test -d "$(CONDA_ENV_PATH)" || ( \
			echo "Creating conda environment at '$(CONDA_ENV_PATH)'..." && \
		 	"$(CONDA_HOME)/bin/conda" create -y -n "$(CONDA_ENV_NAME)" python=$(PYTHON_VERSION)) \
		)
