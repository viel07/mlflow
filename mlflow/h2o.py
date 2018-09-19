"""
The ``mlflow.h2o`` module provides an API for logging and loading H2O models. This module exports
H2O models with the following flavors:

H20 (native) format
    This is the main flavor that can be loaded back into H2O.
:py:mod:`mlflow.pyfunc`
    Produced for use by generic pyfunc-based deployment tools and batch inference.
"""

from __future__ import absolute_import

import os
import yaml

from mlflow import pyfunc
from mlflow.models import Model
import mlflow.tracking


def save_model(h2o_model, path, conda_env=None, mlflow_model=Model(), settings=None):
    """
    Save an H2O model to a path on the local file system.

    :param h2o_model: H2O model to be saved.
    :param path: Local path where the model is to be saved.
    :param mlflow_model: :py:mod:`mlflow.models.Model` this flavor is being added to.

    >>> import mlflow
    >>> import mlflow.h2o
    >>> import h2o
    >>> #create, train, and evaluate your h2o model
    >>> h2o_model = ...
    >>> #set path where to save, local or remote, accessible from code
    >>> h2o_model_dir = ...
    >>> mlflow.h2o.save_model(h2o_model, h2o_model_dir)
    """
    import h2o

    path = os.path.abspath(path)
    if os.path.exists(path):
        raise Exception("Path '{}' already exists".format(path))
    model_dir = os.path.join(path, "model.h2o")
    os.makedirs(model_dir)

    # Save h2o-model
    h2o_save_location = h2o.save_model(model=h2o_model, path=model_dir, force=True)
    model_file = os.path.basename(h2o_save_location)

    # Save h2o-settings
    if settings is None:
        settings = {}
    settings['full_file'] = h2o_save_location
    settings['model_file'] = model_file
    settings['model_dir'] = model_dir
    with open(os.path.join(model_dir, "h2o.yaml"), 'w') as settings_file:
        yaml.safe_dump(settings, stream=settings_file)

    pyfunc.add_to_model(mlflow_model, loader_module="mlflow.h2o",
                        data="model.h2o", env=conda_env)
    mlflow_model.add_flavor("h2o", saved_model=model_file, h2o_version=h2o.__version__)
    mlflow_model.save(os.path.join(path, "MLmodel"))


def log_model(h2o_model, artifact_path, **kwargs):
    """
    Log an H2O model as an MLflow artifact for the current run.

    :param h2o_model: H2O model to be saved.
    :param artifact_path: Run-relative artifact path.
    :param kwargs: kwargs to pass to ``h2o.save_model`` method.

    >>> import mlflow
    >>> import mlflow.h2o
    >>> import h2o
    >>> from h2o.estimators.glm import H2OGeneralizedLinearEstimator
    >>> h2o.init()
    >>> #Partial example code used from H20 documentation <http://docs.h2o.ai/h2o/latest-stable/h2o-docs/data-science/algo-params/early_stopping.html>
    >>> # import the cars dataset:
    >>> # this dataset is used to classify whether or not a car is economical based on
    >>> # the car's displacement, power, weight, and acceleration, and the year it was made
    >>> cars = h2o.import_file("https://s3.amazonaws.com/h2o-public-test-data/smalldata/junit/cars_20mpg.csv")
    >>> # convert response column to a factor
    >>> cars["economy_20mpg"] = cars["economy_20mpg"].asfactor()
    >>> # set the predictor names and the response column name
    >>> predictors = ["displacement","power","weight","acceleration","year"]
    >>> response = "economy_20mpg"
    >>> # split into train and validation sets
    >>> train, valid = cars.split_frame(ratios = [.8])
    >>> # try using the `early_stopping` parameter:
    >>> # Initialize and train a GLM
    >>> h2o_model = H2OGeneralizedLinearEstimator(family = 'binomial', early_stopping = True)
    >>> h2o_model.train(x = predictors, y = response, training_frame = train, validation_frame = valid)
    >>> #log parameters
    >>> mlflow.log_param("early_stopping", "True")
    >>> mlflow.log_param("response", response)
    >>> mlflow.log_param("family", "binomial")
    >>> #log the model
    >>> mlflow.h2o.log_model(h20_model, "h2o_models")
    """
    Model.log(artifact_path=artifact_path, flavor=mlflow.h2o,
              h2o_model=h2o_model, **kwargs)


def _load_model(path, init=False):
    import h2o
    path = os.path.abspath(path)
    with open(os.path.join(path, "h2o.yaml")) as f:
        params = yaml.safe_load(f.read())
    if init:
        h2o.init(**(params["init"] if "init" in params else {}))
        h2o.no_progress()
    return h2o.load_model(os.path.join(path, params['model_file']))


class _H2OModelWrapper:
    def __init__(self, h2o_model):
        self.h2o_model = h2o_model

    def predict(self, dataframe):
        import h2o
        predicted = self.h2o_model.predict(h2o.H2OFrame(dataframe)).as_data_frame()
        predicted.index = dataframe.index
        return predicted


def load_pyfunc(path):
    """
    Load a persisted H2O model as a ``python_function`` model.
    This method calls ``h2o.init``, so the right version of h2o(-py) must be in the
    environment. The arguments given to ``h2o.init`` can be customized in ``path/h2o.yaml``
    under the key ``init``.

    :param path: Local filesystem path to the model saved by :py:func:`mlflow.h2o.save_model`.
    :rtype: Pyfunc format model with function
            ``model.predict(pandas DataFrame) -> pandas DataFrame``.

    >>> import mlflow
    >>> import mlflow.h2o
    >>> import h2o
    >>> # set the path to where the h20 model is saved: local or remote, accessible
    >>> # from code here
    >>> h2o_model_dir = ...
    >>> # set the test Pandas DataFrame
    >>> pandas_df = ...
    >>> h2o_model = mlflow.h2o.load_pyfunc(h20_model_dir)
    >>> predictions = h2o_model.predict(pandas_df)
    """
    return _H2OModelWrapper(_load_model(path, init=True))


def load_model(path, run_id=None):
    """
    Load an H2O model from a local file (if ``run_id`` is ``None``) or a run.
    This function expects there is an H2O instance initialised with ``h2o.init``.

    :param path: Local filesystem path or run-relative artifact path to the model saved
                 by :py:func:`mlflow.h2o.save_model`.
    :param run_id: Run ID. If provided, combined with ``path`` to identify the model.

    >>> import mlflow
    >>> import mlflow.h2o
    >>> import h2o
    >>> # set the path to where the h2o model is saved: local or remote, accessible
    >>> # from code here
    >>> h2o_model_dir = ...
    >>> run_id="96771d893a5e46159d9f3b49bf9013e2"
    >>> h2o_model = mlflow.h2o.load_model(h2o_model_dir, run_id)
    """
    if run_id is not None:
        path = mlflow.tracking.utils._get_model_log_dir(model_name=path, run_id=run_id)
    return _load_model(os.path.join(path, "model.h2o"))
