"""cratedigger -- queryable metadata ontologies for music collections.

The modules here are runnable as scripts as well as importable, which is why
the CLI drives them by subprocess rather than by import: a stage that crashes
takes down one process, not the session, and each stage stays usable on its
own without the CLI.
"""
__version__ = "0.1.0"
