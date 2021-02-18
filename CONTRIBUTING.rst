Contributing
============

Contributions are welcome, and they are greatly appreciated!
Every little bit helps, and credit will always be given.
All contributors are presented in |authors|_ file.

You can contribute in many ways:

Types of Contributions
----------------------


Report Bugs
~~~~~~~~~~~

Report bugs as a `new issue`_.

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.


Write Documentation
~~~~~~~~~~~~~~~~~~~

Cowbird could always use more documentation, whether as part of the
official Cowbird docs, in docstrings, or even on the web in blog posts,
articles, and such.

Submit Feedback
~~~~~~~~~~~~~~~

The best way to send feedback is to file a `new issue`_.

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

Provide utilities
~~~~~~~~~~~~~~~~~

If you made a convenient utility or tool that works conjointly with `Cowbird` in other to provide useful features or
simply provide ease-of-life, don't hesitate to open a PR referring to it in the documentation `utilities`_. We love
sharing and avoiding to rewrite stuff.

Get Started!
------------

Ready to contribute? Here's how to set up `cowbird` for local development.

1. Clone the repository ::

    git clone https://github.com/Ouranosinc/cowbird


2. Install your local copy (see `installation`_)

3. When you're done making changes, check that your changes pass code formatting and tests::

    make check
    make test


4. Commit your changes and push your branch to GitHub.
5. Submit a pull request to the author (tests will run to evaluate that everything still works).


Pull Request Guidelines
-----------------------

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds functionality, the docs should be updated. Put
   your new functionality into a function with a docstring, and add the
   feature to the list in |changes|_ (under relevant category of section `Unreleased`).
3. The tests should work for the specified version of Python for this project.


Tips
----

To run a subset of tests::

    make SPEC="<CUSTOM TEST SPECIFICATIONS>" test-custom


With ``<CUSTOM TEST SPECIFICATIONS>`` being any predefined markers, specific test classes or functions as supported
by ``pytest`` runner.

.. References for this page
.. _new issue: https://github.com/Ouranosinc/cowbird/issues/new
.. |authors| replace:: AUTHORS
.. _authors: AUTHORS.rst
.. |changes| replace:: CHANGES
.. _changes: CHANGES.rst
.. _installation: docs/installation.rst
.. _utilities: docs/utilities.rst
