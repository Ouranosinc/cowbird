.. explicit references must be used in this file (not references.rst) to ensure they are directly rendered on Github
.. :changelog:

Changes
*******

`Unreleased <https://github.com/Ouranosinc/cowbird/tree/master>`_ (latest)
------------------------------------------------------------------------------------

* Nothing yet.

`0.4.1 <https://github.com/Ouranosinc/cowbird/tree/0.4.1>`_ (2022-03-09)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Add an SSL verification setting.
* Add Geoserver workspace and datastore creation/removal linked to user creation/removal.
* Add automated publishing of shapefiles to Geoserver when new files are found.
* Use ``pip`` legacy and faster resolver as per
  `pypa/pip#9187 (comment) <https://github.com/pypa/pip/issues/9187#issuecomment-853091201>`_
  since current one is endlessly failing to resolve development packages (linting tools from ``check`` targets).

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* Pin ``pymongo<4`` to work with pinned ``celery`` version.

`0.4.0 <https://github.com/Ouranosinc/cowbird/tree/0.4.0>`_ (2021-08-05)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Basic users' workspaces management for new or removed users.
* Add a Mongo database backend to store/restore monitoring state across sessions.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* Celery has now a proper result backend.
* Celery tasks are auto-discovered package-wide, no need to import them manually.

`0.3.0 <https://github.com/Ouranosinc/cowbird/tree/0.3.0>`_ (2021-07-06)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Add the RequestTask celery task for handling external services requests.
* Add a docker image for the celery worker

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a

`0.2.0 <https://github.com/Ouranosinc/cowbird/tree/0.2.0>`_ (2021-05-12)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Preliminary design which includes:

  - Webhook API
  - Services interface
  - Permissions synchronizer
  - File system monitoring

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a

`0.1.0 <https://github.com/Ouranosinc/cowbird/tree/0.1.0>`_ (2021-02-18)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* First structured release which includes:

  - CI/CD utilities
  - Minimal testing of *utils*
  - Documentation of generic details (WebApp, CLI, OpenAPI, configs, etc.)
  - Metadata of the package
  - Minimal ``/services`` API route with dummy ``Service``
  - Corresponding ``cowbird services list`` CLI command

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a
