"""Assignment configurations for Otter Assign"""

import fica
import os
import pathlib

from typing import Any, Dict, List, Optional

from .constants import AG_DIR_NAME, STU_DIR_NAME

from ..utils import Loggable


# TODO: remove
class MyConfig(fica.Config):

    def get(self, attr, default):
        return getattr(self, attr)

    def __setitem__(self, key, value):
        setattr(self, key, value)


# TODO: add detection/warnings/errors for when a user provides an invalid key? (to be added to fica)
class Assignment(fica.Config, Loggable):
    """
    Configurations for the assignment.
    """

    requirements: Optional[str] = fica.Key(
        description="the path to a requirements.txt file or a list of packages",
        default=None,
    )

    overwrite_requirements: bool = fica.Key(
        description="whether to overwrite Otter's default requirement.txt in Otter Generate",
        default=False,
    )

    environment: Optional[str] = fica.Key(
        description="the path to a conda environment.yml file",
        default=None,
    )

    run_tests: bool = fica.Key(
        description="whether to run the assignment tests against the autograder notebook",
        default=True,
    )

    solutions_pdf: bool = fica.Key(
        description="whether to generate a PDF of the solutions notebook",
        default=False,
    )

    template_pdf: bool = fica.Key(
        description="whether to generate a filtered Gradescope assignment template PDF",
        default=False,
    )

    init_cell: bool = fica.Key(
        description="whether to include an Otter initialization cell in the output notebooks",
        default=True,
    )

    check_all_cell: bool = fica.Key(
        description="whether to include an Otter check-all cell in the output notebooks",
        default=False,
    )

    class ExportCellValue(MyConfig):

        instructions: str = fica.Key(
            description="additional submission instructions to include in the export cell",
            default="",
        )

        pdf: bool = fica.Key(
            description="whether to include a PDF of the notebook in the generated zip file",
            default=True,
        )

        filtering: bool = fica.Key(
            description="whether the generated PDF should be filtered",
            default=True,
        )

        force_save: bool = fica.Key(
            description="whether to force-save the notebook with JavaScript (only works in " \
                "classic notebook)",
            default=False,
        )

        run_tests: bool = fica.Key(
            description="whether to run student submissions against local tests during export",
            default=True,
        )

    export_cell: ExportCellValue = fica.Key(
        description="whether to include an Otter export cell in the output notebooks",
        subkey_container=ExportCellValue,
    )

    class SeedValue(MyConfig):

        variable: Optional[str] = fica.Key(
            description="a variable name to override with the autograder seed during grading",
            default=None,
        )

        autograder_value: Optional[int] = fica.Key(
            description="the value of the autograder seed",
            default=None,
        )

        student_value: Optional[int] = fica.Key(
            description="the value of the student seed",
            default=None,
        )

    seed: SeedValue = fica.Key(
        description="intercell seeding configurations",
        default=None,
        subkey_container=SeedValue,
    )

    generate: bool = fica.Key(
        description="grading configurations to be passed to Otter Generate as an " \
            "otter_config.json; if false, Otter Generate is disabled",
        default=False,
    )

    save_environment: bool = fica.Key(
        description="whether to save the student's environment in the log",
        default=False,
    )

    variables: Optional[Dict[str, str]] = fica.Key(
        description="a mapping of variable names to type strings for serializing environments",
        default=None,
    )

    ignore_modules: List[str] = fica.Key(
        description="a list of modules to ignore variables from during environment serialization",
        default=[],
    )

    files: List[str] = fica.Key(
        description="a list of other files to include in the output directories and autograder",
        default=[],
    )

    autograder_files: List[str] = fica.Key(
        description="a list of other files only to include in the autograder",
        default=[],
    )

    plugins: List[str] = fica.Key(
        description="a list of plugin names and configurations",
        default=[],
    )

    class TestsValue(MyConfig):

        files: bool = fica.Key(
            description="whether to store tests in separate files, instead of the notebook " \
                "metadata",
            default=False,
        )

        ok_format: bool = fica.Key(
            description="whether the test cases are in OK-format (instead of the exception-based " \
                "format)",
            default=True,
        )

        url_prefix: Optional[str] = fica.Key(
            description="a URL prefix for where test files can be found for student use",
            default=None,
        )

    tests: TestsValue = fica.Key(
        description="information about the structure and storage of tests",
        subkey_container=TestsValue,
        enforce_subkeys=True,
    )

    show_question_points: bool = fica.Key(
        description="whether to add the question point values to the last cell of each question",
        default=False,
    )

    runs_on: str = fica.Key(
        description= "the interpreter this notebook will be run on if different from the " \
            "default interpreter (one of {'default', 'colab', 'jupyterlite'})",
        default="default",
        validator=fica.validators.choice(["default", "colab", "jupyterlite"])
    )

    lang: Optional[str] = None
    """the language of the assignment"""

    master: pathlib.Path = None
    """the path to the master notebook"""

    result: pathlib.Path = None
    """the path to the output directory"""

    seed_required: bool = False
    """whether a seeding configuration is required for Otter Generate"""

    _otter_config: Optional[Dict[str, Any]] = None
    """the (parsed) contents of an ``otter_config.json`` file to be used for Otter Generate"""

    _temp_test_dir: Optional[str] = None
    """the path to a directory of test files for Otter Generate"""

    notebook_basename: Optional[str] = None
    """the basename of the master notebook file"""

    def __init__(self, user_config: Dict[str, Any] = {}) -> None:
        self._logger.debug(f"Initializing with config: {user_config}")

        super().__init__(user_config)

    def update_(self, user_config: Dict[str, Any]):
        self._logger.debug(f"Updating config: {user_config}")
        return super().update_(user_config)

    @property
    def is_r(self):
        """
        Whether the language of the assignment is R
        """
        return self.lang == "r"
    
    @property
    def is_python(self):
        """
        Whether the language of the assignment is Python
        """
        return self.lang == "python"

    @property
    def is_rmd(self):
        """
        Whether the input file is an RMarkdown document
        """
        return self.master.suffix.lower() == ".rmd"

    @property
    def notebook_basename(self):
        return os.path.basename(str(self.master))

    @property
    def ag_notebook_path(self):
        return self.result / AG_DIR_NAME / self.notebook_basename

    def get_ag_path(self, path=""):
        """
        """
        return self.result / AG_DIR_NAME / path

    def get_stu_path(self, path=""):
        """
        """
        return self.result / STU_DIR_NAME / path
