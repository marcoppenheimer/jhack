import ast
import inspect
import logging
import shutil
import tempfile
import typing
from pathlib import Path
from subprocess import Popen
from typing import Optional

from typer import Option

from logger import logger

from ops.charm import CharmBase
from ops.model import StatusBase

from charm.update import update
from charm.utilities import cwd

RESOURCE_ROOT = Path(__file__).parent / 'resources' / 'functional-charm'
DEFAULT_PACKED_CHARM_TEMPLATE = (
            RESOURCE_ROOT / 'functional-charm_ubuntu-20.04-amd64.charm').absolute()

PREFIX = '''#!/usr/bin/env python3
# Copyleft 4242 functional.py

"""
Charm the service! 
Automatically generated by jhack.charm.functional
"""

'''

# fmt: off
def _proto(self: CharmBase, logger: logging.Logger = None): ...  # noqa
def _proto1(self: CharmBase, logger: logging.Logger = None) -> None: ...  # noqa
def _proto2(self: CharmBase, logger: logging.Logger = None) -> StatusBase: ...  # noqa
def _proto3(self: CharmBase, logger: logging.Logger = None) -> Optional[StatusBase]: ...  # noqa
# fmt: on


_protos = [_proto, _proto1, _proto2, _proto3]


def _check_signature(fn):
    sig = inspect.signature(fn)
    if not any(sig == inspect.signature(p) for p in _protos):
        raise ValueError(
            'function signature needs to be '
            '(self:CharmBase, logger:logging.Logger=None) -> Optional[StatusBase]')


def charm(fn: typing.Callable[
    [CharmBase, Optional[logging.Logger]], Optional[StatusBase]]):
    """Decorator to wrap a function and make it a charm's init."""
    _check_signature(fn)


class NotFound(RuntimeError):
    pass


def _get_charm_function(file, name):
    """Parse file for @charm-decorated function."""
    file = Path(file)
    tree = ast.parse(file.read_text())
    fns = filter(lambda fn: isinstance(fn, ast.FunctionDef), ast.walk(tree))

    def is_charm_decorated(fn_tok):
        for decorator in fn_tok.decorator_list:
            if decorator.id == 'charm':
                return True
        return False

    charm_decorated_fns = filter(is_charm_decorated, fns)

    if name:
        try:
            fn = next(filter(lambda fn_: fn_.name == name, charm_decorated_fns))
        except StopIteration:
            raise NotFound()
    else:
        try:
            fn = next(charm_decorated_fns)
        except StopIteration:
            raise NotFound()

    # we rename the function and drop the decorator
    fn.decorator_list = [dec for dec in fn.decorator_list if dec.id != 'charm']
    ori_name = fn.name
    fn.name = 'charm'
    return fn, ori_name


def _load_charm_source():
    charm_source = RESOURCE_ROOT / 'src' / 'charm.py'

    if not charm_source.exists():
        raise ValueError('charm source not found')
    return ast.parse(charm_source.read_text())


def _inject_fn(charm_source, charm_fn):
    charm_init = lambda node: getattr(node, 'name', None) == '__init__'
    charm_init = next(filter(charm_init, ast.walk(charm_source)))
    charm_init.body.insert(1, charm_fn)
    return charm_init


def _update_built_charm(source: str, template, dry_run):
    with tempfile.TemporaryDirectory() as tempdir:
        (Path(tempdir) / 'charm.py').write_text(source)
        update(template, src=[tempdir], dst=('src',), dry_run=dry_run)


def run(file: str,
        name: str = None,
        dry_run: bool = False,
        built_charm_template=DEFAULT_PACKED_CHARM_TEMPLATE,
        deploy: str = Option(
            None, '-d', '--deploy-name',
            help='App name under which to deploy the charm; '
                 'if left blank, the charm will not be deployed')
        ):
    try:
        import astunparse
    except ModuleNotFoundError:
        logger.info(f'this function requires the `astunparse` module. '
              f'To solve: `pip install astunparse`')
        return

    try:
        charm_fn, ori_name = _get_charm_function(file, name)
    except NotFound:
        print(f'@charm-decorated function (with name {name}) not found in {file}')
        return

    charm_source = _load_charm_source()
    charm_init = _inject_fn(charm_source, charm_fn)

    new_source = PREFIX + astunparse.unparse(charm_source)

    if dry_run:
        logger.info('resulting charm.py file:')
        logger.info(new_source)

    # we don't just overwrite our template:
    i = 0
    while True:
        charm_name = ori_name + (f'_{i}' if i else '') + '.charm'
        charm_package = Path() / charm_name
        if not charm_package.exists():
            break
        i += 1

    shutil.copyfile(built_charm_template, charm_package)
    _update_built_charm(new_source, charm_package, dry_run)

    print(f'charm ready at {charm_package.absolute()}')
    if deploy:
        cmd = f"juju deploy ./{charm_name}"
        if dry_run:
            print(f'would run: {cmd}')
            return
        proc = Popen(cmd.split(), cwd=charm_package.parent.absolute())
        proc.wait()

    print('all done.')


if __name__ == '__main__':

    @charm
    def foo(self: CharmBase, logger: logging.Logger = None):
        from ops.model import ActiveStatus
        return ActiveStatus('welcome to functional charms')

    run(__file__, name='foo', deploy='foo')
