import logging
import os
import sys
from pathlib import Path
from typing import Union, NamedTuple, Mapping, Dict, List, Tuple


__all__ = ('PathLike', 'Resource', 'Bundle')

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]

IS_FROZEN = hasattr(sys, '_MEIPASS')


class Resource(NamedTuple):
    bundle: 'Bundle'
    alias: Path
    mount: Path

    @property
    def frozen(self): return IS_FROZEN

    @property
    def abspath(self) -> Path:
        return self.bundle.get_abspath(self)

    @property
    def exists(self) -> bool:
        return self.abspath.exists()

    def __repr__(self):
        return (
            f'Resource('
            f'alias={self.alias!r}, '
            f'mount={self.mount!r}, '
            f'abspath={self.abspath!r}, '
            f'frozen={self.frozen!r}'
            f')'
        )

    __str__ = __repr__


class Bundle:
    @property
    def prefix(self) -> Path:
        return self._prefix

    if not IS_FROZEN:
        @property
        def items(self) -> Mapping[Path, Resource]:
            return self._items

    def __init__(self, prefix=Path('resources'),
                 items: Mapping[PathLike, PathLike] = None):
        self._prefix = prefix
        self._get_pyinstaller_data_called = False

        if not IS_FROZEN:
            self._items: Dict[Path, Resource] = {}

            if items is not None:
                for mount in items:
                    path = items[mount]
                    self.add(path, mount=mount)

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
            if not resource.exists:
                # Instruct user, as this part is tricky
                if self._get_pyinstaller_data_called:
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
                else:
                    raise ValueError(
                        f'Data arguments were not passed to PyInstaller, '
                        f'please use {self.get_pyinstaller_data!r}.'
                    )

        return resource

    def get_pyinstaller_data(self) -> List[Tuple[str, str]]:
        """
        Return data argument to PyInstaller.

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

        try:
            return [
                (str(r.abspath), str(get_pyinstaller_path(r)))
                for r in self._items.values()
            ]
        finally:
            self._get_pyinstaller_data_called = True

    def get_pyinstaller_args(self) -> str:
        """
        Return command line arguments to PyInstaller.
        """
        return ' '.join(
            f'--add-data={abs_path}{os.pathsep}{target_path}'
            for abs_path, target_path in self.get_pyinstaller_data()
        )

    def __eq__(self, other):
        return self is other

    def __repr__(self):
        return (
            '{}(prefix={!r}, {})'.format(
                type(self).__name__, self._prefix,
                (
                    'root={!r}'.format(str(self.get_root())) if IS_FROZEN else
                    'items={!r}'.format(self._items)
                )
            )
        )

    __str__ = __repr__
