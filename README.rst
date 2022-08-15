.. explicit references must be used in this file (not references.rst) to ensure they are directly rendered on Github

======================================
Cowbird: Middleware operation service
======================================
Cowbird (the brood parasite)
  |
  | *The brood parasite manipulates a host, either of the same or of another species,
    *to raise its young as if it were its own*

  | *The shiny cowbird is an obligate brood parasite, meaning that adults will lay their eggs in the nests of other*
    *species and their offspring rely entirely on their hosts for parental care.*

  | (`Wikipedia`_)


.. _Wikipedia: https://en.wikipedia.org/wiki/Brood_parasite

Cowbird is a middleware that manages interactions between various *birds* of the `bird-house`_ stack.

It therefore relies on the existence of other services under a common architecture, but applies changes to
the resources under those services such that the complete ecosystem can seamlessly operate together
(see `Components Diagram`_).


.. start-badges

.. list-table::
    :stub-columns: 1
    :widths: 20 80

    * - dependencies
      - | |py_ver| |dependencies|
    * - build status
      - | |readthedocs|
    * - tests status
      - | |github_latest| |github_tagged| |coverage| |codacy|
    * - docker status
      - | |docker_build_mode| |docker_build_status|
    * - releases
      - | |version| |commits-since|

.. |py_ver| image:: https://img.shields.io/badge/python-3.7%2B-blue.svg
    :alt: Requires Python 3.7+
    :target: https://www.python.org/getit

.. |commits-since| image:: https://img.shields.io/github/commits-since/Ouranosinc/cowbird/0.5.0.svg
    :alt: Commits since latest release
    :target: https://github.com/Ouranosinc/cowbird/compare/0.5.0...master

.. |version| image:: https://img.shields.io/badge/tag-0.5.0-blue.svg?style=flat
    :alt: Latest Tag
    :target: https://github.com/Ouranosinc/cowbird/tree/0.5.0

.. |dependencies| image:: https://pyup.io/repos/github/Ouranosinc/cowbird/shield.svg
    :alt: Dependencies Status
    :target: https://pyup.io/account/repos/github/Ouranosinc/cowbird/

.. |github_latest| image:: https://img.shields.io/github/workflow/status/Ouranosinc/cowbird/Tests/master?label=master
    :alt: Github Actions CI Build Status (master branch)
    :target: https://github.com/Ouranosinc/cowbird/actions?query=branch%3Amaster

.. |github_tagged| image:: https://img.shields.io/github/workflow/status/Ouranosinc/cowbird/Tests/0.5.0?label=0.5.0
    :alt: Github Actions CI Build Status (latest tag)
    :target: https://github.com/Ouranosinc/cowbird/tree/0.5.0

.. |readthedocs| image:: https://img.shields.io/readthedocs/pavics-cowbird
    :alt: Readthedocs Build Status (master branch)
    :target: `readthedocs`_

.. |coverage| image:: https://img.shields.io/codecov/c/gh/Ouranosinc/cowbird.svg?label=coverage
    :alt: Travis-CI CodeCov Coverage
    :target: https://codecov.io/gh/Ouranosinc/cowbird

.. |codacy| image:: https://app.codacy.com/project/badge/Grade/618d09472fe54aa4a0fc418b0e1a20ac
    :alt: Codacy Badge
    :target: https://app.codacy.com/gh/Ouranosinc/cowbird/dashboard

.. |docker_build_mode| image:: https://img.shields.io/docker/cloud/automated/pavics/cowbird.svg?label=build
    :alt: Docker Build Status (latest tag)
    :target: https://hub.docker.com/r/pavics/cowbird/builds

.. |docker_build_status| image:: https://img.shields.io/docker/cloud/build/pavics/cowbird.svg?label=status
    :alt: Docker Build Status (latest tag)
    :target: https://hub.docker.com/r/pavics/cowbird/builds

.. end-badges

--------------
Documentation
--------------

The `REST API`_ documentation is auto-generated and served under ``{COWBIRD_URL}/api/`` using
Swagger-UI with tag ``latest``.

| More ample details about installation, configuration and usage are provided on `readthedocs`_.
| These are generated from corresponding information provided in `docs`_.

----------------------------
Configuration and Usage
----------------------------

| Multiple configuration options exist for ``Cowbird`` application.
| Please refer to `configuration`_ for details.
| See `usage`_ for details.

--------------
Change History
--------------

Addressed features, changes and bug fixes per version tag are available in |changes|_.

--------------
Docker Images
--------------

Following most recent variants are available:

.. list-table::
    :header-rows: 1
    :stub-columns: 1

    * - Version
      - Cowbird Base
      - Cowbird Worker
      - Cowbird Web Service
    * - Most Recent Release
      - |cowbird_tag_base|_
      - |cowbird_tag_worker|_
      - |cowbird_tag_websvc|_
    * - Latest Commit
      - |cowbird_latest_base|_
      - |cowbird_latest_worker|_
      - |cowbird_latest_websvc|_


.. |cowbird_tag_base| replace:: pavics/cowbird:0.5.0
.. _cowbird_tag_base: https://hub.docker.com/r/pavics/cowbird/tags?page=1&ordering=last_updated&name=0.5.0
.. |cowbird_tag_worker| replace:: pavics/cowbird:0.5.0-worker
.. _cowbird_tag_worker: https://hub.docker.com/r/pavics/cowbird/tags?page=1&ordering=last_updated&name=0.5.0-worker
.. |cowbird_tag_websvc| replace:: pavics/cowbird:0.5.0-webservice
.. _cowbird_tag_websvc: https://hub.docker.com/r/pavics/cowbird/tags?page=1&ordering=last_updated&name=0.5.0-webservice

.. |cowbird_latest_base| replace:: pavics/cowbird:latest
.. _cowbird_latest_base: https://hub.docker.com/r/pavics/cowbird/tags?page=1&ordering=last_updated&name=latest
.. |cowbird_latest_worker| replace:: pavics/cowbird:latest-worker
.. _cowbird_latest_worker: https://hub.docker.com/r/pavics/cowbird/tags?page=1&ordering=last_updated&name=latest-worker
.. |cowbird_latest_websvc| replace:: pavics/cowbird:latest-webservice
.. _cowbird_latest_websvc: https://hub.docker.com/r/pavics/cowbird/tags?page=1&ordering=last_updated&name=latest-webservice


**Notes:**

- Older tags the are also available: `Docker Images`_


.. These reference must be left direct (not included with 'references.rst') to allow pretty rendering on Github
.. |changes| replace:: CHANGES
.. _changes: CHANGES.rst
.. _Components Diagram: docs/components.rst
.. _configuration: docs/configuration.rst
.. _installation: docs/installation.rst
.. _usage: docs/usage.rst
.. _utilities: docs/utilities.rst
.. _readthedocs: https://pavics-cowbird.readthedocs.io
.. _docs: https://github.com/Ouranosinc/cowbird/tree/master/docs
.. _bird-house: https://github.com/bird-house/birdhouse-deploy
.. _Pyramid: https://docs.pylonsproject.org/projects/pyramid/
.. _Docker Images: https://hub.docker.com/r/pavics/cowbird/tags

.. REST API redoc reference is auto-generated by sphinx from cowbird cornice-swagger definitions
.. _REST API: https://pavics-cowbird.readthedocs.io/en/latest/api.html
