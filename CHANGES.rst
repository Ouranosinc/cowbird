.. explicit references must be used in this file (not references.rst) to ensure they are directly rendered on Github
.. :changelog:

Changes
*******

`Unreleased <https://github.com/Ouranosinc/cowbird/tree/master>`_ (latest)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Add an ssl verification setting.
* Add Geoserver workspace and datastore creation/removal linked to user creation/removal.
* Add automated publishing of shapefiles to Geoserver when new files are found.

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
