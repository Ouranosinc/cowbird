.. include:: references.rst

.. _usage:
.. _usage_page:

========
Usage
========

In most situation, you will want to run `Cowbird` as a `Web Application`_ in combination with a larger set
of `bird-house`_ components forming a server instance. A minimal `docker-compose.yml`_ example is provided,
but `Cowbird`'s actual configuration will greatly depend on your actual service requirements.


Setup and Validation
----------------------

To use `Cowbird` in a project, first you need to install it. To do so, please follow steps in :ref:`installation` and
:ref:`configuration` procedures.

After this, you should be able to call the CLI :ref:`utilities` to validate it is installed properly using:

.. code-block:: console

    cowbird --help


Web Application
----------------------

To start the Web Application, you can simply run the following command:

.. code-block:: console

    make start

This will first install any missing dependencies in the current environment (see :ref:`installation`), and will
after start a basic Web Application on ``localhost:7000`` with default configurations.
Please refer to :ref:`configuration` if any of the parameters needs adjustment for custom environments.

For running the application, multiple `WSGI HTTP Servers` can be employed (e.g.: `Gunicorn`_, `Waitress`_, etc.).
They usually all support as input an INI configuration file for specific settings. `Cowbird` also employs such INI file
(`cowbird.ini`_) to customize its behaviour.
See :ref:`configuration` for further details, and please refer to the employed `WSGI` application documentation of your
liking for their respective setup requirements.


API
----------------------

When the application is started, the Swagger API should be available under ``/api`` path. This will render the *current*
version API and applicable requests. Please refer to this documentation to discover all provided API paths and
events supported by `Cowbird` on a *running* instance (that could be older than latest code base). Alternatively,
documentation of *all* versions is available on `ReadTheDocs`_.


CLI
----------------------

After successful :ref:`installation` of `Cowbird` package, multiple helper :ref:`utilities` become available
as CLI applications callable from the shell. These can be quite useful to run typical `Cowbird` events calls
from the terminal without having to form corresponding HTTP requests.
Please refer to the relevant page for further details.

Documentation
----------------------

The documentation is automatically built by `ReadTheDocs`_. It is generated from the `documentation source <../docs>`_,
the parsing of Python ``docstrings`` within the code, the code itself, and the `Cowbird REST API`_.

You can also preview the result by building the documentation locally using:

.. code-block:: console

    make docs


The resulting location will be printed on the terminal and can be opened in a web browser.


Testing
----------------------

Tests are executed using a Web Application that gets spawned by a set of default configurations to run HTTP requests
against.

.. note::
    To customize execution parameters, you can export variables such as ``COWBIRD_INI_FILE_PATH`` for example,
    and they will be picked up to validate specific results against defined :ref:`configuration`.


When adding new features or fixing bugs, it is recommended to execute linting checks and tests locally prior to opening
a PR, as each PR gets tested and you will waste more time waiting for results to complete then if ran locally.

To validate linting of the code, simply call:

.. code-block:: console

    make check


To run all tests locally, simply execute the following command:

.. code-block:: console

    make test


Coverage analysis with the same set of tests is also available using:

.. code-block:: console

    make coverage


You can also run subsets of tests according to markers and/or specific test function ``pytest`` specification using:

.. code-block:: console

    make SPEC="<CUSTOM TEST SPECIFICATIONS>" test-custom


Or some of the predefined filters:

.. code-block:: console

    make test-api
    make test-cli


Finally, the following command can be executed to built and run a smoke test of the resulting `Docker`_ image:

.. code-block:: console

    make test-docker

