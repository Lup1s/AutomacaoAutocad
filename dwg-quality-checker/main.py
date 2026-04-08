"""Compatibility CLI entrypoint.

Este módulo delega para `checker.cli.main` para manter uma única superfície
de CLI oficial e evitar divergência de parâmetros/comportamento.
"""

from checker.cli import main


if __name__ == "__main__":
    main()
