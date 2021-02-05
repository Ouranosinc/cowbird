.. _installation:
.. include:: references.rst

Installation
=============

Basic Setup
~~~~~~~~~~~~

At the command line::

    make install


This will create a ``conda`` environment named ``cowbird``, and install all required dependencies of the package in it.
You should be ready to employ `Cowbird` with example `configuration`_ files at this point.

Advanced
~~~~~~~~~~~~

To install in another environment, ``CONDA_ENV_NAME`` can be provided to ``make``.

Otherwise, following can be used to install with whichever ``python`` is detected (up to user to manage references)::

    make install-pkg


If you want the full setup for development (including dependencies for test execution), use::

    make install-dev

