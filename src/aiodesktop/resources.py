import logging
import os
import sys
from pathlib import Path
from typing import Union, NamedTuple, Dict, List, Tuple


__all__ = ('PathLike', 'Resource', 'Bundle')

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

IS_FROZEN = hasattr(sys, '_MEIPASS')


class Resource(NamedTuple):
    bundle: 'Bundle'
    alias: Path  # path to file on compilation stage
    mount: Path  # path to file inside bundle

    @property
    def abspath(self) -> Path:
        """
        Return path to file at runtime.
        """
        return self.bundle.get_abspath(self)

    def __repr__(self):
        return (
            f'Resource('
            f'abspath={self.abspath!r}, '
            f')'
        )

    __str__ = __repr__


class Bundle:
    """
    Bundles are used to manage files inside directory which is created when
    PyInstaller runs your exe. When app is ran from executable, PyInstaller
    adds `sys._MEIPASS` attribute which points to this directory.

    This class is responsible for:
      * checking for name clashes
      * generating `data` argument passed to PyInstaller
    """

    def __init__(self, prefix: PathLike = 'resources'):
        self._prefix = Path(prefix)

        if not IS_FROZEN:
            self._items: Dict[Path, Resource] = {}

    @property
    def prefix(self) -> Path:
        return self._prefix

    if IS_FROZEN:  # available only when frozen
        def get_root(self) -> Path:
            """
            Get path to root directory of this resource bundle.
            """
            # noinspection PyUnresolvedReferences,PyProtectedMember
            return Path(sys._MEIPASS) / self.prefix

    def get_abspath(self, r: 'Resource') -> Path:
        """
        Return absolute path to resource.
        """
        if IS_FROZEN:
            return self.get_root() / r.mount
        else:
            return r.alias.resolve()

    def add(self, path: PathLike, mount: PathLike = None) -> Resource:
        """
        Add given path to a resource bundle.
        """
        alias = Path(path)

        if mount is not None:
            mount = Path(mount) if isinstance(mount, str) else mount

            if mount.is_absolute():
                raise ValueError(f'Mount path {mount!r} must be relative')
        else:
            mount = Path(alias.name)

        if len(mount.parts) != 1:
            raise NotImplementedError(mount)

        resource = Resource(self, alias, mount)

        if not IS_FROZEN:
            if not alias.exists():
                raise ValueError(f'Path {alias!r} does not exist')

            # Check name clashes
            if resource.mount in self._items:
                raise NotImplementedError(
                    f'multiple resources under same mount path {mount!r}'
                )
            else:
                self._items[resource.mount] = resource
                logger.debug('added resource file %r', resource)
        else:
            # When frozen, locate given resource in PyInstaller's directory
            if not resource.abspath.exists():
                # Instruct user, as this part is tricky
                root = self.get_root()
                contents = list(root.glob('*'))
                raise ValueError(
                    f'Path {str(path)!r} not found among registered paths'
                    f', the contents of the root directory: ' +
                    (
                        '\n'.join(f' * {str(p)!r}' for p in contents) + '\n'
                        if bool(contents)
                        else '\n * (no files)\n'
                    ) +
                    'Please make sure that data arguments were passed '
                    'to PyInstaller'
                )

        return resource

    def get_pyinstaller_data(self) -> List[Tuple[str, str]]:
        """
        Return data argument to PyInstaller. It's a list of (source, target).

        Example usage in .spec files:

            >>> from app import server
            ... a = Analysis(
            ...     ...,
            ...     datas=server.resources.get_pyinstaller_data(),
            ...     ...
            ... )
        """
        assert not IS_FROZEN

        def get_pyinstaller_path(r: Resource):
            out = self.prefix / r.mount
            if r.abspath.is_file():
                out = out.parent
            return out

        return [
            (str(r.abspath), str(get_pyinstaller_path(r)))
            for r in self._items.values()
        ]

    def get_pyinstaller_args(self) -> str:
        """
        Return command line arguments to PyInstaller.
        """
        return ' '.join(
            f'--add-data={abs_path}{os.pathsep}{target_path}'
            for abs_path, target_path in self.get_pyinstaller_data()
        )
