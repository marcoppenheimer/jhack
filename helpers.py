import contextlib
import os
from pathlib import Path

from juju.model import Model


@contextlib.asynccontextmanager
async def get_current_model() -> Model:
    model = Model()
    try:
        # connect to the current model with the current user, per the Juju CLI
        await model.connect()
        yield model

    finally:
        if model.is_connected():
            print('Disconnecting from model')
            await model.disconnect()


def get_local_charm() -> Path:
    is_charm = lambda file: file.suffix == '.charm'
    cwd = Path(os.getcwd())
    try:
        return next(filter(is_charm, cwd.iterdir()))
    except StopIteration:
        raise FileNotFoundError(
            f'could not find a charm file in {cwd}'
        )